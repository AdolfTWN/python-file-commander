"""Compare overlay aggregation/navigation with an explicitly named old revision."""
import argparse
import json
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pycommander import vcs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', required=True)
    args = parser.parse_args()
    source = subprocess.run(['git', 'show', args.before + ':pycommander/vcs.py'],
                            check=True, capture_output=True, text=True).stdout
    before = types.ModuleType('pycommander._benchmark_before')
    before.__package__ = 'pycommander'
    exec(compile(source, '<before-vcs>', 'exec'), before.__dict__)
    measurements = {}
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw).resolve()
        git = vcs.vcs_cli('git')
        assert git, 'Git CLI required'
        def command(*params):
            subprocess.run([git, '-C', str(root), *params], check=True,
                           capture_output=True, timeout=30, **vcs._run_options())
        command('init', '-q')
        for number in range(8):
            child = root / str(number); child.mkdir()
            for index in range(250):
                (child / f'{index}.txt').write_text('fixture', encoding='utf-8')
        command('add', '.')
        for label, implementation in [('before', before), ('after', vcs)]:
            implementation.invalidate_vcs_cache()
            run = subprocess.run
            calls = []
            def counted(*a, **kw):
                calls.append(a[0]); return run(*a, **kw)
            with patch.object(implementation.subprocess, 'run', counted):
                started = time.perf_counter()
                states = implementation.folder_statuses(root)
                cold = time.perf_counter() - started
                calls.clear()
                started = time.perf_counter()
                for number in range(8):
                    states = implementation.folder_statuses(root / str(number))
                    assert implementation.status_for(states, root / str(number) / '0.txt') == 'added'
                warm = time.perf_counter() - started
                measurements[label] = dict(cold_seconds=cold, warm_seconds=warm,
                                           warm_git_commands=len(calls))
        for label, implementation in [('before', before), ('after', vcs)]:
            resolves = []
            resolve = Path.resolve
            def counted_resolve(path, *a, **kw):
                resolves.append(path); return resolve(path, *a, **kw)
            states = {}
            started = time.perf_counter()
            with patch.object(Path, 'resolve', counted_resolve):
                for number in range(8):
                    for index in range(250):
                        implementation._merge(states, root / str(number) / f'{index}.txt', 'clean', root)
            measurements[label].update(aggregation_seconds=time.perf_counter() - started,
                                       per_file_resolves=len(resolves))
        vcs.invalidate_vcs_cache()
    print(json.dumps(measurements, indent=2))


if __name__ == '__main__':
    main()
