"""Atomic auxiliary review exports that cannot replace a compared source."""
import os
from pathlib import Path
import tempfile


def safe_review_write(target,data,sources):
    target=Path(target)
    if target.is_symlink():raise OSError('Linked destinations are not supported')
    for source in sources:
        if target.resolve()==Path(source).resolve() or (target.exists() and Path(source).exists() and os.path.samefile(target,source)):
            raise OSError('An export cannot overwrite a compared source')
    if target.exists() and target.stat().st_nlink>1:raise OSError('Hard-linked destinations are not supported')
    before=target.stat() if target.exists() else None
    fd,name=tempfile.mkstemp(prefix='.pfc-review-',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        after=target.lstat() if target.exists() or target.is_symlink() else None
        identity=lambda info:None if info is None else (info.st_dev,info.st_ino,info.st_mtime_ns,info.st_size,info.st_nlink)
        if target.is_symlink() or identity(before)!=identity(after):raise OSError('Export destination changed; no overwrite')
        os.replace(name,target)
    finally:
        if os.path.exists(name):os.unlink(name)
