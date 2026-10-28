"""Bounded automatic errors with recent context; never log document content."""
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import traceback
import uuid
import threading
import sys
import warnings
from .nativecrash import NativeCrashCapture


def diagnostic_records(*snapshots):
    """Merge bounded JSONL tails, ignoring partial lines and duplicate records."""
    rows, seen = [], set()
    for snapshot in snapshots:
        for line in snapshot.splitlines():
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or not isinstance(row.get('event'), str):
                    continue
                key = json.dumps(row, sort_keys=True, ensure_ascii=True)
            except (ValueError, TypeError):
                continue
            if key not in seen:
                rows.append(row); seen.add(key)
    return sorted(rows, key=lambda row: str(row.get('utc_time') or row.get('time') or ''))


def diagnostic_incidents(*snapshots):
    """Fold propagation of the SAME exception, never merely similar failures."""
    result, groups = [], {}
    for row in diagnostic_records(*snapshots):
        key=(row.get('session'),row.get('incident'))
        if not key[1]:
            result.append(row); continue
        if key not in groups:
            row=dict(row,events=[row['event']]);groups[key]=row;result.append(row)
        else:
            first=groups[key]
            if row['event'] not in first['events']:first['events'].append(row['event'])
            if len(row.get('frames',[]))>len(first.get('frames',[])):first['frames']=row['frames']
    return result


def diagnostic_summary(row):
    """Photo-first card: root location before caller chain, no raw values/locals."""
    lines=['PFC '+str(row.get('version','—'))+' · '+str(row.get('severity','—'))+
           ' · '+str(row.get('error') or row.get('event','—')),
           str(row.get('time','—'))]
    frames=row.get('frames',[])
    if frames:
        root=frames[-1]
        label='Python stack: ' if row.get('event')=='process.native_crash' else 'Location: '
        lines.append(label+str(root.get('module','?'))+':'+str(root.get('line','?'))+' · '+str(root.get('function','?')))
    if row.get('reason'):lines.append(str(row['reason']))
    if row.get('native_code'):lines[0]+=' · '+str(row['native_code'])
    runtime=row.get('runtime',{})
    if runtime:
        lines.append('Runtime: '+' · '.join(str(runtime[k]) for k in ('python','platform','machine','tk') if k in runtime))
    if frames:
        for frame in reversed(frames[-3:-1]):
            lines.append('  '+str(frame.get('module','?'))+':'+str(frame.get('line','?'))+' · '+str(frame.get('function','?')))
    events=row.get('events',[])
    lines.append(('Same incident: '+' → '.join(events)) if len(events)>1 else 'Event: '+str(row.get('event','—')))
    lines.append('Incident: '+str(row.get('incident','—')))
    return '\n'.join(lines)


