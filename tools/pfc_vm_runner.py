"""Lease-aware Windows regression entry point. No VNC typing or password reads.

The VM must already have a usable interactive PFC-Test session. A locked/missing
desktop or broken QGA execution is a blocked environment, never a passing test.
"""
from __future__ import annotations
import argparse
import base64
import importlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid
from xml.sax.saxutils import escape

from pfc_workflow import ROOT, Store, digest
from pfc_windows_worker import ALLOWED

MANAGER = Path('/srv/yoder-ai/vm-management')
PYTHON = r'C:\PFC-Test\Python313\python.exe'
SCHTASKS = r'C:\Windows\System32\schtasks.exe'


class Blocked(RuntimeError):
    pass


class Guest:
    def __init__(self, lease, spec, leases):
        self.lease, self.spec, self.leases = lease, spec, leases

    def assert_owner(self):
        active = self.leases.snapshot()['vms'][self.spec.vm_id]['active']
        if not active or active['lease_id'] != self.lease['lease_id']:
            raise Blocked('lease-lost')

    def call(self, execute, **arguments):
        self.assert_owner()  # every guest read/write/exec, not just entry
        request = {'execute': execute, 'arguments': arguments}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.connect(str(self.spec.qga_socket))
            client.sendall((json.dumps(request)+'\n').encode())
            data = b''
            while b'\n' not in data:
                chunk = client.recv(65536)
                if not chunk or len(data) > 2*1024*1024:
                    raise Blocked('qga-invalid-response')
                data += chunk
        result = json.loads(data.split(b'\n', 1)[0])
        if 'error' in result:
            raise Blocked(execute+'-unavailable')
        return result.get('return', {})

    def execute(self, path, args, timeout=20):
        pid = self.call('guest-exec', path=path, arg=args, **{'capture-output': True})['pid']
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            result = self.call('guest-exec-status', pid=pid)
            if result.get('exited'):
                if result.get('exitcode') != 0:
                    raise Blocked('guest-command-failed')
                return result
            time.sleep(.2)
        raise Blocked('guest-command-timeout')

    def put(self, data, remote):
        handle = self.call('guest-file-open', path=remote, mode='wb')
        try:
            for start in range(0, len(data), 48*1024):
                chunk = data[start:start+48*1024]
                reply = self.call('guest-file-write', handle=handle,
                                  **{'buf-b64': base64.b64encode(chunk).decode()})
                if reply['count'] != len(chunk):
                    raise Blocked('guest-short-write')
            self.call('guest-file-flush', handle=handle)
        finally:
            self.call('guest-file-close', handle=handle)

    def read(self, remote):
        handle = self.call('guest-file-open', path=remote, mode='rb')
        try:
            data = b''
            while True:
                result = self.call('guest-file-read', handle=handle, count=65536)
                data += base64.b64decode(result.get('buf-b64', ''))
                if len(data) > 1024*1024:
                    raise Blocked('guest-report-too-large')
                if result.get('eof') or not result.get('count'):
                    return data
        finally:
            self.call('guest-file-close', handle=handle)


def task_xml(directory):
    # InteractiveToken: no password, service desktop, admin elevation or login.
    arguments = subprocess.list2cmdline([directory+'\\pfc_windows_worker.py', directory+'\\request.json'])
    return ('<?xml version="1.0" encoding="UTF-16"?>'
            '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
            '<Principals><Principal id="Author"><UserId>PFC-Test</UserId>'
            '<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel>'
            '</Principal></Principals><Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>'
            '<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>'
            '<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>'
            '<ExecutionTimeLimit>PT20M</ExecutionTimeLimit></Settings>'
            '<Actions Context="Author"><Exec><Command>'+escape(PYTHON)+'</Command>'
            '<Arguments>'+escape(arguments)+'</Arguments><WorkingDirectory>'+escape(directory)+
            '</WorkingDirectory></Exec></Actions></Task>').encode('utf-16')


