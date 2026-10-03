"""Lease-aware Windows regression with host-managed desktop preparation.

The host desktop module prepares the dedicated test session after QGA execution
passes. The worker still verifies the real input desktop before importing PFC.
"""
from __future__ import annotations
import argparse
import base64
from contextlib import contextmanager
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
        self._client = None

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    @contextmanager
    def connection(self):
        fresh = self._client is None
        try:
            if fresh:
                self._client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._client.settimeout(30)
                self._client.connect(str(self.spec.qga_socket))
            yield self._client, fresh
        except BaseException:
            self.close()
            raise

    def assert_owner(self):
        active = self.leases.snapshot()['vms'][self.spec.vm_id]['active']
        if not active or active['lease_id'] != self.lease['lease_id']:
            raise Blocked('lease-lost')

    def call(self, execute, **arguments):
        # A timed-out synchronization handshake has not sent the requested
        # command yet, so reconnecting is safe. Never replay an ambiguous exec
        # or write response. Bound retries independently of readiness polling.
        for attempt in range(3):
            try:
                return self._call(execute, **arguments)
            except Blocked as exc:
                if str(exc) != 'qga-response-timeout: guest-sync-delimited' or attempt == 2:
                    raise
                print('Windows: reconnecting test channel before command dispatch', flush=True)
                time.sleep(.2)

    def _call(self, execute, **arguments):
        self.assert_owner()  # every guest read/write/exec, not just entry
        token = uuid.uuid4().hex
        request = {'execute': execute, 'arguments': arguments, 'id': token}
        with self.connection() as (client, fresh):
            # A newly active Windows guest can take >5 s to answer one QGA
            # request even though the bounded readiness probe just succeeded.
            # Do not retry non-idempotent writes/exec after an ambiguous reply.
            client.settimeout(30)
            def receive(expected, operation):
                data = b''
                deadline = time.monotonic()+(5 if operation == 'guest-sync-delimited' else 30)
                while True:
                    client.settimeout(max(.001, deadline-time.monotonic()))
                    try:
                        chunk = client.recv(65536)
                    except TimeoutError:
                        raise Blocked('qga-response-timeout: '+operation) from None
                    if not chunk or len(data) > 2*1024*1024:
                        raise Blocked('qga-invalid-response')
                    data += chunk
                    if b'\xff' in data: data = data.rsplit(b'\xff', 1)[1]
                    while b'\n' in data:
                        line, data = data.split(b'\n', 1)
                        try:
                            candidate = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(candidate, dict) and candidate.get('id') == expected:
                            return candidate
                    if time.monotonic() >= deadline:
                        raise Blocked('qga-response-timeout: '+operation)
            # QGA requires a synchronization barrier on EVERY new connection,
            # not just matching IDs. Flush partial input/output from old clients
            # before issuing the command (especially following a timeout).
            if fresh:
                nonce = time.time_ns() & ((1 << 63)-1)
                sync_id = token+'-sync'
                sync = {'execute':'guest-sync-delimited', 'arguments':{'id':nonce}, 'id':sync_id}
                client.sendall(b'\xff'+(json.dumps(sync)+'\n').encode())
                if receive(sync_id, 'guest-sync-delimited').get('return') != nonce:
                    raise Blocked('qga-sync-mismatch')
            self.assert_owner()
            client.sendall((json.dumps(request)+'\n').encode())
            result = receive(token, execute)
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
        # Stage only the new request directory through verified Python. Keeping
        # each encoded argument under 16 KiB respects Windows command-line limits
        # and avoids the same intermittent QGA file-channel stall as report reads.
        script = ('import base64,sys; '
                  'f=open(sys.argv[1],"wb" if int(sys.argv[2])==0 else "r+b"); '
                  'f.seek(int(sys.argv[2])); f.write(base64.b64decode(sys.argv[3])); f.close()')
        for start in range(0, max(1, len(data)), 12*1024):
            chunk = base64.b64encode(data[start:start+12*1024]).decode()
            self.execute(PYTHON, ['-c', script, remote, str(start), chunk])

    def read(self, remote, limit=1024*1024):
        # The Windows QGA regular-file channel intermittently hangs while
        # polling atomically replaced reports. Use the already-verified Python
        # execution channel for bounded, read-only chunks; never replay a write.
        data = b''
        chunk_size = 256*1024
        script = ('import pathlib,sys; p=pathlib.Path(sys.argv[1]); '
                  'f=p.open("rb"); f.seek(int(sys.argv[2])); '
                  'sys.stdout.buffer.write(f.read(int(sys.argv[3])))')
        while True:
            try:
                result = self.execute(PYTHON, ['-c', script, remote, str(len(data)), str(chunk_size)])
            except Blocked as exc:
                if str(exc) == 'guest-command-failed':
                    raise Blocked('guest-file-open-unavailable') from None
                raise
            if result.get('out-truncated'):
                raise Blocked('guest-report-truncated')
            chunk = base64.b64decode(result.get('out-data', ''))
            data += chunk
            if len(data) > limit:
                raise Blocked('guest-report-too-large')
            if len(chunk) < chunk_size:
                return data


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


