"""Exact Markdown destinations and conservative, non-searching local reads."""
import os
import re
import stat
from pathlib import Path
from urllib.parse import unquote, urlsplit


def markdown_destination(document, boundary, href):
    """Lexical only: never stat, enumerate, resolve symlinks or access a target."""
    if len(href)>4096 or re.search(r'[\x00-\x20\x7f]', href):
        raise ValueError('Invalid link destination')
    if re.search(r'%(?![0-9a-fA-F]{2})',href):
        raise ValueError('Invalid link encoding')
    parsed=urlsplit(href)
    if parsed.scheme or parsed.netloc or parsed.query:
        raise ValueError('Only local Markdown links are supported')
    name=unquote(parsed.path,errors='strict')
    fragment=unquote(parsed.fragment,errors='strict')
    if any(ord(c)<32 or ord(c)==127 for c in name+fragment):
        raise ValueError('Invalid link destination')
    if not name:
        return Path(document),fragment
    # Reject Windows forms on every platform, not just the developer's OS.
    if name.startswith(('/', '\\')) or ':' in name or '\\' in name:
        raise ValueError('Absolute, network and device paths are not supported')
    if any(part.endswith((' ','.')) and part not in ('.','..') for part in name.split('/')):
        raise ValueError('Ambiguous path spelling')
    if any(re.match(r'(?i)^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)',part)
           for part in name.split('/')):
        raise ValueError('Device paths are not supported')
    if Path(name).suffix.casefold()!='.md':
        raise ValueError('Only Markdown documents can be followed')
    root=Path(os.path.abspath(boundary))
    target=Path(os.path.abspath(Path(document).parent/name))
    try: target.relative_to(root)
    except ValueError: raise ValueError('Link leaves the preview folder boundary') from None
    return target,fragment


def read_linked_markdown(path, boundary, limit):
    """Read a regular file without following directory links or cloud recalls.

    Unknown Windows reparse points are deliberately refused (including cloud
    cases not yet proven safe). No Shell operations or directory enumeration.
    Run only in an isolated preview worker, never on Tk's thread.
    """
    target=Path(os.path.abspath(path));root=Path(os.path.abspath(boundary))
    try: target.relative_to(root)
    except ValueError: raise ValueError('Link leaves the preview folder boundary') from None
    if target.suffix.casefold()!='.md': raise ValueError('Only Markdown documents can be followed')
    if os.name=='nt': return _read_windows_markdown(target,root,limit)
    # Open each component relative to an already opened directory handle.
    # Renaming/replacing a parent cannot redirect the subsequent open.
    handles=[]
    try:
        fd=os.open(target.anchor,os.O_RDONLY|os.O_DIRECTORY);handles.append(fd)
        device=os.fstat(fd).st_dev
        for part in target.parts[1:-1]:
            fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            handles.append(fd)
            if os.fstat(fd).st_dev!=device:
                raise ValueError('Mounted paths are not supported for linked preview')
        fd=os.open(target.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        handles.append(fd);info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode): raise ValueError('Target is not a regular file')
        if info.st_dev!=device: raise ValueError('Mounted paths are not supported for linked preview')
        chunks=[];remaining=limit+1
        while remaining:
            chunk=os.read(fd,min(remaining,65536))
            if not chunk: break
            chunks.append(chunk);remaining-=len(chunk)
        return b''.join(chunks),(info.st_mtime_ns,info.st_size)
    finally:
        for fd in reversed(handles): os.close(fd)


def _read_windows_markdown(target, root, limit):
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetDriveTypeW.argtypes=[wintypes.LPCWSTR]
    if not target.drive or str(target).startswith('\\\\') or kernel.GetDriveTypeW(target.anchor)!=3:
        raise ValueError('Only fixed local drives are supported for linked preview')
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
        ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.GetFileInformationByHandleEx.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.GetFinalPathNameByHandleW.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
    class FileIdentity(ctypes.Structure):
        _fields_=[('Attributes',wintypes.DWORD),('Created',wintypes.FILETIME),
            ('Accessed',wintypes.FILETIME),('Written',wintypes.FILETIME),
            ('Volume',wintypes.DWORD),('SizeHigh',wintypes.DWORD),('SizeLow',wintypes.DWORD),
            ('Links',wintypes.DWORD),('IndexHigh',wintypes.DWORD),('IndexLow',wintypes.DWORD)]
    kernel.GetFileInformationByHandle.argtypes=[wintypes.HANDLE,ctypes.POINTER(FileIdentity)]
    def identity(handle):
        info=FileIdentity()
        if not kernel.GetFileInformationByHandle(handle,ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return info.Volume,info.IndexHigh,info.IndexLow
    handles=[]
    try:
        for part in [*reversed(target.parents),target]:
            final=part==target
            # Deny delete sharing: each checked component stays in place until
            # the read ends. OPEN_REPARSE_POINT + OPEN_NO_RECALL avoids following.
            handle=kernel.CreateFileW(str(part),0x80,
                1,None,3,0x02000000|0x00200000|0x00100000,None)
            if handle==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
            attrs=(wintypes.DWORD*2)()
            if not kernel.GetFileInformationByHandleEx(handle,9,ctypes.byref(attrs),ctypes.sizeof(attrs)):
                raise ctypes.WinError(ctypes.get_last_error())
            if attrs[0] & (0x400|0x1000|0x40000|0x400000):
                raise ValueError('Cloud-only, linked or unknown reparse paths cannot be followed')
            if final and attrs[0]&0x10: raise ValueError('Target is not a regular file')
        buffer=ctypes.create_unicode_buffer(32768)
        count=kernel.GetFinalPathNameByHandleW(handles[-1],buffer,len(buffer),0)
        if not count or count>=len(buffer): raise ValueError('Cannot verify the link target')
        actual=buffer.value
        if actual.startswith('\\\\?\\'): actual=actual[4:]
        if os.path.normcase(actual)!=os.path.normcase(str(target)):
            raise ValueError('Link target changed during validation')
        # Request data access only after every locked component passed metadata
        # checks. Existing handles deny write/delete until this read finishes.
        handle=kernel.CreateFileW(str(target),0x80000000,1,None,3,0x00200000|0x00100000,None)
        if handle==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
        handles.append(handle)
        # Validate the actual data handle as well, before reading any content.
        attrs=(wintypes.DWORD*2)()
        if not kernel.GetFileInformationByHandleEx(handle,9,ctypes.byref(attrs),ctypes.sizeof(attrs)):
            raise ctypes.WinError(ctypes.get_last_error())
        if attrs[0] & (0x10|0x400|0x1000|0x40000|0x400000):
            raise ValueError('Cloud-only, linked or unknown reparse paths cannot be followed')
        count=kernel.GetFinalPathNameByHandleW(handle,buffer,len(buffer),0)
        actual=buffer.value
        if actual.startswith('\\\\?\\'): actual=actual[4:]
        if not count or count>=len(buffer) or os.path.normcase(actual)!=os.path.normcase(str(target)):
            raise ValueError('Link target changed during validation')
        if identity(handles[-2])!=identity(handle):
            raise ValueError('Link target changed during validation')
        fd=msvcrt.open_osfhandle(handles[-1],os.O_RDONLY|os.O_BINARY);handles.pop()
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            return stream.read(limit+1),(info.st_mtime_ns,info.st_size)
    finally:
        for handle in reversed(handles): kernel.CloseHandle(handle)
