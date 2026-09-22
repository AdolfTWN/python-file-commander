"""Read-only VCS discovery/status and explicit Tortoise dialog hand-off.

No command in this module stages, commits, fetches or pushes. GUI commands only
open the client's confirmation dialog; authentication remains with that client.
"""

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VcsLocation:
    kind: str
    root: Path


@dataclass(frozen=True)
class VcsContext:
    location: VcsLocation | None
    focus: Path
    paths: tuple[Path, ...]
    reason: str = ""
    mixed: bool = False


@dataclass(frozen=True)
class VcsSummary:
    changed: int = 0
    untracked: int = 0
    conflicts: int = 0
    branch: str = ""
    upstream: str = ""
    ahead: int | None = None
    behind: int | None = None
    url: str = ""
    error: str = ""


def vcs_absolute(path):
    # Do not resolve a tracked symlink into an unrelated repository.
    return Path(os.path.abspath(path))


def vcs_location(path):
    path = vcs_absolute(path)
    if any(part.casefold() in {'.git', '.svn'} for part in path.parts):
        return None
    directory = path if path.is_dir() else path.parent
    for candidate in (directory, *directory.parents):
        for kind, marker in (('git', '.git'), ('svn', '.svn')):
            if (candidate / marker).exists():
                # A .git file represents a worktree/submodule, not its parent's repo.
                return VcsLocation(kind, candidate)
    return None


def vcs_context(paths, focus, virtual=False):
    focus = vcs_absolute(focus)
    paths = tuple(dict.fromkeys(vcs_absolute(p) for p in paths)) or (focus,)
    if virtual:
        return VcsContext(None, focus, paths, 'Archive previews are not working copies.')
    try:
        location = vcs_location(focus)
        if location is None:
            return VcsContext(None, focus, paths, 'Not a Git or SVN working copy.')
        mixed = any(vcs_location(p) != location for p in paths)
        return VcsContext(location, focus, paths, mixed=mixed)
    except OSError:
        return VcsContext(None, focus, paths, 'Working copy is unavailable.')