def validate_result(result, request_id, checks):
    if result.get('request_id') != request_id:
        raise Blocked('stale-result')
    if result.get('status') == 'passed':
        tests = result.get('tests', [])
        if [t.get('check') for t in tests] != checks or any(t.get('exit_code') != 0 for t in tests):
            raise Blocked('incomplete-test-results')
    return result


def windows_checks(guest, checks, ready_timeout, test_timeout, cleanup=None):
    # A cheap, read-only execution probe comes before staging or UI interaction.
    guest.execute(PYTHON, ['-c', 'import sys; assert sys.version_info >= (3, 10)'])
    request_id = uuid.uuid4().hex
    directory = 'C:\\PFC-Test\\workflow\\'+request_id
    guest.execute(PYTHON, ['-c', 'import pathlib,sys; pathlib.Path(sys.argv[1]).mkdir(parents=True)', directory])
    files = {'pfc.py': ROOT/'pfc.py', 'pfc_windows_worker.py': ROOT/'tools/pfc_windows_worker.py'}
    files.update({name: ROOT/'tools'/name for name in checks})
    # Shared fixtures used by folder tests, harmless for other groups.
    files['folder_native_test_support.py'] = ROOT/'tools/folder_native_test_support.py'
    hashes = {}
    for name, path in files.items():
        data = path.read_bytes(); hashes[name] = digest(data)
        guest.put(data, directory+'\\'+name)
    request = dict(request_id=request_id, checks=checks, files=hashes, test_timeout=test_timeout)
    guest.put(json.dumps(request).encode(), directory+'\\request.json')
    guest.put(task_xml(directory), directory+'\\task.xml')
    task = 'PFC-Workflow-'+request_id
    created = False
    result = None
    cleanup = cleanup if cleanup is not None else []
    try:
        created = True
        guest.execute(SCHTASKS, ['/Create', '/TN', task, '/XML', directory+'\\task.xml'])
        guest.execute(SCHTASKS, ['/Run', '/TN', task])
        deadline = time.monotonic()+ready_timeout
        began_tests = False
        while time.monotonic() < deadline:
            try:
                result = validate_result(json.loads(guest.read(directory+'\\result.json')), request_id, checks)
            except Blocked as exc:
                if str(exc) != 'guest-file-open-unavailable':
                    raise
            else:
                if result['status'] in ('passed', 'failed', 'blocked'):
                    break
                if result['status'] == 'running' and not began_tests:
                    began_tests = True
                    deadline = time.monotonic()+len(checks)*(test_timeout+15)
            time.sleep(1)
        else:
            raise Blocked('test-timeout' if began_tests else 'interactive-session-not-ready')
        return {**result, 'artifact_sha256': hashes['pfc.py'], 'cleanup': cleanup}
    finally:
        if created:
            # Exact task generated by this run only. Never reset a shared desktop.
            if not result or result.get('status') not in ('passed', 'failed', 'blocked'):
                try:
                    guest.execute(SCHTASKS, ['/End', '/TN', task])
                except (Blocked, OSError):
                    cleanup.append('task-stop-unconfirmed')
            try:
                guest.execute(SCHTASKS, ['/Delete', '/TN', task, '/F'])
            except (Blocked, OSError):
                cleanup.append('task-removal-unconfirmed')


