"""Seeded data-integrity stress, permanent operations only inside one temp root."""
import hashlib
import importlib
import json
from pathlib import Path
import random
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
ops=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.fileops')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    seed=int(sys.argv[sys.argv.index('--seed')+1]) if '--seed' in sys.argv else time.time_ns()&0xffffffff
    randomizer=random.Random(seed);started=time.monotonic();cases=0;total_bytes=0
    print(json.dumps({'event':'operations.soak.start','seed':seed}),flush=True)
    # 64 seeded rounds fit the leased runner's 180-second bound without idle padding.
    with tempfile.TemporaryDirectory(prefix='pfc-ops-soak-') as raw:
        root=Path(raw).resolve();sentinel=root/'protected.bin';sentinel.write_bytes(b'KEEP')
        for round_ in range(64):
            area=root/f'round-{round_:03}';area.mkdir()
            source=area/'source';target=area/'target';moved=area/'moved'
            source.mkdir();target.mkdir();moved.mkdir()
            entries=[]
            for n in range(randomizer.randint(3,12)):
                name=f'{n:03} 報告 # space [test].txt'
                path=source/name;data=randomizer.randbytes(randomizer.randint(0,32768))
                path.write_bytes(data);entries.append((path,hashlib.sha256(data).hexdigest()))
                total_bytes+=len(data)
            result=ops.copy_items([p for p,_ in entries],target)
            assert not result.failures and not result.skipped
            assert all(digest(target/p.name)==hash_ and digest(p)==hash_ for p,hash_ in entries)
            cases+=1
            chosen,hash_=entries[0];old=target/chosen.name
            old.write_bytes(b'ORIGINAL')
            result=ops.copy_items([chosen],target,lambda *_:'skip')
            assert result.skipped==[chosen] and old.read_bytes()==b'ORIGINAL';cases+=1
            result=ops.copy_items([chosen],target,lambda *_:'keep_both')
            assert not result.failures and old.read_bytes()==b'ORIGINAL'
            sibling=target/(chosen.stem+' (2)'+chosen.suffix)
            assert digest(sibling)==hash_;cases+=1
            result=ops.copy_items([chosen],target,lambda *_:'replace')
            assert not result.failures and digest(old)==hash_;cases+=1
            result=ops.copy_items([p for p,_ in entries],target,lambda *_:'cancel')
            assert len(result.skipped)==len(entries) and not result.completed;cases+=1
            result=ops.move_items([target/p.name for p,_ in entries],moved)
            assert not result.failures
            assert all(not (target/p.name).exists() and digest(moved/p.name)==h for p,h in entries);cases+=1
            result=ops.copy_items([chosen],source,lambda *_:'replace')
            assert result.failures and digest(chosen)==hash_;cases+=1
            missing=source/'missing.txt'
            result=ops.copy_items([missing,chosen],target,continue_on_error=True)
            assert len(result.failures)==1 and result.completed==[chosen] and digest(target/chosen.name)==hash_;cases+=1
            result=ops.delete_items([area])
            assert not result.failures and not area.exists() and sentinel.read_bytes()==b'KEEP';cases+=1
        assert sentinel.read_bytes()==b'KEEP'
    print(json.dumps({'event':'operations.soak.passed','seed':seed,'cases':cases,'input_bytes':total_bytes,
                      'seconds':round(time.monotonic()-started,3)}),flush=True)


if __name__=='__main__':main()
