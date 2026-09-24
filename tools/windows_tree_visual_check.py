"""Leased, interactive Windows desktop only: real wheel + GDI frame evidence.

No accounts/network or real user folders. Compare old/new portable modules using
the same fixture. A local pass is not a substitute for the reporter's retest.
"""
import ctypes
from ctypes import wintypes as W
import importlib
import json
import os
from pathlib import Path
import struct
import sys
import threading
import time

if os.name != 'nt': raise SystemExit('Windows interactive desktop required')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pfc')
out=Path(sys.argv[2] if len(sys.argv)>2 else 'tree-visual-evidence')
out.mkdir(exist_ok=True)
u=ctypes.WinDLL('user32',use_last_error=True);g=ctypes.WinDLL('gdi32',use_last_error=True)
u.GetDC.argtypes=[W.HWND];u.GetDC.restype=W.HDC
u.ReleaseDC.argtypes=[W.HWND,W.HDC]
g.CreateCompatibleDC.argtypes=[W.HDC];g.CreateCompatibleDC.restype=W.HDC
g.CreateCompatibleBitmap.argtypes=[W.HDC,ctypes.c_int,ctypes.c_int];g.CreateCompatibleBitmap.restype=W.HBITMAP
g.SelectObject.argtypes=[W.HDC,W.HGDIOBJ];g.SelectObject.restype=W.HGDIOBJ
g.BitBlt.argtypes=[W.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.HDC,ctypes.c_int,ctypes.c_int,W.DWORD]
g.GetDIBits.argtypes=[W.HDC,W.HBITMAP,W.UINT,W.UINT,ctypes.c_void_p,ctypes.c_void_p,W.UINT]
g.DeleteObject.argtypes=[W.HGDIOBJ];g.DeleteDC.argtypes=[W.HDC]
u.SetCursorPos.argtypes=[ctypes.c_int,ctypes.c_int]
u.mouse_event.argtypes=[W.DWORD,W.DWORD,W.DWORD,W.DWORD,ctypes.c_size_t]

app=pfc.tk.Tk();app.geometry('900x800+20+20');app.title('PFC — offline wheel rendering check')
app.attributes('-topmost',True)
pfc.configure_ttk_theme(app,pfc.COLOR_SCHEMES['light_grey'])
font=pfc.tkfont.nametofont('TkDefaultFont');font.configure(size=21)
style=pfc.ttk.Style(app);style.configure('Treeview',font=font,rowheight=49)
nav=pfc.RootFolderTree(app,lambda path:None,lambda e:None);nav.pack(fill='both',expand=True)
tree=nav.tree
nav.after_cancel(nav._poll_job);nav.load=lambda *a,**kw:None
nav._probe_visible=lambda:None
tree.delete(*tree.get_children(nav.pc));nav.paths.clear();nav.nodes.clear()
parent=nav.pc
for name in ('Drive','Users','Demo'):
    parent=tree.insert(parent,'end',text=name,open=True);nav.paths[parent]=Path('C:/Fixture')/name
leaves=[]
for n in range(70):
    iid=tree.insert(parent,'end',text=f'Folder {n:02}',open=False)
    nav.paths[iid]=Path('C:/Fixture')/f'Folder {n:02}';leaves.append(iid)
tree.selection_set(leaves[4]);tree.focus(leaves[4]);tree.focus_force()
errors=[];app.report_callback_exception=lambda *exc:errors.append(str(exc))
done=threading.Event();stop=threading.Event();results={}

def longest(values):
    best=();start=None
    for y,match in enumerate(values+[False]):
        if match and start is None:start=y
        if not match and start is not None:
            if y-start>=10 and (not best or y-start>best[1]-best[0]):best=(start,y)
            start=None
    return best

def capture(x,y,w,h,color):
    screen=u.GetDC(None);memory=g.CreateCompatibleDC(screen)
    bitmap=g.CreateCompatibleBitmap(screen,w,h);old=g.SelectObject(memory,bitmap)
    header=struct.pack('<IiiHHIIiiII',40,w,-h,1,32,0,w*h*4,0,0,0,0)
    info=ctypes.create_string_buffer(header);buffer=ctypes.create_string_buffer(w*h*4)
    samples=[];splits=[];valid=0;started=time.monotonic();next_wheel=started+1;steps=0
    # Real OS input, deliberately NOT Treeview.event_generate.
    u.SetCursorPos(x+w-80,y+h//2)
    try:
        while time.monotonic()-started<18 and not stop.is_set():
            now=time.monotonic()
            if now>=next_wheel:
                delta=-120 if steps%6<3 else 120
                u.mouse_event(0x0800,0,0,delta & 0xffffffff,0)
                steps+=1;next_wheel=now+.12
            assert g.BitBlt(memory,0,0,w,h,screen,x,y,0x00CC0020)
            assert g.GetDIBits(memory,bitmap,0,h,buffer,info,0)==h
            raw=buffer.raw
            runs=[]
            for column in (8,w-35):
                runs.append(longest([raw[(row*w+column)*4:(row*w+column)*4+3]==color for row in range(h)]))
            if any(runs):valid+=1
            bad=bool(any(runs) and (not all(runs) or max(abs(a-b) for a,b in zip(*runs))>2))
            if bad:
                splits.append({'at':round(now-started,4),'runs':runs})
                if len(splits)<=12:
                    (out/f'split-{len(splits):02}.bmp').write_bytes(b'BM'+struct.pack('<IHHI',54+len(raw),0,0,54)+header+raw)
            if not samples or len(samples)==100:
                (out/f'frame-{len(samples):03}.bmp').write_bytes(b'BM'+struct.pack('<IHHI',54+len(raw),0,0,54)+header+raw)
            samples.append(round(now-started,4))
            time.sleep(.005)
        elapsed=time.monotonic()-started
        results.update(frames=len(samples),fps=round(len(samples)/elapsed,1),visible_selection_frames=valid,
                       split_frames=len(splits),splits=splits[:20],wheel_events=steps,errors=errors)
        (out/'result.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    except Exception as exc:
        results['error']=str(exc)
    finally:
        g.SelectObject(memory,old);g.DeleteObject(bitmap);g.DeleteDC(memory);u.ReleaseDC(None,screen);done.set()

def begin():
    nav._redraw_lines();tree.focus_force()
    x,y=tree.winfo_rootx(),nav.winfo_rooty()+nav.caption.winfo_height()+12
    w,h=tree.winfo_width(),nav.winfo_height()-nav.caption.winfo_height()-45
    rgb=app.winfo_rgb(style.lookup('FolderNav.Treeview','background',('selected',)))
    color=bytes(round(value/257) for value in reversed(rgb))
    threading.Thread(target=capture,args=(x,y,w,h,color),daemon=True).start()
    check()

def check():
    if done.is_set():app.destroy()
    else:app.after(50,check)

app.after(1200,begin)
try:app.mainloop()
finally:stop.set()
print(json.dumps(results),flush=True)
if results.get('error') or errors or results.get('visible_selection_frames',0)<30 or results.get('wheel_events',0)<50:
    raise SystemExit('INCONCLUSIVE: insufficient capture/input or errors')
if results['split_frames']:raise SystemExit('FAIL: captured split selection')
print('PASS: native Windows wheel frames contain no split selection (fixture only)',flush=True)
