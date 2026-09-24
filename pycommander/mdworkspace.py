"""Opt-in, bounded Markdown discovery. No persistent index or automatic scans."""
import os
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from .mdlinks import markdown_destination, read_linked_markdown

MD_EXCLUDES = frozenset({'.git', '.svn', 'node_modules', '.venv', 'venv', '__pycache__'})
MD_UNSAFE_ATTRIBUTES = 0x400 | 0x1000 | 0x40000 | 0x400000


def remember_markdown_workspace(config, root, depth):
    if not config.has_section('markdown_workspace'): config.add_section('markdown_workspace')
    # ConfigParser interprets percent signs; paths must survive a save/reload.
    config.set('markdown_workspace', 'root', str(root).replace('%', '%%'))
    config.set('markdown_workspace', 'depth', str(depth))


def wiki_destination(value):
    """Parse visible wikilink text without touching the filesystem."""
    target, sep, alias = value.partition('|')
    name, hashmark, fragment = target.partition('#')
    name = name.strip(); fragment = fragment.strip()
    if (len(value) > 1024 or any(ord(c) < 32 for c in value)
            or any(c in name for c in '\\:*?<>"') or name.startswith('/')
            or (name and any(p in ('.', '..', '') or p.endswith((' ', '.')) for p in name.split('/')))):
        raise ValueError('Invalid wiki destination')
    if not name and not fragment:
        raise ValueError('Invalid wiki destination')
    if fragment.startswith('^'):
        raise ValueError('Block references are not supported')
    if name and Path(name).suffix and Path(name).suffix.casefold() != '.md':
        raise ValueError('Only Markdown documents can be followed')
    filename = name if not name or name.casefold().endswith('.md') else name + '.md'
    return {'name': filename, 'fragment': fragment,
            'label': alias.strip() if sep and alias.strip() else (target if name else fragment),
            'href': quote(filename, safe='/') + ('#' + quote(fragment, safe='') if hashmark else '')}


def workspace_root(value, document):
    """Lexical scope check; filesystem validation happens only in the worker."""
    if not value or not Path(value).is_absolute():
        raise ValueError('Choose an absolute project folder')
    root = Path(os.path.abspath(value))
    if root == Path(root.anchor) or root == Path.home():
        raise ValueError('Choose a project folder, not a drive root or home folder')
    try:
        Path(os.path.abspath(document)).relative_to(root)
    except ValueError:
        raise ValueError('The project folder must contain the current document') from None
    if any(p.startswith('pfc-archive-') for p in root.parts):
        raise ValueError('Cross-document links are disabled inside archives')
    return root


