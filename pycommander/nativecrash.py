"""Crash-safe native stacks, recovered as private structured incidents on restart.

The fatal handler only writes to an already-open descriptor: no Python logging,
Tk calls, allocation of crash metadata, or locks run in a corrupted process.
"""
from datetime import datetime, timezone
import faulthandler
import json
import os
from pathlib import Path
import platform
import re


def _native_journal_lock(stream):
    """Nonblocking lifetime lock: never recover another running PFC's journal."""
    stream.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def native_crash_record(header, dump, timestamp):
    """Allowlisted classification and basename-only frames, never source/locals."""
    kinds = (
        ('Windows fatal exception: access violation', 'NativeAccessViolation', '0xC0000005'),
        ('Windows fatal exception: stack overflow', 'NativeStackOverflow', '0xC00000FD'),
        ('Windows fatal exception:', 'NativeWindowsException', None),
        ('Fatal Python error: Segmentation fault', 'NativeSegmentationFault', None),
        ('Fatal Python error: Aborted', 'NativeAbort', None),
        ('Fatal Python error: Bus error', 'NativeBusError', None),
        ('Fatal Python error: Illegal instruction', 'NativeIllegalInstruction', None),
        ('Fatal Python error:', 'NativeFatalError', None),
    )
    kind = next(((name, code) for marker, name, code in kinds if marker in dump), None)
    if kind is None:
        return None  # clean exit / force-kill / a timeout dump is NOT a native crash
    # A previous watchdog dump may precede the fatal event in the same stream.
    dump = dump[min(dump.index(marker) for marker, _, _ in kinds if marker in dump):]
    frames = []
    # faulthandler lists the faulting/current thread first, innermost frame first.
    # Keep its first bounded Python stack; this is context, NOT proof that the
    # crash occurred in that Python frame (the fatal thread may be native-only).
    for line in dump.splitlines():
        match = re.fullmatch(r'  File "([^"]+)", line (\d+) in ([\w<>. -]+)', line)
        if match:
            frames.append(dict(module=match[1].replace('\\', '/').rsplit('/', 1)[-1][:100],
                               line=int(match[2]), function=match[3][:100]))
            if len(frames) == 16:
                break
        elif frames:
            break
    moment = datetime.fromtimestamp(timestamp, timezone.utc)
    record = dict(event='process.native_crash', severity='CRITICAL', error=kind[0],
                  time=moment.astimezone().isoformat(), utc_time=moment.isoformat(),
                  version=header['version'], session=header['session'],
                  incident='native-' + header['session'], frames=list(reversed(frames)),
                  runtime=header.get('runtime', {}), started_at=header.get('started_at'),
                  recovered_at=datetime.now().astimezone().isoformat(),
                  crash_time_source='journal_mtime',
                  reason='Native process crash; recovered on next start. Time is the last crash-journal write.')
    if kind[1]:
        record['native_code'] = kind[1]
    elif kind[0] == 'NativeWindowsException':
        code = re.search(r'Windows fatal exception: code (0x[0-9a-fA-F]{8})\b', dump)
        if code:
            record['native_code'] = '0x' + code[1][2:].upper()
    return record


class NativeCrashCapture:
    """Own one fatal-handler descriptor; no global watchdog or per-operation I/O."""
    def __init__(self, directory, version, session, runtime, write_record):
        self.directory = Path(directory)
        self.path = self.directory / ('pfc-native-' + session + '.log')
        self.stream = None
        self.enabled = False
        self.write_record = write_record
        self.header = dict(version=version, session=session,
                           started_at=datetime.now().astimezone().isoformat(),
                           runtime=dict(python=platform.python_version(),
                                        platform=platform.system(), machine=platform.machine(), **{
                                            k: v for k, v in runtime.items()
                                            if k not in ('python', 'platform', 'machine')}))

    def recover(self):
        try:
            paths = list(self.directory.glob('pfc-native-*.log'))
        except OSError:
            return
        for path in paths:
            try:
                if path == self.path or path.is_symlink():
                    continue
                with path.open('r+b', buffering=0) as stream:
                    _native_journal_lock(stream)
                    stream.seek(0)
                    header = json.loads(stream.readline(8192))
                    if not (isinstance(header, dict) and
                            isinstance(header.get('version'), str) and
                            re.fullmatch(r'[a-f0-9]{12}', header.get('session', ''))):
                        continue
                    dump = stream.read(2 * 1024 * 1024).decode('utf-8', errors='replace')
                    record = native_crash_record(header, dump, os.fstat(stream.fileno()).st_mtime)
                    # A failed append retains the journal for a future start.
                    if record and not self.write_record(record):
                        continue
                path.unlink()
            except (OSError, ValueError, TypeError):
                continue  # unavailable/live/corrupt journal must not break startup

    def start(self):
        self.recover()
        if faulthandler.is_enabled():
            return 'native-handler-already-installed'
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.stream = open(self.path, 'x+b', buffering=0,
                               opener=lambda name, flags: os.open(name, flags, 0o600))
            _native_journal_lock(self.stream)
            self.stream.write((json.dumps(self.header, ensure_ascii=True) + '\n').encode('utf-8'))
            self.stream.flush()
            faulthandler.enable(file=self.stream, all_threads=True)
            self.enabled = True
            return None
        except (OSError, ValueError, RuntimeError):
            self.close()
            return 'native-crash-log-unavailable'

    def close(self):
        if self.enabled:
            faulthandler.disable()
            self.enabled = False
        if self.stream:
            self.stream.close()
            self.stream = None
            try:
                self.path.unlink()
            except OSError:
                pass
