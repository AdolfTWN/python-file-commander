"""Real FlowToolbar manual reflow, removed groups and recursive destruction."""
import importlib
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
module=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.flowlayout')
app=tk.Tk();app.geometry('700x180');errors=[];failures=[]
app.report_callback_exception=lambda *exc:errors.append(exc[0].__name__)
app.tk.call('set','::flow_errors',());app.tk.call('proc','bgerror','message','lappend ::flow_errors $message')
try:
    toolbar=module.FlowToolbar(app);toolbar.pack(fill='x')
    first=ttk.Button(toolbar,text='First');second=ttk.Button(toolbar,text='Second')
    for button in (first,second):toolbar.add(button,minimum=lambda b=button:len(b.cget('text'))*12)
    app.update();toolbar.schedule();pending=toolbar._flow_job
    toolbar.layout()
    if pending in app.tk.splitlist(app.tk.call('after','info')):failures.append('Manual layout orphaned its pending idle token')
    first.destroy();toolbar.schedule();app.update()
    if any(group[0] is first for group in toolbar.groups):failures.append('Destroyed group remains measurable')
    second.bind('<Destroy>',lambda _event:toolbar.layout(),add='+')
    toolbar.schedule();toolbar.destroy()
    end=time.monotonic()+.2
    while time.monotonic()<end:app.update();time.sleep(.003)
    assert not errors,('Python callback failures',errors,failures)
    native=app.tk.splitlist(app.tk.call('set','::flow_errors'))
    assert not native,('Native orphaned callbacks',native)
    assert not failures,failures
    print('PASS: manual reflow consumes pending idle; removed groups and teardown cannot relayout dead controls')
finally:app.destroy()
