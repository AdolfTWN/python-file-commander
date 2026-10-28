"""Same real copy task with explicit simulated slow I/O; measure UI dispatch."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0,os.environ.get('PFC_AUDIT_ROOT',str(Path(__file__).resolve().parents[1])))
pfc=importlib.import_module('pycommander.app')
with tempfile.TemporaryDirectory(prefix='pfc-transfer-bench-') as raw:
    root=Path(raw);source=root/'Source';source.mkdir();destination=root/'Destination'
    items=[]
    for index in range(5):
        item=source/(str(index)+'.bin');item.write_bytes(bytes([index])*65536);items.append(item)
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True;pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();app.auto_font_size_var.set(False);app.update()
    ticks=[];active=True;started=time.perf_counter()
    def tick():
        if active:ticks.append(time.perf_counter()-started);app.after(20,tick)
    app.after(20,tick)
    def slow(items,target,resolver,continue_errors):
        time.sleep(.12*len(items));return pfc.copy_items(items,target,resolver,continue_errors)
    try:
        result=app._execute_transfer('Copy',slow,items,destination,confirm=False)
        elapsed=time.perf_counter()-started;active=False
        assert result.completed==items and not result.failures
        assert all((destination/item.name).read_bytes()==item.read_bytes() for item in items)
        # No app.update after return: ticks count only dispatch during the task.
        gaps=[b-a for a,b in zip([0]+ticks,ticks+[elapsed])]
        print(json.dumps(dict(files=5,bytes=327680,simulated_delay_per_item=.12,
            task_seconds=elapsed,ui_ticks=len(ticks),max_dispatch_gap_seconds=max(gaps))))
    finally:app.close_app()
