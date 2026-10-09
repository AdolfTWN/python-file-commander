"""Bounded automatic errors and opt-in diagnostics; never log document content."""
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


class DiagnosticLog:
    def __init__(self, version, directory=None, automatic=False):
        base = Path(os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')
        self.path = Path(directory or base/'PFC'/'logs')/'pfc-debug.jsonl'
        self.version, self.session = version, uuid.uuid4().hex[:12]
        self.handler = None
        self.error = None
        self.error_path = self.path.with_name('pfc-errors.jsonl')
        self.error_handler = None
        self._lock = threading.RLock()
        self._hooks = []
        self._logging_handler = None
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

    def close(self):
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
            if not handlers: return
            metadata.update(time=datetime.now().astimezone().isoformat(),
                            utc_time=datetime.now(timezone.utc).isoformat(), version=self.version,
                            session=self.session, event=event, severity=severity)
            try:
                payload = json.dumps(metadata, ensure_ascii=True)
            except (TypeError, ValueError):
                self.error = 'diagnostic-metadata-invalid'
                return
            for handler in handlers: self._write(handler, payload)

    def _write(self, handler, payload):
        try:
            # Write directly: logging.handleError can leak raw exception text
            # to stderr; diagnostic I/O failure must not interrupt Preview.
            if handler.shouldRollover(logging.makeLogRecord({'msg':payload})):
                handler.doRollover()
            handler.stream.write(payload+'\n'); handler.flush()
        except (OSError, ValueError):
            self.error = 'diagnostic-write-failed'

    def file(self, event, path, **metadata):
        if self.handler is None: return
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
        data = dict(error=type(exc).__name__, frames=frames)
        if isinstance(exc, OSError): data.update(errno=exc.errno, winerror=getattr(exc,'winerror',None))
        if isinstance(exc, NameError) and getattr(exc,'name',None): data['name'] = exc.name
        self.event(event, severity=severity, **data)

    def snapshot(self, automatic=False):
        path = self.error_path if automatic else self.path
        if not path.exists(): return ''
        with self._lock, path.open('rb') as stream:
            stream.seek(max(0, os.fstat(stream.fileno()).st_size-128*1024))
            return stream.read(128*1024).decode('utf-8', errors='replace')
