"""Bounded UI stall watchdog and folder-operation timing; no Tk on the worker."""
from functools import wraps
from itertools import count
import os
from pathlib import Path
import queue
import sys
import threading
import time
import uuid


_LATENCY_FILE_TYPES = frozenset(
    '.lnk .url .ico .exe .dll .zip .7z .rar .pdf .doc .docx .xls .xlsx .ppt .pptx '
    '.md .txt .json .csv .html .svg .png .jpg .jpeg .mp4 .reg .py'.split())


def _latency_file_type(item, is_dir):
    if item is None:
        return None
    if is_dir:
        return 'folder'
    suffix = item.suffix.casefold()
    return suffix if suffix in _LATENCY_FILE_TYPES else 'other entry'


class UiLatencyMonitor:
    """One UI producer, one independent writer. Fast operations never write logs."""

    def __init__(self, log, *, stall=5., total=3., phase=1., sample=.1, repeats=5,
                 poll=.5, cooldown=60.):
        self._log = log
        self._stall, self._total, self._phase = stall, total, phase
        self._sample, self._repeats, self._poll, self._cooldown = sample, repeats, poll, cooldown
        self._ui_thread = threading.get_ident()
        self._timing_local = threading.local()
        self._ui_active = None
        self._beat = time.monotonic()
        self._active = None
        self._sequence = count(1)
        self._last_slow = {}
        self._records = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self._source = Path(__file__).absolute()
        self._thread = threading.Thread(target=self._watch, name='PFC-UI-watchdog', daemon=True)
        self._thread.start()

    @property
    def _active(self):
        return getattr(self._timing_local, 'active', None)

    @_active.setter
    def _active(self, value):
        self._timing_local.active = value
        if threading.get_ident() == self._ui_thread:
            self._ui_active = value

    def heartbeat(self):
        self._beat = time.monotonic()

    def close(self):
        self._stop.set()
        self._enqueue(None, None)

    def _enqueue(self, event, data):
        try:
            self._records.put_nowait((event, data))
        except queue.Full:
            pass

    def action(self, action, callback, *args, **kwargs):
        if self._active is not None or self._stop.is_set():
            return callback(*args, **kwargs)
        started = time.monotonic()
        # Keep stats local to this UI operation. The worker reads the current
        # phase snapshot only, never the stats dictionary or Tk objects.
        operation = {'action':action, 'stats':{}, 'incident':f'ui-{next(self._sequence):x}',
                     'watched':False, 'user_wait':0.}
        self._active = (operation, None)
        try:
            return callback(*args, **kwargs)
        finally:
            self._active = None
            elapsed = max(0., time.monotonic()-started-operation['user_wait'])
            self._completed(operation, elapsed)

    def measure(self, name, callback, *args, item=None, is_dir=False, **kwargs):
        active = self._active
        if active is None:
            return callback(*args, **kwargs)
        operation, parent = active
        started = time.monotonic()
        current = [name, started, item, is_dir, 0.]
        self._active = (operation, current)
        try:
            return callback(*args, **kwargs)
        finally:
            elapsed = time.monotonic()-started
            self._active = active
            if parent is not None:
                parent[4] += elapsed
            own = max(0., elapsed-current[4])
            stats = operation['stats'].get(name)
            if stats is None:
                stats = operation['stats'][name] = [0., 0, 0, 0., None]
            stats[0] += own
            stats[1] += 1
            if own >= self._sample:
                stats[2] += 1
            if own > stats[3]:
                stats[3] = own
                stats[4] = _latency_file_type(item, is_dir) if own >= self._sample else None

    def rows(self, count):
        if self._active is not None:
            self._active[0]['rows'] = count

    def _completed(self, operation, elapsed):
        stats = operation['stats']
        if not operation['watched'] and elapsed < min(self._total, self._phase, self._sample*self._repeats):
            return
        ranked = sorted(stats, key=lambda key: stats[key][0], reverse=True)
        slow = [name for name in ranked if stats[name][0] >= self._phase
                or stats[name][2] >= self._repeats]
        if not (operation['watched'] or elapsed >= self._total or slow
                or sum(value[2] for value in stats.values()) >= self._repeats):
            return
        key = (operation['action'], (slow or ranked or [None])[0])
        now = time.monotonic()
        if not operation['watched'] and now-self._last_slow.get(key, float('-inf')) < self._cooldown:
            return
        # Action/phase identifiers are fixed application strings.
        self._last_slow[key] = now
        phases = []
        for name in (slow + [name for name in ranked if name not in slow])[:4]:
            total, calls, delayed, longest, file_type = stats[name]
            value = dict(phase=name, elapsed_ms=round(total*1000), calls=calls,
                         slow_calls=delayed, longest_ms=round(longest*1000))
            if file_type:
                value['file_type'] = file_type
            phases.append(value)
        data = dict(action=operation['action'], duration_ms=round(elapsed*1000), phases=phases)
        other = elapsed-sum(stats[name][0] for name in ranked)
        if other >= self._phase:
            data['other_ui_ms'] = round(other*1000)
        if 'rows' in operation:
            data['rows'] = operation['rows']
        self._enqueue('ui.operation.slow', (operation['incident'], data, []))

    def _stack(self):
        # Do not use traceback/linecache: don't read source, locals, arguments,
        # document paths or arbitrary code outside PFC.
        frame = sys._current_frames().get(self._ui_thread)
        frames = []
        for _ in range(48):
            if frame is None:
                break
            code = frame.f_code
            if code is latency_user_wait.__code__ or (
                    code.co_name == 'show' and frame.f_globals.get('__name__') == 'tkinter.commondialog'):
                return None  # OS modal dialogs wait for the user, not I/O.
            path = Path(code.co_filename)
            if len(frames) < 6 and (path == self._source or (
                    self._source.name == 'latency.py' and path.parent == self._source.parent)):
                if code.co_name not in {'measure', 'action', 'wrapped', 'latency_call'}:
                    frames.append(dict(module='pfc.py' if path == self._source and not __package__
                                       else path.name, line=frame.f_lineno, function=code.co_name))
            frame = frame.f_back
        return list(reversed(frames))

    def _emit(self, event, record):
        incident, data, frames = record
        self._log.event(event, severity='WARNING', include_context=False, incident=incident,
                        latency=data, **({'frames':frames} if frames else {}))

    def _watch(self):
        reported = None
        previous = floor = time.monotonic()
        while not self._stop.is_set():
            try:
                event, record = self._records.get(timeout=self._poll)
                if event is not None and not self._stop.is_set():
                    self._emit(event, record)
            except queue.Empty:
                pass
            if self._stop.is_set():
                return
            now, beat = time.monotonic(), self._beat
            if reported and beat > reported[0]:
                old, incident = reported
                self._emit('ui.stall.recovered', (incident, {'resumed_ms':round((beat-old)*1000)}, []))
                reported = None
            # If the worker itself was not scheduled (e.g. system suspended),
            # don't count that entire gap as evidence of a Tk-only stall.
            if now-previous >= self._stall:
                floor = now
            previous = now
            since = max(beat, floor)
            if reported or now-since < self._stall:
                continue
            frames = self._stack()
            if frames is None:
                floor = now
                continue
            data = {'stalled_ms':round((now-since)*1000)}
            active = self._ui_active
            incident = uuid.uuid4().hex[:12]
            if active is not None:
                operation, phase = active
                incident = operation['incident']
                operation['watched'] = True
                data['action'] = operation['action']
                if phase is not None:
                    name, started, item, is_dir, _ = phase
                    data.update(pending_phase=name, pending_ms=round((now-started)*1000))
                    file_type = _latency_file_type(item, is_dir)
                    if file_type:
                        data['pending_type'] = file_type
            reported = (beat, incident)
            self._emit('ui.stall.detected', (incident, data, frames))