def stop_request_checks(guest, directory, checks):
    # Ending a scheduled task can leave its GUI children alive. Match only the
    # exact commands staged by this request, never all Python/PFC processes.
    expected = [subprocess.list2cmdline([PYTHON, directory+'\\'+name, 'pfc']) for name in checks]
    commands = ','.join("'"+item.replace("'", "''")+"'" for item in expected)
    script = ("$ErrorActionPreference='Stop'; $expected=@("+commands+"); "
              "$children=@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
              "Where-Object {$expected -contains $_.CommandLine}); "
              "foreach($child in $children) { & taskkill.exe /PID $child.ProcessId /T /F | Out-Null }; "
              "if(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
              "Where-Object {$expected -contains $_.CommandLine}) {throw 'request-child-still-running'}")
    guest.execute(r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
                  ['-NoProfile', '-NonInteractive', '-Command', script], timeout=30)


def windows_checks(guest, checks, ready_timeout, test_timeout, cleanup=None, evidence_dir=None):
    # A cheap, read-only execution probe comes before staging or UI interaction.
    print('Windows: checking Python execution', flush=True)
    guest.execute(PYTHON, ['-c', 'import sys; assert sys.version_info >= (3, 10)'])
    print('Windows: preparing leased test desktop', flush=True)
    try:
        desktop = importlib.import_module('vm_desktop')
        desktop_status = desktop.prepare_desktop(guest, timeout=ready_timeout)
        # An unlocked console can still have a powered-off display after S4.
        # Wake only the verified test account, through the same leased helper;
        # never type into an unknown account or bypass desktop readiness.
        kind, _, _ = desktop.inspect_login_screen(guest)
        if kind == 'blank':
            if not desktop.session_status(guest).get('ready'):
                raise Blocked('desktop-not-ready-for-display-wake')
            with desktop.Keyboard(guest) as keyboard:
                keyboard.press(0xffe1)
            time.sleep(.5)
            if desktop.inspect_login_screen(guest)[0] == 'blank':
                raise Blocked('desktop-display-remains-blank')
            desktop_status['display_woken'] = True
    except (ImportError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if isinstance(exc, Blocked):
            raise
        # The host helper uses fixed reason codes, never credentials or OCR text.
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        raise Blocked('desktop-preparation-failed: '+reason) from None
    request_id = uuid.uuid4().hex
    print('Windows: desktop ready; staging verified candidate', flush=True)
    directory = 'C:\\PFC-Test\\workflow\\'+request_id
    guest.execute(PYTHON, ['-c', 'import pathlib,sys; pathlib.Path(sys.argv[1]).mkdir(parents=True)', directory])
    files = {'pfc.py': ROOT/'pfc.py', 'pfc_windows_worker.py': ROOT/'tools/pfc_windows_worker.py'}
    files.update({name: ROOT/'tools'/name for name in checks})
    # Shared fixtures used by folder tests, harmless for other groups.
    files['folder_native_test_support.py'] = ROOT/'tools/folder_native_test_support.py'
    hashes = {}
    for name, path in files.items():
        print('Windows: staging '+name, flush=True)
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
        print('Windows: native checks started', flush=True)
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
        if evidence_dir is not None:
            evidence_dir = evidence_dir/request_id
            evidence_dir.mkdir(parents=True, exist_ok=True)
            for test in result.get('tests', []):
                name = test['check']
                (evidence_dir/(name+'.log')).write_bytes(guest.read(directory+'\\'+name+'.log'))
            if result['status']=='passed' and 'review_compare_check.py' in checks:
                from PIL import Image
                import io
                for name in ('text-light','text-dark','workbook','workbook-empty','folder-pair','archive-draft'):
                    data=guest.read(directory+'\\evidence-'+name+'.bmp', limit=16*1024*1024)
                    Image.open(io.BytesIO(data)).save(evidence_dir/(name+'.png'))
        return {**result, 'artifact_sha256': hashes['pfc.py'],
                'desktop_preparation': desktop_status, 'cleanup': cleanup}
    finally:
        if created:
            # Exact task generated by this run only. Never reset a shared desktop.
            if not result or result.get('status') not in ('passed', 'failed', 'blocked'):
                try:
                    guest.execute(SCHTASKS, ['/End', '/TN', task])
                except (Blocked, OSError):
                    cleanup.append('task-stop-unconfirmed')
            try:
                stop_request_checks(guest, directory, checks)
            except (Blocked, OSError):
                cleanup.append('test-child-stop-unconfirmed')
            try:
                guest.execute(SCHTASKS, ['/Delete', '/TN', task, '/F'])
            except (Blocked, OSError):
                cleanup.append('task-removal-unconfirmed')


def run_vm(store, run_id, selected, ready_timeout=120, test_timeout=180, manager=MANAGER):
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
    guest = None
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
        output.update(windows_checks(guest, selected, ready_timeout, test_timeout, output['cleanup'],
                                     store.directory/run_id/'windows-evidence'))
    except (Blocked, OSError, ValueError, KeyError) as exc:
        output.update(status='blocked', reason=str(exc) if isinstance(exc, Blocked) else type(exc).__name__)
    except KeyboardInterrupt:
        output.update(status='blocked', reason='interrupted')
    finally:
        if guest is not None:
            guest.close()
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
    parser.add_argument('--ready-timeout', type=int, default=120)
    parser.add_argument('--test-timeout', type=int, default=180)
    args = parser.parse_args()
    result = run_vm(Store(args.state_dir), args.run, args.checks,
                    max(5, min(120, args.ready_timeout)), max(5, min(180, args.test_timeout)))
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