def run_vm(store, run_id, selected, ready_timeout=45, test_timeout=180, manager=MANAGER):
    if store.get(run_id)['status'] != 'running':
        raise ValueError('Run already finished')
    if not selected or len(selected) > 5 or any(name not in ALLOWED for name in selected):
        raise ValueError('Select 1–5 supported checks')
    store.mark(run_id, 'environment')
    definitions = digest(b''.join((ROOT/'tools'/name).read_bytes() for name in sorted(selected)))
    sys.path.insert(0, str(manager))
    leases = importlib.import_module('vm_lease')
    specs = importlib.import_module('vm_pool_config').VM_SPECS
    stop = threading.Event()
    lease = None
    queued_request = None
    heartbeat = None
    started = time.monotonic()
    output = {'status': 'blocked', 'stage': 'lease', 'cleanup': []}
    try:
        grant = leases.request_lease('codex', 'pfc-workflow-'+run_id, 'PFC Windows validation', 1800)
        if grant['result'] == 'waiting':
            queued_request = grant['request']['request_id']
            # Wait for promotion without touching either desktop.
            grant = leases.wait_for_lease(queued_request, min(60, ready_timeout))
        if grant['result'] != 'granted':
            raise Blocked('vm-pool-busy')
        if grant.get('reused'):
            raise Blocked('lease-already-owned-by-another-runner')
        lease = grant['lease']
        queued_request = None
        spec = specs[lease['vm_id']]
        output.update(vm_id=spec.vm_id, stage='qga-ready')
        def renew():
            while not stop.wait(60):
                if leases.heartbeat(lease['lease_id'], 1800)['result'] != 'renewed':
                    stop.set()
        heartbeat = threading.Thread(target=renew, daemon=True); heartbeat.start()
        guest = Guest(lease, spec, leases)
        deadline = time.monotonic()+ready_timeout
        while True:
            try:
                guest.call('guest-ping')
                break
            except (OSError, Blocked) as exc:
                if str(exc) == 'lease-lost' or time.monotonic() >= deadline:
                    raise Blocked('qga-not-ready') from exc
                time.sleep(1)
        output['stage'] = 'execution-readiness'
        output.update(windows_checks(guest, selected, ready_timeout, test_timeout, output['cleanup']))
    except (Blocked, OSError, ValueError, KeyError) as exc:
        output.update(status='blocked', reason=str(exc) if isinstance(exc, Blocked) else type(exc).__name__)
    except KeyboardInterrupt:
        output.update(status='blocked', reason='interrupted')
    finally:
        stop.set()
        if heartbeat:
            heartbeat.join(timeout=6)
        if queued_request:
            try:
                cancelled = leases.cancel(queued_request)
                if cancelled['result'] != 'cancelled':
                    # Promotion may race timeout/cancel: recover only our own
                    # request's lease and release it, without guest interaction.
                    late = leases.wait_for_lease(queued_request, 0)
                    if late['result'] == 'granted':
                        lease = late['lease']
                    elif late['result'] != 'missing':
                        output['cleanup'].append('queue-cancel-unconfirmed')
            except Exception:
                output['cleanup'].append('queue-cancel-unconfirmed')
        if lease:
            # Independent attempts: a network cleanup failure must not skip release.
            try:
                result = subprocess.run([sys.executable, str(manager/'vm_network.py'), 'disable',
                                         '--lease-id', lease['lease_id']], capture_output=True, timeout=15)
                if result.returncode:
                    output['cleanup'].append('network-disable-unconfirmed')
            except (OSError, subprocess.TimeoutExpired):
                output['cleanup'].append('network-disable-unconfirmed')
            try:
                if leases.release(lease['lease_id'])['result'] != 'released':
                    output['cleanup'].append('lease-release-unconfirmed')
            except Exception:
                output['cleanup'].append('lease-release-unconfirmed')
        if output['cleanup']:
            output['status'] = 'blocked'
        store.stage(run_id, 'windows', output['status'], time.monotonic()-started,
                    scope=digest(json.dumps([selected, definitions, output.get('vm_id'), output.get('environment')]).encode()), result=output)
    return output


def main():
    import signal
    def interrupted(*_args):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--checks', nargs='+', choices=sorted(ALLOWED), default=['tooltip_check.py'])
    parser.add_argument('--ready-timeout', type=int, default=45)
    parser.add_argument('--test-timeout', type=int, default=180)
    args = parser.parse_args()
    result = run_vm(Store(args.state_dir), args.run, args.checks,
                    max(5, min(120, args.ready_timeout)), max(5, min(180, args.test_timeout)))
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