class DiagnosticLog:
    def __init__(self, version, directory=None, automatic=False, runtime=None):
        base = Path(os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')
        self.path = Path(directory or base/'PFC'/'logs')/'pfc-debug.jsonl'
        self.version, self.session = version, uuid.uuid4().hex[:12]
        self.runtime=dict(runtime or {})
        self.handler = None
        self.error = None
        self.error_path = self.path.with_name('pfc-errors.jsonl')
        self.error_handler = None
        self._lock = threading.RLock()
        self._recent = deque(maxlen=64)
        self._hooks = []
        self._logging_handler = None
        self._native_capture = None
        if automatic:
            try:
                self.error_path.parent.mkdir(parents=True, exist_ok=True)
                self.error_handler = RotatingFileHandler(self.error_path, maxBytes=1024*1024,
                                                         backupCount=2, encoding='utf-8')
                self.event('session.started', severity='INFO', automatic=True,
                           python=platform.python_version(), platform=platform.system())
            except OSError:
                self.error = 'automatic-log-unavailable'

    def install_hooks(self):
        """Observe unhandled failures/warnings, preserving normal Python handling."""
        if self._hooks or self._logging_handler: return
        old_sys, old_thread, old_warning = sys.excepthook, threading.excepthook, warnings.showwarning
        def system(kind, exc, tb):
            self.exception('python.unhandled', exc.with_traceback(tb))
            old_sys(kind, exc, tb)
        def thread(args):
            if not isinstance(args.exc_value,SystemExit):
                self.exception('thread.unhandled', args.exc_value.with_traceback(args.exc_traceback))
            old_thread(args)
        def warning(message, category, filename, lineno, file=None, line=None):
            self.event('python.warning', severity='WARNING', category=category.__name__,
                       module=Path(filename).name, line=lineno)
            old_warning(message, category, filename, lineno, file, line)
        for obj, name, new, old in ((sys,'excepthook',system,old_sys),
                (threading,'excepthook',thread,old_thread), (warnings,'showwarning',warning,old_warning)):
            setattr(obj,name,new); self._hooks.append((obj,name,new,old))
        owner = self
        class ErrorHandler(logging.Handler):
            def emit(self, record):
                if record.exc_info and record.exc_info[1]:
                    owner.exception('logging.exception', record.exc_info[1])
                else:
                    owner.event('logging.warning', severity=record.levelname,
                                logger=record.name, module=record.module, line=record.lineno)
        self._logging_handler = ErrorHandler(logging.WARNING)
        logging.getLogger().addHandler(self._logging_handler)
        if self.error_handler:
            self._native_capture = NativeCrashCapture(self.path.parent, self.version, self.session,
                                                     self.runtime, self._recover_native_record)
            issue = self._native_capture.start()
            if issue:
                self.event('diagnostics.native_capture.unavailable', severity='WARNING', reason=issue)

    def _recover_native_record(self, record):
        # Retain the CRASH version/session/time, not the recovering executable's.
        with self._lock:
            if not self.error_handler:
                return False
            return self._write(self.error_handler, json.dumps(record, ensure_ascii=True))

    def close(self):
        if self._native_capture:
            self._native_capture.close()
            self._native_capture = None
        for obj,name,new,old in reversed(self._hooks):
            if getattr(obj,name) is new: setattr(obj,name,old)
        self._hooks.clear()
        if self._logging_handler:
            logging.getLogger().removeHandler(self._logging_handler)
            self._logging_handler = None
        with self._lock:
            for handler in (self.handler,self.error_handler):
                if handler: handler.close()
            self.handler = self.error_handler = None

    def set_enabled(self, enabled):
        with self._lock:
            return self._set_enabled(enabled)

    def _set_enabled(self, enabled):
        if not enabled:
            self.event('debug.disabled')
            if self.handler: self.handler.close()
            self.handler = None
            return True
        if self.handler: return True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handler = RotatingFileHandler(self.path, maxBytes=1024*1024, backupCount=2, encoding='utf-8')
            self.handler.setFormatter(logging.Formatter('%(message)s'))
            self.error = None
            self.event('debug.enabled', python=platform.python_version(), platform=platform.system(), version=self.version)
            return True
        except OSError as exc:
            self.error = type(exc).__name__
            self.handler = None
            return False

    def event(self, event, severity='INFO', automatic=False, **metadata):
        with self._lock:
            handlers = [h for h in (self.handler, self.error_handler
                        if automatic or severity in ('WARNING','ERROR','CRITICAL') else None) if h]
            if not handlers and self.error_handler is None: return
            metadata.update(time=datetime.now().astimezone().isoformat(),
                            utc_time=datetime.now(timezone.utc).isoformat(), version=self.version,
                            session=self.session, event=event, severity=severity)
            serious = severity in ('WARNING','ERROR','CRITICAL')
            if serious and self.error_handler and self._recent:
                metadata['context'] = [json.loads(record) for record in self._recent]
            try:
                payload = json.dumps(metadata, ensure_ascii=True)
            except (TypeError, ValueError):
                self.error = 'diagnostic-metadata-invalid'
                return
            for handler in handlers: self._write(handler, payload)
            # No normal-operation disk stream: keep a bounded, detached snapshot
            # for the next failure, without recursively buffering old contexts.
            metadata.pop('context',None)
            if serious:
                self._recent.clear()
            elif self.error_handler:
                recent=json.dumps(metadata,ensure_ascii=True)
                if len(recent)<=1024:self._recent.append(recent)

    def _write(self, handler, payload):
        try:
            # Write directly: logging.handleError can leak raw exception text
            # to stderr; diagnostic I/O failure must not interrupt Preview.
            if handler.shouldRollover(logging.makeLogRecord({'msg':payload})):
                handler.doRollover()
            handler.stream.write(payload+'\n'); handler.flush()
            return True
        except (OSError, ValueError):
            self.error = 'diagnostic-write-failed'
            return False

    def file(self, event, path, **metadata):
        if self.handler is None and self.error_handler is None: return
        path = Path(path)
        # Match events for one file without exposing personal paths/names.
        metadata.update(file_id=hashlib.sha256(os.fsencode(os.path.abspath(path))).hexdigest()[:16],
                        suffix=path.suffix.lower()[:16])
        try:
            stat = path.stat(); metadata.update(bytes=stat.st_size, modified_ns=stat.st_mtime_ns)
        except OSError as exc: metadata['stat_error'] = type(exc).__name__
        self.event(event, **metadata)

    def exception(self, event, exc, severity='ERROR'):
        frames = [dict(module=Path(f.filename).name, line=f.lineno, function=f.name)
                  for f in traceback.extract_tb(exc.__traceback__)[-16:]]
        # An exception object survives re-raise through page/window/request.
        # IDs distinguish independent identical failures and preserve audit rows.
        with self._lock:
            ids=getattr(exc,'_pfc_diagnostic_incidents',{})
            incident=ids.get(self.session)
            if not incident:
                incident=uuid.uuid4().hex[:12]
                try:
                    exc._pfc_diagnostic_incidents={**ids,self.session:incident}
                except (AttributeError,TypeError):pass
        runtime=dict(python=platform.python_version(),platform=platform.system(),machine=platform.machine())
        tkmodule=sys.modules.get('tkinter')
        if tkmodule is not None:runtime['tk']='Tk '+str(tkmodule.TkVersion)
        runtime.update(self.runtime)
        data = dict(error=type(exc).__name__, frames=frames, incident=incident,runtime=runtime)
        # Allow only an exact known interpreter message, never arbitrary text
        # (which may contain paths, source lines or NDA document values).
        if isinstance(exc,TypeError) and exc.args == ("int() argument must be a string, a bytes-like object or a real number, not '_tkinter.Tcl_Obj'",):
            data['reason']='Geometry: int() received a Tcl pixel object.'
        if isinstance(exc, OSError): data.update(errno=exc.errno, winerror=getattr(exc,'winerror',None))
        if isinstance(exc, NameError) and getattr(exc,'name',None): data['name'] = exc.name
        self.event(event, severity=severity, **data)

    def snapshot(self, automatic=False):
        path = self.error_path if automatic else self.path
        if not path.exists(): return ''
        with self._lock, path.open('rb') as stream:
            start=max(0, os.fstat(stream.fileno()).st_size-128*1024)
            stream.seek(max(0,start-1))
            if start and stream.read(1)!=b'\n':stream.readline()
            return stream.read(128*1024).decode('utf-8', errors='replace')

    def clear(self):
        """Clear both diagnostic streams and their two owned rotation files.

        Keep handlers open so ongoing diagnostics continue after truncation.
        Failures are reported to the caller, never presented as a successful clear.
        """
        with self._lock:
            try:
                for path in (self.path, self.error_path):
                    handler = self.handler if path == self.path else self.error_handler
                    if handler and handler.stream:
                        handler.flush()
                        handler.stream.seek(0); handler.stream.truncate(); handler.flush()
                    elif path.exists():
                        with path.open('wb'):
                            pass
                    for suffix in ('.1', '.2'):
                        path.with_name(path.name+suffix).unlink(missing_ok=True)
            except (OSError, ValueError):
                self.error = 'diagnostic-clear-failed'
                return False
            self._recent.clear()
            self.event('logs.cleared', automatic=True)
            return True