def vcs_run(command):
    env = os.environ.copy()
    # Local status must never open a terminal/authentication dialog or update the index.
    env.update(GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')
    result = subprocess.run(command, capture_output=True, timeout=4, env=env,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('VCS status unavailable')
    return result.stdout


def vcs_cli(kind):
    if os.name == 'nt':
        # Windows executable lookup otherwise searches the current working directory.
        # Merely selecting a repository must not execute its own git.exe/svn.exe.
        found = next((result for entry in os.environ.get('PATH', '').split(os.pathsep)
                      if entry and Path(entry).is_absolute()
                      for result in [shutil.which(str(Path(entry) / (kind + '.exe')))] if result), None)
    else:
        found = shutil.which(kind)
    if found:
        return found
    if os.name == 'nt':
        for variable in ('ProgramFiles', 'ProgramFiles(x86)'):
            base = os.environ.get(variable)
            if base:
                relative = 'Git/cmd/git.exe' if kind == 'git' else 'TortoiseSVN/bin/svn.exe'
                candidate = Path(base) / relative
                if candidate.is_file():
                    return str(candidate)
    return None


def vcs_parse_git_status(data):
    values = dict(changed=0, untracked=0, conflicts=0, branch='', upstream='',
                  ahead=None, behind=None)
    records = iter(data.split(b'\0'))
    for record in records:
        if record.startswith(b'# branch.head '):
            values['branch'] = record[14:].decode('utf-8', 'replace')
        elif record.startswith(b'# branch.upstream '):
            values['upstream'] = record[18:].decode('utf-8', 'replace')
        elif record.startswith(b'# branch.ab '):
            counts = record[12:].split()
            values['ahead'], values['behind'] = int(counts[0]), abs(int(counts[1]))
        elif record.startswith(b'? '):
            values['untracked'] += 1
        elif record.startswith(b'u '):
            values['conflicts'] += 1
        elif record.startswith((b'1 ', b'2 ')):
            values['changed'] += 1
            if record.startswith(b'2 '):
                next(records, None)  # second path can contain arbitrary characters
    return VcsSummary(**values)


def vcs_status(context):
    if context.location is None:
        return VcsSummary(error=context.reason)
    if context.mixed:
        return VcsSummary(error='Selection spans working copies. Select items from one working copy.')
    kind, root = context.location.kind, context.location.root
    executable = vcs_cli(kind)
    if executable is None:
        return VcsSummary(error='Command-line client not found. Tortoise dialogs are still available.')
    try:
        if kind == 'git':
            command = [executable, '--no-optional-locks', '--literal-pathspecs', '-c', 'core.fsmonitor=false', '-C', str(root),
                       'status', '--porcelain=v2', '--branch', '-z', '--untracked-files=normal', '--']
            command.extend(os.path.relpath(p, root) for p in context.paths)
            return vcs_parse_git_status(vcs_run(command))
        # status/info without -u are local-only; @ disambiguates literal peg characters.
        targets = [str(p) + '@' for p in context.paths]
        document = ET.fromstring(vcs_run([executable, 'status', '--xml', '--non-interactive',
                                         '--ignore-externals', '--', *targets]))
        changed = untracked = conflicts = 0
        seen = set()
        for entry in document.findall('.//entry'):
            path = entry.get('path')
            if path in seen:
                continue
            seen.add(path)
            wc = entry.find('wc-status')
            if wc is None:
                continue
            item, props = wc.get('item'), wc.get('props')
            if item == 'conflicted' or props == 'conflicted' or wc.get('tree-conflicted') == 'true':
                conflicts += 1
            elif item == 'unversioned':
                untracked += 1
            elif item in {'modified', 'added', 'deleted', 'missing', 'replaced', 'obstructed', 'incomplete'} or props == 'modified':
                changed += 1
        # An untracked item has no info, but its nearest versioned parent does.
        url = ''
        for info_path in dict.fromkeys((context.focus, context.focus.parent, root)):
            if info_path != root and root not in info_path.parents:
                continue
            try:
                info = ET.fromstring(vcs_run([executable, 'info', '--xml', '--non-interactive',
                                             '--', str(info_path) + '@']))
                url = info.findtext('.//relative-url') or info.findtext('.//url') or ''
                break
            except ValueError:
                continue
        return VcsSummary(changed, untracked, conflicts, url=url)
    except (OSError, subprocess.SubprocessError, ValueError, ET.ParseError):
        return VcsSummary(error='Status unavailable or timed out. No changes were made.')


VCS_CLIENT_NAMES = {'git': 'TortoiseGitProc.exe', 'svn': 'TortoiseProc.exe'}


def vcs_find_client(kind, configured=''):
    name = VCS_CLIENT_NAMES[kind]
    candidates = [configured] if configured else []
    if os.name == 'nt':
        # Only known installation locations/explicit preferences, never the working repo.
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                    try:
                        product = 'TortoiseGit' if kind == 'git' else 'TortoiseSVN'
                        with winreg.OpenKey(hive, 'Software\\' + product, 0, winreg.KEY_READ | view) as key:
                            candidates.append(str(Path(winreg.QueryValueEx(key, 'Directory')[0]) / 'bin' / name))
                    except OSError:
                        pass
        except ImportError:
            pass
        for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
            base = os.environ.get(variable)
            if base:
                candidates.append(str(Path(base) / ('TortoiseGit' if kind == 'git' else 'TortoiseSVN') / 'bin' / name))
    for candidate in candidates:
        if candidate and Path(candidate).is_absolute() and Path(candidate).is_file() and Path(candidate).name.casefold() == name.casefold():
            return str(candidate)
    return None


def vcs_dialog_command(executable, context, action):
    if context.location is None:
        raise ValueError('Not a Git or SVN working copy.')
    if action not in {'commit', 'commit_all', 'push', 'log', 'revisiongraph'}:
        raise ValueError('Unsupported VCS action')
    if action in {'commit', 'commit_all', 'push'} and context.mixed:
        raise ValueError('Selection spans working copies. Select items from one working copy.')
    location = context.location
    if action == 'push' and location.kind != 'git':
        raise ValueError('SVN does not use Push')
    if action == 'commit':
        paths = context.paths
    elif action in {'commit_all', 'push'} or (action == 'revisiongraph' and location.kind == 'git'):
        paths = (location.root,)
    else:
        paths = (context.focus,)
    if any('*' in str(p) or '\0' in str(p) for p in paths):
        raise ValueError('Unsupported path characters')
    command = 'commit' if action == 'commit_all' else action
    arguments = [str(executable), '/command:' + command, '/path:' + '*'.join(map(str, paths))]
    if len(subprocess.list2cmdline(arguments).encode('utf-16-le')) > 60000:
        raise ValueError('Too many selected paths. Select fewer items or their parent folder.')
    return arguments