@contextmanager
def workspace_entries(path):
    """Keep validated directory handles alive while enumerating one level.

    Windows denies deletion/renaming of all ancestors; POSIX opens relative to
    retained descriptors with O_NOFOLLOW. Cloud/reparse/mount paths fail closed.
    This is not an adversarial-filesystem sandbox or a provider no-recall API.
    """
    path = Path(os.path.abspath(path)); handles = []
    if os.name != 'nt':
        try:
            fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY); handles.append(fd)
            device = os.fstat(fd).st_dev
            for part in path.parts[1:]:
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                handles.append(fd)
                if os.fstat(fd).st_dev != device:
                    raise ValueError('Mounted paths are not supported for linked preview')
            with os.scandir(fd) as entries:
                yield entries
        finally:
            for fd in reversed(handles): os.close(fd)
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                   ctypes.c_void_p, wintypes.DWORD]
    if not path.drive or str(path).startswith('\\\\') or kernel.GetDriveTypeW(path.anchor) != 3:
        raise ValueError('Only fixed local drives are supported for linked preview')
    try:
        for part in [*reversed(path.parents), path]:
            handle = kernel.CreateFileW(str(part), 0x80, 1, None, 3,
                                        0x02000000 | 0x00200000 | 0x00100000, None)
            if handle == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle); attrs = (wintypes.DWORD * 2)()
            if not kernel.GetFileInformationByHandleEx(handle, 9, attrs, ctypes.sizeof(attrs)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not attrs[0] & 0x10 or attrs[0] & MD_UNSAFE_ATTRIBUTES:
                raise ValueError('Cloud-only, linked or unknown reparse paths cannot be followed')
        with os.scandir(path) as entries:
            yield entries
    finally:
        for handle in reversed(handles): kernel.CloseHandle(handle)


def scan_markdown_workspace(request, parse_document, decode):
    """Single explicit scan, shared budgets across all branches and file reads."""
    root = workspace_root(request['root'], request['path'])
    depth = int(request.get('depth', 3))
    if depth not in (1, 3, 5, 8): raise ValueError('Invalid search depth')
    mode = request.get('mode', 'files')
    if mode not in ('files', 'wiki', 'backlinks'): raise ValueError('Invalid search mode')
    query = str(request.get('query', '')).strip()
    if len(query) > 256: raise ValueError('Search text is too long')
    target = Path(os.path.abspath(request['path']))
    # Callers may lower budgets in tests, but never raise the release ceilings.
    max_entries = max(1, min(5000, int(request.get('max_entries', 5000))))
    deadline = time.monotonic() + max(.001, min(3., float(request.get('seconds', 3))))
    pending = [(root, 0)]; seen = 0; skipped = 0; byte_count = 0
    results = []; reasons = set(); examined = 0
    while pending:
        if time.monotonic() >= deadline: reasons.add('time'); break
        directory, level = pending.pop()
        try:
            with workspace_entries(directory) as entries:
                for entry in entries:
                    if time.monotonic() >= deadline: reasons.add('time'); break
                    if seen >= max_entries: reasons.add('entries'); break
                    seen += 1
                    if entry.name.casefold() in MD_EXCLUDES:
                        skipped += 1; continue
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & MD_UNSAFE_ATTRIBUTES:
                            skipped += 1; reasons.add('unavailable'); continue
                        path = directory / entry.name
                        if stat.S_ISDIR(info.st_mode):
                            if level < depth: pending.append((path, level + 1))
                            else: skipped += 1
                            continue
                        if not stat.S_ISREG(info.st_mode) or path.suffix.casefold() != '.md': continue
                        detail = 'Filename match'
                        if mode == 'wiki':
                            candidate = str(path.relative_to(root)).replace(os.sep, '/') if '/' in query else entry.name
                            if candidate.casefold() != query.casefold(): continue
                        if mode == 'files' and query.casefold() not in entry.name.casefold(): continue
                        if mode == 'backlinks':
                            if path == target: continue
                            if info.st_size > 256 * 1024:
                                skipped += 1; reasons.add('large documents'); continue
                            remaining = 8 * 1024 * 1024 - byte_count
                            if remaining <= 0 or info.st_size > remaining:
                                reasons.add('content budget'); break
                            read_limit = min(256 * 1024, remaining)
                            data, _ = read_linked_markdown(path, root, read_limit)
                            byte_count += len(data)
                            if len(data) > read_limit:
                                if read_limit < 256 * 1024:
                                    reasons.add('content budget'); break
                                skipped += 1; reasons.add('large documents'); continue
                            examined += 1
                            model = parse_document(decode(data)[0]); matches = []
                            for link in model.get('links', []):
                                try:
                                    if link.get('wiki'):
                                        wiki = wiki_destination(link['wiki'])
                                        if wiki['name'] and '/' not in wiki['name']:
                                            if wiki['name'].casefold() == target.name.casefold():
                                                matches.append('Possible filename reference')
                                            continue
                                        href = wiki['href']
                                        resolved, _ = markdown_destination(root / '__scope__.md', root, href)
                                    else:
                                        resolved, _ = markdown_destination(path, root, link['href'])
                                    if os.path.normcase(str(resolved)) == os.path.normcase(str(target)):
                                        matches.append('Exact path reference')
                                except (ValueError, UnicodeError): continue
                            if not matches: continue
                            detail = 'Exact path reference' if 'Exact path reference' in matches else matches[0]
                        results.append({'path': str(path.relative_to(root)), 'detail': detail})
                        if len(results) >= 50: reasons.add('results'); break
                    except (OSError, ValueError):
                        skipped += 1; reasons.add('unavailable')
        except (OSError, ValueError):
            if directory == root: raise
            skipped += 1; reasons.add('unavailable')
        if reasons & {'entries', 'time', 'results', 'content budget'}: break
    if time.monotonic() >= deadline: reasons.add('time')
    return {'results': sorted(results, key=lambda r: r['path'].casefold()),
            'root': str(root), 'visited': seen, 'skipped': skipped, 'examined': examined,
            'reasons': sorted(reasons), 'mode': mode, 'depth': depth}
