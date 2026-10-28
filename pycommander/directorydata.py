"""Per-listing metadata snapshots: one stat per item, no persistent disk cache."""
from dataclasses import dataclass
from pathlib import Path
import stat as statlib

from .fileops import is_hidden, is_system


@dataclass(frozen=True)
class DirectoryItem:
    path: Path
    metadata: object

    @property
    def is_dir(self):
        return self.metadata is not None and statlib.S_ISDIR(self.metadata.st_mode)


def listing_items(paths):
    rows=[]
    for path in paths:
        try:metadata=path.stat()
        except OSError:metadata=None
        rows.append(DirectoryItem(path,metadata))
    return tuple(rows)


def directory_items(folder,show_hidden=False,show_system=False,reveal=None):
    # Preserve GetFileAttributesW visibility semantics for Windows links rather
    # than substituting the followed target's stat attributes.
    return listing_items(path for path in folder.iterdir() if path==reveal or
        ((show_hidden or not is_hidden(path)) and (show_system or not is_system(path))))


def listing_signature(rows):
    # Results may span folders and share a basename. Keep their full identity,
    # and never compare unavailable None metadata with another row's numbers.
    records=((str(row.path),row.metadata.st_size,row.metadata.st_mtime_ns,row.metadata.st_mode)
             if row.metadata is not None else (str(row.path),None,None,None) for row in rows)
    return tuple(sorted(records,key=lambda record:record[0]))


def ordered_listing(rows,column='name',reverse=False,mix=True):
    def key(row):
        if column=='name':return row.path.name.lower()
        if column=='ext':return row.path.suffix.lower()
        # Unreadable entries still participate in the signature, but never mix
        # a string key into an otherwise numeric sort.
        value=(row.metadata.st_size if column=='size' else row.metadata.st_mtime) if row.metadata is not None else 0
        return value
    rows=sorted(rows,key=key,reverse=reverse)
    if not mix:rows.sort(key=lambda row:not row.is_dir)
    return rows
