"""One-shot interactive Windows test worker; no credentials/network/autologon.

Launched by an InteractiveToken scheduled task in the dedicated test account.
Reports are atomic and tied to one unpredictable request ID and exact file hashes.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import time
from contextlib import contextmanager

ALLOWED = {'cloud_overlay_check.py', 'folder_icon_check.py', 'ux_walkthrough_check.py', 'search_results_check.py', 'vcs_gui_check.py', 'architecture_check.py', 'reliability_check.py', 'tooltip_check.py', 'preview_tabs_check.py', 'settings_check.py',
           'folder_scroll_check.py', 'folder_navigation_check.py', 'folder_leaf_check.py', 'settings_readability_groups_check.py',
           'interaction_layout_check.py', 'compact_chrome_check.py', 'review_compare_check.py', 'control_scaling_check.py', 'render_formats_check.py', 'structure_search_check.py', 'render_reliability_check.py', 'markdown_reading_check.py', 'structure_matches_check.py', 'structure_wrap_check.py'}


def desktop_ready():
    if os.name != 'nt':
        return False
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.OpenInputDesktop.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    user.OpenInputDesktop.restype = W.HANDLE
    user.GetUserObjectInformationW.argtypes = [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD, ctypes.POINTER(W.DWORD)]
    user.CloseDesktop.argtypes = [W.HANDLE]
    desktop = user.OpenInputDesktop(0, False, 1)  # DESKTOP_READOBJECTS
    if not desktop:
        return False
    try:
        name = ctypes.create_unicode_buffer(256)
        length = W.DWORD()
        receives_input = W.BOOL()
        if not user.GetUserObjectInformationW(desktop, 6, ctypes.byref(receives_input),
                                              ctypes.sizeof(receives_input), ctypes.byref(length)) or not receives_input.value:
            return False
        return bool(user.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name),
                                                   ctypes.byref(length)) and name.value.casefold() == 'default')
    finally:
        user.CloseDesktop(desktop)


def atomic_report(path, record):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(record), encoding='utf-8')
    # Windows report readers/antivirus can briefly deny delete-sharing. Keep
    # the old complete report visible while retrying this one owned replace.
    for attempt in range(8):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt==7:raise
            time.sleep(min(.025*2**attempt,.2))


class DisplayUnavailable(OSError):
    pass


@contextmanager
def visible_test_display(set_state=None):
    """Keep only this verified interactive test's display awake, then restore.

    CPU/Tk activity alone does not reset Windows' display idle timer. Without
    this request a running test can capture an old DWM frame after monitor-off.
    No power-plan, login, networking or VM lifecycle setting is changed.
    """
    if set_state is None:
        set_state=ctypes.WinDLL('kernel32',use_last_error=True).SetThreadExecutionState
        set_state.argtypes=[W.DWORD];set_state.restype=W.DWORD
        # Some virtual display drivers do not repaint on an execution-state
        # request alone. A zero-distance move wakes the verified test desktop;
        # it clicks nothing and leaves the pointer location unchanged.
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.mouse_event.argtypes=[W.DWORD,W.DWORD,W.DWORD,W.DWORD,ctypes.c_size_t]
        user.mouse_event(0x0001,0,0,0,0)
    previous=set_state(0x80000002)  # ES_CONTINUOUS | ES_DISPLAY_REQUIRED
    if not previous:raise DisplayUnavailable('Cannot keep the validation display awake')
    try:yield
    finally:set_state(previous | 0x80000000)


def execute(request_path):
    request_path = Path(request_path).resolve()
    directory = request_path.parent
    request = json.loads(request_path.read_text(encoding='utf-8'))
    result = {'request_id': request['request_id'], 'status': 'starting', 'stage': 'desktop', 'tests': [],
              'environment': {'python': platform.python_version(), 'arch': platform.machine(),
                              'windows': platform.version()}}
    report = directory/'result.json'
    atomic_report(report, result)
    # No Tk application or PFC import before the actual input desktop is ready.
    if not desktop_ready():
        result.update(status='blocked', reason='interactive-desktop-unavailable')
        atomic_report(report, result)
        return 2
    for name, expected in request['files'].items():
        if Path(name).name != name or not name.endswith('.py'):
            raise ValueError('Invalid artifact name')
        if hashlib.sha256((directory/name).read_bytes()).hexdigest() != expected:
            result.update(status='blocked', stage='artifact', reason='hash-mismatch')
            atomic_report(report, result)
            return 2
    if any(name not in ALLOWED for name in request['checks']):
        raise ValueError('Unknown check')
    try:
        with visible_test_display():
            return run_checks(directory,request,result,report)
    except DisplayUnavailable:
        result.update(status='blocked',stage='desktop',reason='display-request-unavailable')
        atomic_report(report,result)
        return 2
    except OSError:
        result.update(status='blocked',stage='worker-io',reason='worker-file-io-unavailable')
        atomic_report(report,result)
        return 2


def run_checks(directory,request,result,report):
    result.update(status='running', stage='tests')
    atomic_report(report, result)
    for name in request['checks']:
        if not desktop_ready():
            result.update(status='blocked', stage='desktop', reason='desktop-became-unavailable')
            break
        started = time.monotonic()
        with (directory/(name+'.log')).open('wb') as output:
            process = subprocess.Popen([sys.executable, str(directory/name), 'pfc'],
                                       cwd=directory, stdout=output, stderr=subprocess.STDOUT)
            try:
                while process.poll() is None:
                    if not desktop_ready():
                        result.update(status='blocked', stage='desktop', reason='desktop-became-unavailable')
                        raise subprocess.TimeoutExpired(name, 0)
                    if time.monotonic()-started > request.get('test_timeout', 180):
                        raise subprocess.TimeoutExpired(name, request.get('test_timeout', 180))
                    time.sleep(.2)
                code = process.returncode
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                process.wait(timeout=10)
                code = -1
        result['tests'].append({'check': name, 'exit_code': code,
                                'seconds': round(time.monotonic()-started, 3)})
        atomic_report(report, result)
        if code:
            if result['status'] != 'blocked':
                result.update(status='failed', stage='tests')
            break
    else:
        result.update(status='passed', stage='tests')
    atomic_report(report, result)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(execute(sys.argv[1]))
