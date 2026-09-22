"""Bounded, lossless text loading and conflict-checked editing for Compare."""
import codecs
import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path


TEXT_EDIT_LIMIT = 2 * 1024 * 1024


@dataclass
class TextDocument:
    path: Path
    text: str
    encoding: str
    bom: bytes
    ending: str
    digest: str
    reason: str = ''

    @property
    def description(self):
        newline = {'\n': 'LF', '\r\n': 'CRLF', '\r': 'CR', '': 'Mixed EOL'}[self.ending]
        return f'{self.encoding.upper()}{" BOM" if self.bom else ""} · {newline}' + (
            f' · Read-only: {self.reason}' if self.reason else '')

    def save(self, text):
        if self.reason:
            raise OSError(self.reason)
        if self.path.is_symlink():
            raise OSError('Symbolic links are read-only in Compare.')
        current = read_text_document(self.path)
        if current.reason:
            raise OSError(current.reason)
        if current.digest != self.digest:
            raise OSError('The file changed on disk. Reopen it before editing; your text has not been discarded.')
        normalized = text.replace('\r\n', '\n').replace('\r', '\n')
        data = self.bom + normalized.replace('\n', self.ending).encode(self.encoding, errors='strict')
        if len(data) > TEXT_EDIT_LIMIT:
            raise OSError('The edited file exceeds the 2 MiB text limit. Your draft has not been discarded.')
        mode = stat.S_IMODE(self.path.stat().st_mode)
        # Same-directory replacement avoids a partially written original on an
        # interrupted save. Refuse hard links: replacement would split the link.
        if self.path.stat().st_nlink > 1:
            raise OSError('Hard-linked files are read-only in Compare.')
        fd, name = tempfile.mkstemp(prefix='.pfc-edit-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, mode)
            if read_text_document(self.path).digest != self.digest:
                raise OSError('The file changed during save. No overwrite was performed.')
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                replace = ctypes.WinDLL('kernel32', use_last_error=True).ReplaceFileW
                replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                    wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
                replace.restype = wintypes.BOOL
                # Unlike a plain rename, preserve Windows ACLs/streams. Never
                # opt into IGNORE_ACL_ERRORS on a failed metadata merge.
                if not replace(str(self.path.absolute()), name, None, 0, None, None):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                import shutil
                shutil.copystat(self.path, name)
                os.utime(name, None)
                os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        self.text = normalized
        self.digest = hashlib.sha256(data).hexdigest()


def read_text_document(path):
    path = Path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise OSError('Text Compare requires an ordinary file.')
    with path.open('rb') as stream:
        data = stream.read(TEXT_EDIT_LIMIT + 1)
    if len(data) > TEXT_EDIT_LIMIT:
        raise OSError('Text Compare is limited to 2 MiB per file. Use folder content comparison for larger files.')
    encoding, bom, reason = 'utf-8', b'', ''
    for marker, codec in ((codecs.BOM_UTF32_LE, 'utf-32-le'), (codecs.BOM_UTF32_BE, 'utf-32-be'),
                          (codecs.BOM_UTF8, 'utf-8'), (codecs.BOM_UTF16_LE, 'utf-16-le'),
                          (codecs.BOM_UTF16_BE, 'utf-16-be')):
        if data.startswith(marker):
            encoding, bom = codec, marker
            break
    try:
        text = data[len(bom):].decode(encoding, errors='strict')
    except UnicodeDecodeError:
        text = data[len(bom):].decode(encoding, errors='replace')
        reason = 'Unknown or invalid encoding; no automatic conversion'
    if '\x00' in text:
        reason = 'Binary data or encoding without a BOM'
    crlf = text.count('\r\n')
    kinds = ([ '\r\n' ] if crlf else []) + (['\n'] if text.count('\n') > crlf else []) + (
        ['\r'] if text.count('\r') > crlf else [])
    ending = kinds[0] if len(kinds) == 1 else ('\n' if not kinds else '')
    if not ending:
        reason = reason or 'Mixed line endings; no automatic conversion'
    if path.is_symlink():
        reason = 'Symbolic link'
    elif info.st_nlink > 1:
        reason = 'Hard-linked file'
    elif not info.st_mode & 0o222 or getattr(info, 'st_file_attributes', 0) & 1:
        reason = 'Read-only file'
    return TextDocument(path, text.replace('\r\n', '\n').replace('\r', '\n'), encoding, bom,
                        ending, hashlib.sha256(data).hexdigest(), reason)
