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

ALLOWED = {'tooltip_check.py', 'preview_tabs_check.py', 'settings_check.py',
           'folder_scroll_check.py', 'folder_navigation_check.py'}


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
    tmp.replace(path)


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