def latency_action(name):
    """Wrap a Tk callback without touching Tk or changing its return contract."""
    def decorate(callback):
        @wraps(callback)
        def wrapped(owner, *args, **kwargs):
            monitor = getattr(owner, '_ui_latency', None)
            if monitor is None:
                return callback(owner, *args, **kwargs)
            return monitor.action(name, callback, owner, *args, **kwargs)
        return wrapped
    return decorate


def latency_call(monitor, name, callback, *args, item=None, is_dir=False, **kwargs):
    if monitor is None:
        return callback(*args, **kwargs)
    return monitor.measure(name, callback, *args, item=item, is_dir=is_dir, **kwargs)


def latency_user_wait(monitor, callback, *args, **kwargs):
    """Exclude an intentional modal wait without excluding its preparation."""
    return _latency_wait(monitor, callback, *args, **kwargs)


def latency_responsive_wait(monitor, callback, *args, **kwargs):
    """Pause outer timing while Tk processes events; do not mask nested stalls."""
    return _latency_wait(monitor, callback, *args, **kwargs)


def _latency_wait(monitor, callback, *args, **kwargs):
    active = monitor._active if monitor is not None else None
    if active is None:
        return callback(*args, **kwargs)
    started = time.monotonic()
    monitor._active = None
    try:
        return callback(*args, **kwargs)
    finally:
        elapsed = time.monotonic()-started
        operation, phase = active
        operation['user_wait'] += elapsed
        if phase is not None:
            phase[4] += elapsed
        monitor._active = active
