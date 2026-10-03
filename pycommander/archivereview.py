"""Transactional archive comparison drafts; originals change only on commit."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from .archivefs import ArchiveSession, _seven_zip_executable, _hidden_process_options, ArchiveCancelled


ARCHIVE_REVIEW_BUDGET = 2 * 1024 * 1024 * 1024


def archive_digest(path,cancel=None):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            if cancel and cancel.is_set():raise ArchiveCancelled('Archive operation cancelled')
            digest.update(block)
    return digest.hexdigest()


def checked_archive_members(path):
    """Reject dangerous members before extraction, including Windows aliases."""
    records=[]; path=Path(path)
    if path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as z:
            for i in z.infolist():
                if i.flag_bits&1:raise OSError('Encrypted archives are read-only in Compare')
                mode=i.external_attr>>16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)):
                    raise OSError('Archive contains links or special files')
                records.append((i.filename,i.file_size,i.is_dir()))
    else:
        exe=_seven_zip_executable()
        if not exe:raise OSError('Install or configure 7-Zip to compare 7z archives')
        result=subprocess.run([exe,'l','-slt','--',str(path)],stdin=subprocess.DEVNULL,capture_output=True,
                              text=True,errors='replace',timeout=30,**_hidden_process_options())
        if result.returncode:raise OSError('Cannot list archive; encrypted or unsupported archive')
        body=result.stdout.partition('----------')[2]
        for block in body.replace('\r\n','\n').split('\n\n'):
            fields=dict(line.split(' = ',1) for line in block.splitlines() if ' = ' in line)
            if 'Path' not in fields:continue
            if fields.get('Encrypted')=='+':raise OSError('Encrypted archives are read-only in Compare')
            if fields.get('Symbolic Link') or fields.get('Hard Link') or 'Reparse' in fields.get('Attributes',''):
                raise OSError('Archive contains links')
            # 7-Zip versions differ: some emit Folder=+, others only the DOS
            # D attribute. A real directory must not become a colliding file.
            directory=fields.get('Folder')=='+' or 'D' in fields.get('Attributes','')
            records.append((fields['Path'],int(fields.get('Size','0')),directory))
    names=set();total=0; files=set()
    reserved={'CON','PRN','AUX','NUL'}|{f'{prefix}{n}' for prefix in ('COM','LPT') for n in range(1,10)}
    for name,size,isdir in records:
        p=PurePosixPath(name.replace('\\','/'));parts=p.parts
        if not parts or p.is_absolute() or '..' in parts or any(
                ':' in part or part.endswith((' ','.')) or part.split('.')[0].upper() in reserved or '\x00' in part for part in parts):
            raise OSError('Unsafe archive member: '+name)
        key=p.as_posix().rstrip('/').casefold()
        if key in names:raise OSError('Duplicate or case-colliding archive member: '+name)
        names.add(key)
        if not isdir:files.add(key)
        total+=size
        if len(names)>100000 or total>ARCHIVE_REVIEW_BUDGET:raise OSError('Archive exceeds 100,000 members / 2 GiB expanded safety budget')
    for name in names:
        if any(parent.as_posix().casefold() in files for parent in PurePosixPath(name).parents if str(parent)!='.'):
            raise OSError('Archive file/folder path collision')
    return records,total


def archive_manifest(root,cancel=None):
    result={};pending=[Path(root)];total=0
    while pending:
        directory=pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if cancel and cancel.is_set():raise ArchiveCancelled('Archive operation cancelled')
                path=Path(entry.path);info=entry.stat(follow_symlinks=False)
                if entry.is_symlink() or getattr(info,'st_file_attributes',0)&0x400 or (stat.S_ISREG(info.st_mode) and info.st_nlink>1):
                    raise OSError('Archive draft contains links')
                relative=path.relative_to(root).as_posix()
                if stat.S_ISDIR(info.st_mode):result[relative+'/']=None;pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    total+=info.st_size
                    if total>ARCHIVE_REVIEW_BUDGET:raise OSError('Archive draft exceeds 2 GiB budget')
                    result[relative]=archive_digest(path,cancel)
                else:raise OSError('Archive draft contains a special file')
                if len(result)>100000:raise OSError('Archive draft exceeds 100,000 members')
    return result


class ArchiveReviewSession:
    def __init__(self,path,cancel=None):
        self.path=Path(path).absolute(); self.cancel=cancel or threading.Event();self.backup=None
        if self.path.is_symlink() or self.path.stat().st_nlink>1:raise OSError('Linked archives are read-only')
        self.records,self.expanded=checked_archive_members(self.path)
        if shutil.disk_usage(tempfile.gettempdir()).free<self.expanded*2+64*1024*1024:
            raise OSError('Insufficient temporary space for safe archive comparison')
        self.digest=archive_digest(self.path)
        self.session=ArchiveSession(self.path,cancel_event=self.cancel);self.root=self.session.root
        try:
            self.original=archive_manifest(self.root,self.cancel)
            if archive_digest(self.path)!=self.digest:raise OSError('Archive changed while opening')
        except Exception:self.session.close();raise
        self.removed=tempfile.TemporaryDirectory(prefix='pfc-archive-removed-');self.deletions=[]

    def delete_from_draft(self,names):
        targets=[]
        for name in names:
            relative=PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or not relative.parts:raise OSError('Invalid draft path')
            path=self.root.joinpath(*relative.parts)
            if path.is_symlink() or self.root not in path.resolve().parents:raise OSError('Invalid draft destination')
            if path.exists():targets.append(path)
        for path in sorted(set(targets),key=lambda p:len(p.parts)):
            if not path.exists():continue  # Already included in a selected parent.
            backup=Path(self.removed.name)/uuid.uuid4().hex
            path.rename(backup);self.deletions.append((path,backup))

    def undo_delete(self):
        if not self.deletions:return
        path,backup=self.deletions[-1]
        if path.exists():raise OSError('A new item now occupies the deleted path; no overwrite')
        path.parent.mkdir(parents=True,exist_ok=True);backup.rename(path);self.deletions.pop()

    def changes(self):
        current=archive_manifest(self.root,self.cancel)
        return [(name,'Add' if name not in self.original else 'Delete' if name not in current else 'Replace')
                for name in sorted(set(current)|set(self.original)) if current.get(name,'missing')!=self.original.get(name,'missing')]

    def commit(self,approved=None):
        if self.cancel.is_set():raise ArchiveCancelled('Cancelled')
        if self.path.is_symlink() or self.path.stat().st_nlink>1 or archive_digest(self.path)!=self.digest:
            raise OSError('Original archive changed; draft retained, no overwrite')
        expected=archive_manifest(self.root,self.cancel)
        if approved is not None and expected!=approved:raise OSError('Draft changed after review; no archive write')
        if not self.changes():return None
        expanded=sum((self.root/name).stat().st_size for name in expected if not name.endswith('/'))
        if expanded>ARCHIVE_REVIEW_BUDGET or len(expected)>100000:raise OSError('Archive draft exceeds safety budget')
        if shutil.disk_usage(self.path.parent).free<expanded+self.path.stat().st_size*2+64*1024*1024:
            raise OSError('Insufficient space for archive staging and backup')
        fd,raw=tempfile.mkstemp(prefix='.pfc-archive-review-',suffix=self.path.suffix,dir=self.path.parent);os.close(fd)
        staging=Path(raw);backup=self.path.with_name(self.path.name+'.pfc-backup-'+uuid.uuid4().hex[:10])
        try:
            if self.path.suffix.lower()=='.zip':
                with zipfile.ZipFile(self.path) as original,zipfile.ZipFile(staging,'w') as output:
                    infos={i.filename.replace('\\','/'):i for i in original.infolist()}
                    output.comment=original.comment
                    for name in expected:
                        if self.cancel.is_set():raise ArchiveCancelled('Cancelled')
                        old=infos.get(name)
                        if old is not None:
                            if name.endswith('/'):output.writestr(old,b'')
                            else:
                                with output.open(old,'w') as dst, (self.root/name).open('rb') as src:shutil.copyfileobj(src,dst,1024*1024)
                        elif name.endswith('/'):output.writestr(name,b'')
                        else:output.write(self.root/name,name,compress_type=zipfile.ZIP_DEFLATED)
            else:
                staging.unlink()
                process=subprocess.Popen([_seven_zip_executable(),'a','-t7z','-mx=5','--',str(staging),'.'],cwd=self.root,
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**_hidden_process_options())
                started=time.monotonic()
                try:
                    while process.poll() is None:
                        if self.cancel.wait(.05):raise ArchiveCancelled('Cancelled')
                        if time.monotonic()-started>180:raise OSError('7-Zip compression timed out')
                    if process.returncode:raise OSError('7-Zip could not build the staged archive')
                finally:
                    if process.poll() is None:process.terminate();process.wait(timeout=5)
            checked_archive_members(staging)
            verify=ArchiveSession(staging,cancel_event=self.cancel)
            try:
                if archive_manifest(verify.root,self.cancel)!=expected:raise OSError('Archive verification failed; original untouched')
            finally:verify.close()
            if self.cancel.is_set():raise ArchiveCancelled('Cancelled')
            if self.path.is_symlink() or self.path.stat().st_nlink>1 or archive_digest(self.path)!=self.digest:raise OSError('Archive changed during save; original untouched')
            with backup.open('xb') as dst,self.path.open('rb') as src:
                shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
            shutil.copystat(self.path,backup)
            if archive_digest(backup)!=self.digest or archive_digest(self.path)!=self.digest:
                raise OSError('Archive changed during backup; no overwrite')
            shutil.copystat(self.path,staging)
            if os.name=='nt':
                import ctypes
                from ctypes import wintypes
                replace=ctypes.WinDLL('kernel32',use_last_error=True).ReplaceFileW
                replace.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_void_p,ctypes.c_void_p]
                replace.restype=wintypes.BOOL
                if not replace(str(self.path),str(staging),None,0,None,None):raise ctypes.WinError(ctypes.get_last_error())
            else:os.replace(staging,self.path)
            self.digest=archive_digest(self.path);self.original=expected;self.backup=backup
            return backup
        finally:staging.unlink(missing_ok=True)

    def cleanup(self):self.cancel.set();self.session.close();self.removed.cleanup()
