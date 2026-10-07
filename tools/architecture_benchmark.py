"""Repeatable archive workload; counters and timings are measured separately."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def workload(module, folders=100, files=20, repeats=5):
    with tempfile.TemporaryDirectory(prefix="pfc-architecture-") as raw:
        root = Path(raw)
        source = root / "selected"
        source.mkdir()
        for number in range(folders):
            folder = source / f"folder-{number:04}"
            folder.mkdir()
            (folder / "empty").mkdir()
            for index in range(files):
                (folder / f"file-{index:03}.md").write_bytes(b"# Note\n" * 32)
        for path in [source, *source.rglob("*")]:
            os.utime(path, (1700000000, 1700000000))
        target = root / "result.zip"
        samples = []
        for _ in range(repeats):
            started = time.perf_counter()
            module.create_zip_archive([source], target)
            samples.append(time.perf_counter() - started)
        counts = {"stat": 0, "scandir": 0}
        real_stat, real_scan = os.stat, os.scandir

        def counted_stat(*args, **kwargs):
            counts["stat"] += 1
            return real_stat(*args, **kwargs)

        def counted_scan(*args, **kwargs):
            counts["scandir"] += 1
            return real_scan(*args, **kwargs)

        updates = []
        with patch("os.stat", counted_stat), patch("os.scandir", counted_scan):
            module.create_zip_archive([source], target,
                                      lambda done, total, name: updates.append((done, total, name)))
        with zipfile.ZipFile(target) as archive:
            manifest = [(i.filename, i.file_size, i.CRC, i.external_attr)
                        for i in archive.infolist()]
        return {"folders": folders, "files_per_folder": files, "repeats": repeats,
                "median_seconds": statistics.median(samples), "samples_seconds": samples,
                "metadata_calls": counts, "members": len(manifest),
                "manifest_sha256": hashlib.sha256(json.dumps(manifest).encode()).hexdigest(),
                "progress_sha256": hashlib.sha256(json.dumps(updates).encode()).hexdigest()}


def notification_workload(module, events=100000, repeats=5):
    enqueue, drain, pending = [], [], []
    path = Path(tempfile.gettempdir()) / "pfc-notification-demo"
    for _ in range(repeats):
        manager = module.DirectoryWatchManager(supported=False)
        started = time.perf_counter()
        for _ in range(events):
            manager.events.put(path)
        enqueue.append(time.perf_counter() - started)
        pending.append(manager.events.qsize())
        started = time.perf_counter()
        changed = manager.drain()
        drain.append(time.perf_counter() - started)
        assert changed == {module.directory_key(path)}
        assert manager.events.empty()
        manager.close()
    return {"events": events, "repeats": repeats, "pending_records": pending,
            "enqueue_median_seconds": statistics.median(enqueue),
            "drain_median_seconds": statistics.median(drain),
            "total_median_seconds": statistics.median([a+b for a, b in zip(enqueue, drain)]),
            "changed_directories": 1}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", default="pycommander.archivefs")
    parser.add_argument("--folders", type=int, default=100)
    parser.add_argument("--files", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--notifications", action="store_true")
    args = parser.parse_args()
    module = importlib.import_module(args.module)
    result = (notification_workload(module, repeats=args.repeats) if args.notifications else
              workload(module, args.folders, args.files, args.repeats))
    print(json.dumps(result, indent=2))
