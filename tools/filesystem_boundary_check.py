"""Real cross-device move/copy and link-safe deletion inside disposable roots."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
ops=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.fileops')


def snapshot(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


with tempfile.TemporaryDirectory(prefix='pfc-fs-boundary-') as raw:
    root=Path(raw);sentinel=root/'outside';sentinel.mkdir()
    (sentinel/'keep.txt').write_bytes(b'NEVER DELETE')
    original=snapshot(sentinel)
    link_root=root/'delete-links';link_root.mkdir()
    try:(link_root/'outside-link').symlink_to(sentinel,target_is_directory=True)
    except (OSError,NotImplementedError):print(json.dumps({'event':'boundary.links.skipped','reason':'symlink privilege unavailable'}),flush=True)
    else:
        result=ops.delete_items([link_root],progress=lambda *_:None)
        assert not result.failures and snapshot(sentinel)==original
        assert not link_root.exists()
        print(json.dumps({'event':'boundary.links.passed'}),flush=True)
    alternative=Path('/dev/shm')
    if os.name!='nt' and alternative.is_dir() and root.stat().st_dev!=alternative.stat().st_dev:
        with tempfile.TemporaryDirectory(prefix='pfc-cross-device-',dir=alternative) as other:
            destination=Path(other);source=root/'payload';source.mkdir()
            (source/'empty').mkdir();nested=source/'中文 nested';nested.mkdir()
            (nested/'report 🧪.txt').write_text('cross-device fixture\n'*100,encoding='utf-8')
            (source/'binary.bin').write_bytes(bytes(range(256))*400)
            expected=snapshot(source)
            old=destination/source.name;old.mkdir();(old/'old.txt').write_bytes(b'PREVIOUS')
            result=ops.move_items([source],destination,lambda *_:'replace')
            assert not result.failures and not source.exists(),result
            assert snapshot(old)==expected and (old/'empty').is_dir()
            result=ops.copy_items([old],root)
            assert not result.failures and snapshot(root/'payload')==expected
            assert snapshot(old)==expected and snapshot(sentinel)==original
            print(json.dumps({'event':'boundary.cross-device.passed','source_device':root.stat().st_dev,
                              'target_device':destination.stat().st_dev,'files':len(expected),
                              'bytes':sum(p.stat().st_size for p in old.rglob('*') if p.is_file())}),flush=True)
    else:print(json.dumps({'event':'boundary.cross-device.skipped','reason':'second physical filesystem unavailable'}),flush=True)
