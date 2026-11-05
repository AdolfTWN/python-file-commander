"""Repeated space context menus and immediate scale/close use bounded Tk work."""
import importlib
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
module=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.spaceanalyzer')
root=tk.Tk();root.geometry('1000x700');errors=[];failures=[];window=None
root.report_callback_exception=lambda *exc:errors.append(exc[0].__name__)
root.tk.call('set','::space_errors',())
root.tk.call('proc','bgerror','message','lappend ::space_errors $message')
try:
    with tempfile.TemporaryDirectory(prefix='pfc-space-lifetime-') as raw:
        folder=Path(raw);(folder/'fixture.bin').write_bytes(b'fixture')
        nested=folder/'cancel-case';nested.mkdir();child=nested/'last';child.mkdir()
        original_scan=module.scan_space;cancel=threading.Event()
        def interrupted(path,event):
            if path==child:event.set();raise InterruptedError
            return original_scan(path,event)
        with patch.object(module,'scan_space',interrupted):
            try:original_scan(nested,cancel)
            except InterruptedError:pass
            else:raise AssertionError('Final-child cancellation was swallowed')
        window=module.SpaceAnalyzerWindow(root,folder,lambda *_:None,lambda *_:False,{})
        deadline=time.monotonic()+5
        while window.root_node is None:
            root.update();time.sleep(.005)
            assert time.monotonic()<deadline,'Scan did not finish'
        node=next(n for n in window.root_node.children if n.path.name=='fixture.bin')
        commands=[];menus=[];invoked=[]
        with patch.object(window,'_node_at',return_value=node),patch.object(tk.Menu,'tk_popup'),\
                patch.object(window,'_confirm_remove',side_effect=lambda *a,**k:invoked.append((a,k))):
            for _ in range(40):
                window._right_click(SimpleNamespace(x=2,y=2,x_root=5,y_root=5))
                root.update()
                choices=[w for w in window.winfo_children() if isinstance(w,tk.Menu)]
                choices[-1].invoke(0)
                menus.append(len(choices))
                commands.append(len(root.tk.splitlist(root.tk.call('info','commands'))))
        assert len(invoked)==40 and all(args==(node,) and kwargs=={'permanent':False} for args,kwargs in invoked)
        if max(menus[5:])!=min(menus[5:]):failures.append(('Context menu count grows',menus[0],menus[-1]))
        if max(commands[5:])-min(commands[5:])>2:failures.append(('Tcl commands grow',commands[5],commands[-1]))
        window.apply_scale(1.5);window.close();window=None
        deadline=time.monotonic()+.2
        while time.monotonic()<deadline:root.update();time.sleep(.005)
        native=root.tk.splitlist(root.tk.call('set','::space_errors'))
        if native:failures.append(('Native callbacks after close',len(native)))
        assert not errors,errors
        assert not failures,failures
        print('PASS: 40 context menu openings retain one menu/bounded commands; scale-close leaves no orphaned callback')
finally:
    if window is not None:window.close()
    root.destroy()
