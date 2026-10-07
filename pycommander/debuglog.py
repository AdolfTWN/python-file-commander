"""Opt-in local diagnostics: metadata only, bounded files, no document content."""
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


class DiagnosticLog:
    def __init__(self, version, directory=None):
        base = Path(os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')
        self.path = Path(directory or base/'PFC'/'logs')/'pfc-debug.jsonl'
        self.version, self.session = version, uuid.uuid4().hex[:12]
        self.handler = None
        self.error = None

    def set_enabled(self, enabled):
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

    def event(self, event, **metadata):
        if self.handler is None: return
        try:
            payload = json.dumps(dict(time=datetime.now(timezone.utc).isoformat(), session=self.session,
                                      event=event, **metadata), ensure_ascii=True)
            # Write directly: logging.handleError can leak raw exception text
            # to stderr; diagnostic I/O failure must not interrupt Preview.
            if self.handler.shouldRollover(logging.makeLogRecord({'msg':payload})):
                self.handler.doRollover()
            self.handler.stream.write(payload+'\n'); self.handler.flush()
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

    def exception(self, event, exc):
        frames = [dict(module=Path(f.filename).name, line=f.lineno, function=f.name)
                  for f in traceback.extract_tb(exc.__traceback__)[-16:]]
        data = dict(error=type(exc).__name__, frames=frames)
        if isinstance(exc, OSError): data.update(errno=exc.errno, winerror=getattr(exc,'winerror',None))
        if isinstance(exc, NameError) and getattr(exc,'name',None): data['name'] = exc.name
        self.event(event, **data)

    def snapshot(self):
        if not self.path.exists(): return ''
        with self.path.open('rb') as stream:
            stream.seek(max(0, self.path.stat().st_size-128*1024))
            return stream.read(128*1024).decode('utf-8', errors='replace')
