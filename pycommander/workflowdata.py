"""Small local workflow records, explicit compare rules and inert reports."""
import fnmatch
import html
import json
import os
import stat
import tempfile
from collections import Counter
from pathlib import Path


DEFAULT_COMPARE_EXCLUDES = '.git;.svn;node_modules;.venv;__pycache__'


def compare_path_blocked(path):
    info = Path(path).lstat()
    # Do not follow junctions, symlinks, cloud placeholders or special devices.
    return (stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))
            or bool(getattr(info, 'st_file_attributes', 0) & (0x400 | 0x1000 | 0x40000 | 0x400000)))


class WorkflowRecords:
    """Named INI metadata only: no directory discovery, indexing or file content."""
    LIMIT = 40

    def __init__(self, config, key):
        self.config, self.key = config, key

    def read(self):
        raw = self.config.get('workflows', self.key, fallback='[]')
        try:
            records = json.loads(raw) if len(raw) <= 1024 * 1024 else []
            if not isinstance(records, list): return []
            return [r for r in records if isinstance(r, dict) and isinstance(r.get('name'), str)
                    and isinstance(r.get('data'), dict)][:self.LIMIT]
        except (ValueError, TypeError):
            return []

    def write(self, records):
        serialized = json.dumps(records[:self.LIMIT], ensure_ascii=False)
        if len(serialized) > 1024 * 1024:
            raise ValueError('Saved workflow data exceeds the limit. Remove an entry before saving more.')
        if not self.config.has_section('workflows'): self.config.add_section('workflows')
        self.config.set('workflows', self.key, serialized)

    def put(self, name, data):
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError('Use a name between 1 and 80 characters.')
        entries = [r for r in self.read() if r['name'].casefold() != name.casefold()]
        if len(entries) >= self.LIMIT:
            raise ValueError('Forty saved entries is the limit. Remove one before adding another.')
        self.write([{'name': name, 'data': data}] + entries)

    def remove(self, name):
        self.write([r for r in self.read() if r['name'] != name])


def compare_excluded(relative, patterns):
    """Semicolon globs: bare names at any depth, paths relative to selected roots."""
    value = str(relative).replace('\\', '/').strip('/')
    pieces = value.casefold().split('/')
    rules = ['.git', '.svn'] + [p.strip().replace('\\', '/').strip('/').casefold()
                                for p in patterns.split(';') if p.strip()]
    prefixes = ['/'.join(pieces[:i]) for i in range(1, len(pieces) + 1)]
    return any(any(fnmatch.fnmatchcase(part, rule) for part in (prefixes if '/' in rule else pieces))
               for rule in rules)


def compare_sync_plans(rows, actions, left_root, right_root, left_read_only=False, right_read_only=False):
    """Only individually scanned files. Never copy a directory recursively.

    This is essential: a recursive directory copy would silently reintroduce
    excluded files, cloud placeholders and new unreviewed children.
    """
    choices = {os.path.normcase(str(Path(key))): value for key, value in actions.items()}
    plans = []
    for _status, key, left, right in rows:
        relative = Path(key)
        action = choices.get(os.path.normcase(str(relative)))
        if action is None:
            # Probe only ancestors, not every selected row: selecting 10,000
            # files must not create a 100-million-comparison UI pause.
            for parent in relative.parents:
                action = choices.get(os.path.normcase(str(parent)))
                if action is not None: break
        if action == 'right' and left is not None and not right_read_only:
            source, target = left, Path(right_root) / key
        elif action == 'left' and right is not None and not left_read_only:
            source, target = right, Path(left_root) / key
        else:
            continue
        if not compare_path_blocked(source) and source.is_file():
            destination_root = Path(right_root) if action == 'right' else Path(left_root)
            ancestors = [target] + list(target.parents)
            if any((p.exists() or p.is_symlink()) and compare_path_blocked(p) for p in ancestors
                   if p == destination_root or destination_root in p.parents):
                continue
            plans.append((source, target))
    return plans


def comparison_report(rows, rules, format='html'):
    """Relative names only; inert HTML, no source content or absolute roots."""
    statuses = Counter(row[0] for row in rows)
    rule_text = '; '.join(f'{key}: {value}' for key, value in rules.items())
    summary = ', '.join(f'{key}: {value}' for key, value in sorted(statuses.items()))
    if format == 'text':
        return 'PFC comparison report\n' + rule_text + '\n' + summary + '\n\n' + '\n'.join(
            f'{status}\t{relative}' for status, relative, *_ in rows) + '\n'
    body = ''.join(f'<tr><td>{html.escape(status)}</td><td>{html.escape(relative)}</td></tr>'
                   for status, relative, *_ in rows)
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<meta name="viewport" content="width=device-width"><title>PFC comparison report</title>'
            '<style>body{font:15px system-ui;margin:24px;color:#203447;background:#fff}'
            'table{border-collapse:collapse;width:100%}td,th{padding:7px 10px;text-align:left;'
            'border-bottom:1px solid #ccd5df;overflow-wrap:anywhere}th{background:#e9eef3}'
            'p{overflow-wrap:anywhere}</style><h1>PFC comparison report</h1><p>' + html.escape(rule_text) +
            '</p><p>' + html.escape(summary) + '</p><table><thead><tr><th>Status</th><th>Relative path</th>'
            '</tr></thead><tbody>' + body + '</tbody></table></html>')


def write_comparison_report(destination, rows, rules):
    """Export cannot target a compared source through a link/alias either."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        info = destination.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
            raise OSError('Choose an ordinary report file, not a linked or special file.')
    canonical = destination.resolve()
    if any(canonical == path.resolve() for row in rows for path in row[2:] if path):
        raise OSError('The report cannot replace a compared file.')
    content = comparison_report(rows, rules, 'text' if destination.suffix.lower() == '.txt' else 'html')
    descriptor, staging = tempfile.mkstemp(prefix='.pfc-report-', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.replace(staging, destination)
    finally:
        if os.path.exists(staging): os.unlink(staging)


def reading_anchor(model, offset, fraction, signature):
    before = [h for h in model.get('headings', []) if h['start'] <= offset]
    heading = before[-1] if before else None
    return dict(heading=heading['title'] if heading else '', fraction=float(fraction),
                offset=max(0, offset - heading['start']) if heading else 0,
                signature=list(signature or []))


def resolve_reading_anchor(model, saved, signature):
    """No fuzzy lookup: unchanged file -> view; changed -> unique heading only."""
    if saved.get('signature') == list(signature or []):
        fraction = saved.get('fraction', 0)
        return ('fraction', min(1., max(0., float(fraction))), False)
    matches = [h for h in model.get('headings', []) if h['title'] == saved.get('heading')]
    if len(matches) == 1:
        return ('offset', matches[0]['start'], True)
    return ('fraction', 0., True)
