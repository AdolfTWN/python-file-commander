"""Measured PFC maintenance workflow. Local private records; no inferred tokens.

Start one run per task; use its explicit ID in subsequent commands. Ordinary
subprocesses perform deterministic work, not nested model invocations.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import signal
import sqlite3
import statistics
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1
GROUPS = {
    'tooltip': ('tooltip', 'nested_menu', 'context_settings', 'pathbar'),
    'tree': ('folder_scroll', 'folder_navigation', 'folder_sticky', 'folder_hierarchy', 'folder_leaf'),
    'preview': ('preview_tabs', 'markdown_reading', 'markdown_workspace'),
    'settings': ('settings', 'settings_previews', 'settings_layout', 'column_menu', 'settings_readability_groups'),
    'tabs': ('single_panel', 'tab_panel_drag', 'tab_lock', 'workflow_features'),
    'vcs': ('vcs_actions', 'vcs_gui'),
    'workflow': (),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def environment():
    import tkinter
    tcl = tkinter.Tcl()
    return {'platform': platform.system(), 'arch': platform.machine(),
            'python': platform.python_version(), 'tcl': tcl.call('info', 'patchlevel'),
            'host': digest(platform.node().encode())[:16], 'schema': SCHEMA}


def source_fingerprint():
    files = [ROOT/'pfc.py', *sorted((ROOT/'pycommander').glob('*.py')),
             *sorted((ROOT/'tools').glob('*.py')), *sorted((ROOT/'tests').glob('test_*.py'))]
    hasher = hashlib.sha256()
    for path in files:
        hasher.update(str(path.relative_to(ROOT)).encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt':
        path.chmod(0o700)
    return path


class Store:
    def __init__(self, directory=None):
        base = Path(directory) if directory else Path.home()/'.local/state/pfc-workflow'
        self.directory = private_dir(base)
        self.database = base/'runs.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS stages (id TEXT PRIMARY KEY, run_id TEXT, data TEXT NOT NULL)')
        if os.name != 'nt':
            self.database.chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.database, timeout=30)

    def start(self, kind, model='unknown', effort='unknown'):
        run_id = uuid.uuid4().hex
        record = dict(id=run_id, kind=kind, model=model, effort=effort,
                      started=time.time(), ended=None, status='running',
                      environment=environment(), source=source_fingerprint(), usage=None, coverage='unknown',
                      phases=[], active_phase='analysis', phase_started=time.time())
        self.save(record)
        return record

    def save(self, record):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO runs VALUES (?, ?)',
                       (record['id'], json.dumps(record)))

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT data FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise ValueError('Unknown run ID')
        record = json.loads(row[0])
        # Bootstrap/older traces cannot retrospectively identify work phases.
        record.setdefault('phases', [])
        record.setdefault('active_phase', 'unclassified')
        record.setdefault('phase_started', record['started'])
        return record

    def stages(self, run_id):
        with self.connect() as db:
            rows = db.execute('SELECT data FROM stages WHERE run_id=? ORDER BY rowid', (run_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def stage(self, run_id, label, status, seconds, **details):
        self.get(run_id)
        stage = dict(id=uuid.uuid4().hex, label=label, status=status,
                     seconds=round(seconds, 4), at=time.time(), **details)
        with self.connect() as db:
            db.execute('INSERT INTO stages VALUES (?, ?, ?)', (stage['id'], run_id, json.dumps(stage)))
        return stage

    def report(self, run_id):
        record = self.get(run_id)
        if record.get('events_path'):
            try:
                with Path(record['events_path']).open(encoding='utf-8') as stream:
                    record['usage'] = parse_usage(stream)
                record['coverage'] = 'partial' if record['usage'] else 'unknown'
                self.save(record)
            except OSError:
                pass
        stages = self.stages(run_id)
        elapsed = (record['ended'] or time.time()) - record['started']
        result = dict(run_id=run_id, status=record['status'], elapsed_seconds=round(elapsed, 2),
                      recorded_stages=len(stages), failed_stages=sum(s['status'] != 'passed' for s in stages),
                      retries=sum(max(0, n-1) for n in
                                  [sum(s['label'] == label for s in stages) for label in {s['label'] for s in stages}]),
                      usage=record['usage'], usage_coverage=record['coverage'],
                      comparison={'status': 'no comparable baseline'})
        result['phases'] = record.get('phases', [])
        with self.connect() as db:
            candidates = [json.loads(row[0]) for row in db.execute('SELECT data FROM runs')]
        comparable = [r for r in candidates if r['started'] < record['started'] and
                      r['environment'] == record['environment'] and r['kind'] == record['kind']]
        # Stage speed remains measurable even when an unrelated VM stage blocks
        # the task. No failed stage is ever used as a speed baseline.
        result['stage_comparisons'] = []
        for stage in {s['label']: s for s in stages}.values():
            if stage['status'] != 'passed':
                continue
            samples = []
            for prior in sorted(comparable, key=lambda r: r['started'], reverse=True):
                matches = [s for s in self.stages(prior['id']) if s['status'] == 'passed' and
                           s['label'] == stage['label'] and s.get('scope') == stage.get('scope')]
                if matches:
                    samples.append(matches[-1]['seconds'])
                if len(samples) == 5:
                    break
            if samples:
                baseline = statistics.median(samples)
                result['stage_comparisons'].append({'stage': stage['label'], 'samples': len(samples),
                    'seconds': stage['seconds'], 'baseline_seconds': baseline,
                    'change_percent': round((stage['seconds']/baseline-1)*100, 1) if baseline else None})
        # Failed/blocked and open runs never become a faster-success task baseline.
        if record['status'] != 'passed' or not stages:
            return result
        signature = sorted((s['label'], s.get('scope', '')) for s in {s['label']: s for s in stages}.values())
        peers = []
        for prior in sorted(candidates, key=lambda r: r['started'], reverse=True):
            if (prior['id'] == run_id or prior['status'] != 'passed' or
                    prior['started'] >= record['started'] or prior['kind'] != record['kind'] or
                    prior['environment'] != record['environment']):
                continue
            old_stages = self.stages(prior['id'])
            if sorted((s['label'], s.get('scope', '')) for s in {s['label']: s for s in old_stages}.values()) == signature:
                peers.append(prior)
            if len(peers) == 5:
                break
        if not peers:
            return result
        baseline = statistics.median(r['ended']-r['started'] for r in peers)
        comparison = {'status': 'observed; not a causal speedup claim', 'samples': len(peers),
                      'baseline_elapsed_seconds': round(baseline, 2),
                      'elapsed_change_percent': round((elapsed/baseline-1)*100, 1) if baseline > 0 else None,
                      'tokens': 'unknown or incomparable'}
        token_peers = [r for r in peers if r['coverage'] == 'full' and r['usage'] and
                       r['model'] == record['model'] != 'unknown' and r['effort'] == record['effort'] != 'unknown']
        if record['usage'] and record['coverage'] == 'full' and token_peers:
            comparison['tokens'] = {}
            for key, value in record['usage'].items():
                if value is None:
                    continue
                samples = [p['usage'].get(key) for p in token_peers if p['usage'].get(key) is not None]
                if not samples:
                    continue
                old = statistics.median(samples)
                comparison['tokens'][key] = {'current': value, 'baseline_median': old,
                    'change_percent': round((value/old-1)*100, 1) if old else None}
        result['comparison'] = comparison
        return result

    def finish(self, run_id, status):
        record = self.get(run_id)
        if record['status'] != 'running':
            raise ValueError('Run already finished')
        latest = {s['label']: s for s in self.stages(run_id)}
        if status == 'passed' and (not latest or any(s['status'] != 'passed' for s in latest.values())):
            raise ValueError('Cannot mark passed with failed/blocked stages; use completed-with-issues')
        timestamp = time.time()
        record['phases'].append({'phase': record['active_phase'], 'seconds': round(timestamp-record['phase_started'], 3)})
        record.update(status=status, ended=timestamp)
        self.save(record)
        return self.report(run_id)

    def mark(self, run_id, phase):
        record = self.get(run_id)
        if record['status'] != 'running':
            raise ValueError('Run already finished')
        timestamp = time.time()
        if record['active_phase'] != phase:
            record['phases'].append({'phase': record['active_phase'], 'seconds': round(timestamp-record['phase_started'], 3)})
            record.update(active_phase=phase, phase_started=timestamp)
            self.save(record)
        return {'run_id': run_id, 'phase': phase}


def parse_usage(lines):
    """Official codex exec --json turn deltas, not cumulative rollout counters.

    Do not retain transcript text, tool arguments, paths or credentials. Reimport
    replaces this run's usage rather than adding it twice. Input cache is a
    subset of input; reasoning is a subset of output, not an extra charge here.
    """
    keys = ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens')
    totals = {k: 0 for k in keys}
    observed = {k: False for k in keys}
    count = 0
    missing = set()
    for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict) or event.get('type') != 'turn.completed' or not isinstance(event.get('usage'), dict):
            continue
        usage = event['usage']
        if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('input_tokens', 'output_tokens')):
            raise ValueError('Invalid usage counters')
        for key in keys:
            value = usage.get(key)
            if value is not None:
                if type(value) is not int or value < 0:
                    raise ValueError('Invalid usage counters')
                totals[key] += value
                observed[key] = True
            else:
                missing.add(key)
        if usage.get('cached_input_tokens', 0) > usage['input_tokens']:
            raise ValueError('Cached input exceeds input')
        count += 1
    return ({k: totals[k] if observed[k] and k not in missing else None for k in keys} if count else None)


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'posix':
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
    else:
        # Only this runner's child tree, never the VM or another session.
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    process.wait(timeout=10)


def run_command(store, run_id, label, command, timeout=180, scope=None):
    record = store.get(run_id)
    if record['status'] != 'running':
        raise ValueError('Run already finished')
    if not command:
        raise ValueError('Missing command')
    logdir = private_dir(store.directory/run_id)
    log = logdir/(uuid.uuid4().hex+'.log')
    started = time.monotonic()
    status, code, process = 'failed', None, None
    try:
        with log.open('wb') as output:
            if os.name != 'nt':
                log.chmod(0o600)
            process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=os.name == 'posix')
            code = process.wait(timeout=timeout)
            status = 'passed' if code == 0 else 'failed'
    except subprocess.TimeoutExpired:
        status = 'timeout'
    except (OSError, KeyboardInterrupt):
        status = 'interrupted' if process else 'launch-failed'
    finally:
        if process is not None:
            stop_process(process)
    # Never echo raw commands/logs: arguments and output can contain private data.
    result = store.stage(run_id, label, status, time.monotonic()-started,
                         scope=scope or digest(json.dumps(command).encode()),
                         exit_code=code, log=log.name, output_bytes=log.stat().st_size)
    return {k: result[k] for k in ('label', 'status', 'seconds', 'exit_code', 'log', 'output_bytes')}


def checks(profile):
    unit = ('unit', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'])
    if profile == 'workflow':
        return [('workflow-unit', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_pfc_workflow*.py', '-q'])]
    selected = [unit]
    lines = (ROOT/'tools/run_headless_checks.sh').read_text().splitlines()
    for line in lines:
        if not line.startswith('xvfb-run '):
            continue
        args = shlex.split(line)
        script = Path(args[3]).stem.removesuffix('_check')
        if profile != 'full' and script not in GROUPS[profile]:
            continue
        args[2] = sys.executable
        args = [str(ROOT) if part == '$project_root' else part for part in args]
        label = script + ('-portable' if args[-1] == 'pfc' else '-source')
        selected.append((label, args))
    return selected


def run_tests(store, run_id, profile, jobs, timeout):
    if jobs not in (1, 2, 4):
        raise ValueError('Use 1, 2 or 4 isolated headless workers')
    selected = checks(profile)
    definitions = b''.join(p.read_bytes() for p in sorted((ROOT/'tests').glob('test_*.py')))
    definitions += b''.join(p.read_bytes() for p in sorted((ROOT/'tools').glob('*check.py')))
    scope = digest(definitions + json.dumps([profile, [x[0] for x in selected]]).encode())
    started = time.monotonic()
    source_before = source_fingerprint()
    # Separate xvfb-run per subprocess. Never parallelize a shared Windows desktop.
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = [executor.submit(run_command, store, run_id, label, cmd, timeout, scope)
                   for label, cmd in selected]
        results = [f.result() for f in futures]
    status = 'passed' if all(r['status'] == 'passed' for r in results) else 'failed'
    if source_before != source_fingerprint():
        status = 'failed'
        results.append({'label': 'source-stability', 'status': 'source-changed-during-tests'})
    store.stage(run_id, 'suite-'+profile, status, time.monotonic()-started, scope=scope,
                workers=jobs, source=source_before)
    return {'profile': profile, 'status': status, 'checks': len(results),
            'failures': [r for r in results if r['status'] != 'passed'],
            'stage_comparisons': store.report(run_id)['stage_comparisons']}


def release_check(store, run_id):
    """Read-only release gate: same commit, tag, portable and verified mirror job."""
    started = time.monotonic()
    result = {'status': 'blocked', 'stage': 'release-check'}
    def output(*command):
        return subprocess.check_output(command, cwd=ROOT, timeout=30, stderr=subprocess.DEVNULL).decode().strip()
    try:
        version = re.search(r'__version__ = "([0-9.]+)"', (ROOT/'pycommander/__init__.py').read_text())[1]
        if output('git', 'status', '--porcelain'):
            raise ValueError('worktree-not-clean')
        head = output('git', 'rev-parse', 'HEAD')
        remote = output('git', 'ls-remote', 'origin', 'refs/heads/main', 'refs/tags/v'+version)
        refs = dict(line.split()[::-1] for line in remote.splitlines())
        if any(refs.get(ref) != head for ref in ('refs/heads/main', 'refs/tags/v'+version)):
            raise ValueError('published-refs-mismatch')
        # PFC's actual updater is authoritative, not a separate download URL.
        sys.path.insert(0, str(ROOT))
        from pycommander.app import fetch_pfc_update
        fetched_version, data = fetch_pfc_update()
        if fetched_version != version or data != (ROOT/'pfc.py').read_bytes():
            raise ValueError('updater-artifact-mismatch')
        jobs = json.loads(output('gh', 'run', 'list', '--workflow', 'gitlab-mirror.yml', '--commit', head,
                                 '--limit', '5', '--json', 'databaseId,status,conclusion'))
        successful = next((job for job in jobs if job['status'] == 'completed' and job['conclusion'] == 'success'), None)
        if not successful:
            raise ValueError('mirror-not-yet-verified')
        log = output('gh', 'run', 'view', str(successful['databaseId']), '--log')
        if 'Verified: GitHub and GitLab branch/tag references match.' not in log:
            raise ValueError('mirror-ref-proof-missing')
        result.update(status='passed', version=version, commit=head, portable_sha256=digest(data),
                      mirror_workflow=successful['databaseId'])
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        result['reason'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    store.stage(run_id, 'release-check', result['status'], time.monotonic()-started,
                scope='github-updater-gitlab-v1', result=result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path)
    sub = parser.add_subparsers(dest='action', required=True)
    start = sub.add_parser('start')
    start.add_argument('--kind', required=True, choices=['bugfix', 'feature', 'validation', 'release', 'maintenance'])
    start.add_argument('--model', default='unknown'); start.add_argument('--effort', default='unknown')
    start.add_argument('--events', type=Path)
    automatic = sub.add_parser('auto-test')
    automatic.add_argument('--profile', choices=[*GROUPS, 'full'], default='full')
    automatic.add_argument('--jobs', type=int, choices=[1, 2, 4], default=2)
    automatic.add_argument('--timeout', type=int, default=180)
    for name in ('run', 'test', 'report', 'finish', 'usage', 'release-check', 'mark'):
        p = sub.add_parser(name); p.add_argument('--run', required=True)
        if name == 'run':
            p.add_argument('--stage', required=True); p.add_argument('--timeout', type=int, default=180)
            p.add_argument('command', nargs=argparse.REMAINDER)
        elif name == 'test':
            p.add_argument('--profile', choices=[*GROUPS, 'full'], required=True)
            p.add_argument('--jobs', type=int, choices=[1, 2, 4], default=2)
            p.add_argument('--timeout', type=int, default=180)
        elif name == 'finish':
            p.add_argument('--status', choices=['passed', 'blocked', 'failed', 'completed-with-issues'], required=True)
        elif name == 'usage':
            p.add_argument('--events', type=Path, required=True)
            p.add_argument('--coverage', choices=['full', 'partial'], default='partial')
        elif name == 'mark':
            p.add_argument('--phase', choices=['analysis', 'implementation', 'validation', 'environment', 'release'], required=True)
    args = parser.parse_args(argv)
    store = Store(args.state_dir)
    if args.action == 'start':
        result = store.start(args.kind, args.model, args.effort)
        events = args.events or os.environ.get('PFC_WORKFLOW_EVENTS')
        if events:
            result['events_path'] = str(Path(events).resolve())
            store.save(result)
        result = {'run_id': result['id'], 'status': 'tracking', 'usage': 'unknown until official events imported'}
    elif args.action == 'auto-test':
        run = store.start('validation')
        store.mark(run['id'], 'validation')
        print(json.dumps({'run_id': run['id'], 'status': 'testing', 'profile': args.profile}), flush=True)
        tests = run_tests(store, run['id'], args.profile, args.jobs, args.timeout)
        result = store.finish(run['id'], tests['status'])
        result['failures'] = tests['failures']
    elif args.action == 'run':
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        result = run_command(store, args.run, args.stage, command, args.timeout)
    elif args.action == 'test':
        store.mark(args.run, 'validation')
        result = run_tests(store, args.run, args.profile, args.jobs, args.timeout)
    elif args.action == 'usage':
        record = store.get(args.run)
        record.pop('events_path', None)  # explicit complete import supersedes stream
        with args.events.open(encoding='utf-8') as stream:
            record['usage'] = parse_usage(stream)
        record['coverage'] = args.coverage if record['usage'] else 'unknown'
        store.save(record); result = store.report(args.run)
    elif args.action == 'finish':
        result = store.finish(args.run, args.status)
    elif args.action == 'release-check':
        store.mark(args.run, 'release')
        result = release_check(store, args.run)
    elif args.action == 'mark':
        result = store.mark(args.run, args.phase)
    else:
        result = store.report(args.run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('status') not in ('failed', 'timeout', 'blocked', 'launch-failed', 'interrupted') else 1


if __name__ == '__main__':
    raise SystemExit(main())
