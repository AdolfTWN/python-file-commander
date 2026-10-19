"""Offline native metadata smoke check + injected cloud status UI regression."""
import base64
import ctypes
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
module=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')
cloud=module if module.__name__=='pfc' else importlib.import_module('pycommander.cloudstatus')
icons=module if module.__name__=='pfc' else importlib.import_module('pycommander.icons')

def settle(app,seconds=.2):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.update(); time.sleep(.01)

def capture(window,name):
    window.lift();settle(window,.15)
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/('evidence-cloud-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save('/tmp/pfc-cloud-'+name+'.png')

def comparison_badge(size,state,variant):
    if variant==1:return icons.cloud_badge_png(size,state)
    factor=6;side=size*factor;pixels=bytearray(side*side*4)
    if variant==0:
        old_colors={'online':'#00e5e5','available':'#00a6ff','pinned':'#00a6ff'}
        layers=[]
        for inset,color in ((.02,'#ffffff'),(.075,'#151b23'),(.14,old_colors.get(state,icons.CLOUD_BADGE_COLORS[state][0]))):
            lo,hi=inset,1-inset
            layers.append((((lo,lo),(hi,lo),(hi,hi)),color))
    for points,color in layers:
        icons._paint_polygon(pixels,side,[(x*side,y*side) for x,y in points],icons._hex_rgba(color))
    return icons._rgba_png_downsample(pixels,size,factor)

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw)/'cloud-fixture'; root.mkdir()
    paths=[]
    for state in cloud.CLOUD_LABELS:
        path=root/(state+'.txt'); path.write_text('fixture'); paths.append(path)
    if os.name=='nt':
        hr=ctypes.windll.ole32.CoInitializeEx(None,2)
        try:
            # Ordinary local files must not be falsely labeled as synchronized.
            assert cloud.read_cloud_status(paths[0]) is None
            assert cloud.read_cloud_status(root/'absent.txt') is None
            assert not module.is_hidden(paths[0])
            assert ctypes.windll.kernel32.SetFileAttributesW(str(paths[0]),2)
            try: assert module.is_hidden(paths[0])
            finally: ctypes.windll.kernel32.SetFileAttributesW(str(paths[0]),0x80)
        finally:
            if hr>=0: ctypes.windll.ole32.CoUninitialize()
        print('PASS: native fast property store ABI, ordinary/missing file, Windows hidden attribute',flush=True)
    module.Commander._find_ini_path=staticmethod(lambda:Path(raw)/'pfc.ini')
    module.Commander._sync_auto_start=lambda self,**kw:True
    app=module.Commander(); errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False); app.geometry('1500x760')
        app.cloud_status=cloud.CloudStatusCache([root],lambda p:Path(p).stem)
        pane=app.left_tabs.current(); pane.navigate(root); app.set_active(pane)
        settle(app,.7)
        rows=pane.tree.get_children()
        assert all(app.cloud_status.get(path)==path.stem for path in paths)
        for iid in rows:
            path=Path(pane.tree.item(iid,'tags')[0])
            assert 'OneDrive:' in pane._tooltip_name(iid)
            assert cloud.CLOUD_LABELS[path.stem] in pane._tooltip_name(iid)
            assert cloud.CLOUD_DETAILS[path.stem] in pane._tooltip_name(iid)
        images=[]
        display=tk.Toplevel(app); display.title('OneDrive badge regression fixture (not live sync)')
        # Real Windows Known Folder images plus explicit blue/purple fixtures.
        # Same paths, states and scales across thin / raised / adaptive edges.
        states=tuple(cloud.CLOUD_LABELS)
        native_get=icons.ShellIconProvider.get
        for scale in (100,175,200):
            for child in display.winfo_children():child.destroy()
            images.clear();size=round(24*scale/100)
            originals=[]
            for col in range(7):
                native=None
                if os.name=='nt' and col<3:
                    native=icons.ShellIconProvider(size)._load(Path.home()/('Desktop','Pictures','Documents')[col],True)
                if native is None:
                    native=tk.PhotoImage(width=size,height=size)
                    native.put(('#168dd2','#a23acb','#d49b12')[col%3],to=(0,size//4,size,size))
                originals.append(native)
            images.extend(originals)
            stacked=21*(size+max(4,round(size*.3))+6)+30>display.winfo_screenwidth()-30
            for variant,title in enumerate(('Before: thin diagonal','White bevel + shadow','Candidate: bevel + adaptive lightness')):
                group=ttk.Frame(display);group.grid(row=variant if stacked else 0,column=0 if stacked else variant,padx=5,sticky='n')
                ttk.Label(group,text=title).grid(row=0,column=0,columnspan=7)
                for col,label in enumerate(('online','local','kept','pending','error','pause','warn')):
                    ttk.Label(group,text=label).grid(row=1,column=col,padx=2)
                for row,bg in enumerate(('#eeeeee','#20242b','#0078d4','#eeeeee'),2):
                    for col,state in enumerate(states):
                        provider=icons.ShellIconProvider(size)
                        base=originals[col]
                        vcs={3:'modified',4:'clean'}.get(row)
                        if row==5:
                            base=tk.PhotoImage(width=size,height=size)
                            base.put(icons.CLOUD_BADGE_COLORS[state][0],to=(0,0,size,size))
                        if variant==2:
                            with patch.object(provider,'_load',return_value=base),patch.dict(native_get.__globals__,os=SimpleNamespace(name='nt',path=os.path)):
                                picture=provider.get(paths[col],True,vcs,state)
                        else:
                            if vcs:base=provider._with_overlay(base,vcs,compact=True)
                            picture=provider._with_text_gap(base)
                            diameter,x=icons.cloud_badge_geometry(size)
                            badge=tk.PhotoImage(data=base64.b64encode(comparison_badge(diameter,state,variant)).decode(),format='png')
                            picture.tk.call(str(picture),'copy',str(badge),'-to',x,0,'-compositingrule','overlay')
                        images.append(picture)
                        tk.Label(group,image=picture,bg=bg,padx=3,pady=4).grid(row=row,column=col,sticky='ew')
            display.update_idletasks()
            display.geometry(f'{display.winfo_reqwidth()}x{display.winfo_reqheight()}+0+0');settle(app)
            capture(display,str(scale))
        display.withdraw()
        native_get=icons.ShellIconProvider.get
        for size in (16,24,42,48,80):
            base=tk.PhotoImage(width=size,height=size);base.put('#ab9067',to=(0,0,size,size))
            base.put('#00dd55',to=(0,size*3//4,size//4,size))
            base.put('#dd00aa',to=(size*3//4,size*3//4,size,size))
            for vcs in (None,'clean','modified'):
                provider=icons.ShellIconProvider(size)
                with patch.object(provider,'_load',return_value=base),patch.dict(native_get.__globals__,os=SimpleNamespace(name='nt',path=os.path)):
                    image=provider.get(paths[0],False,vcs,'available')
                for y in range(size*3//4,size):
                    for x in range(size):assert image.get(x,y)==base.get(x,y), 'PFC overwrote reserved bottom corners'
                diameter,x0=icons.cloud_badge_geometry(size)
                assert image.width()==provider.blank.width(), 'Status must not change row width'
                plain=provider._with_overlay(base,vcs,compact=True) if vcs else base
                for y in range(size):
                    for x in range(size):
                        if x<x0 or y>=diameter:assert image.get(x,y)==plain.get(x,y), 'Cloud must stay in attached NE corner'
                    for x in range(size,image.width()):assert image.transparency_get(x,y), 'Cloud must not detach into filename space'
                colors=[image.get(x,y) for y in range(diameter) for x in range(x0,size)]
                assert any(min(rgb)>220 for rgb in colors), 'White diagonal bevel must remain visible at every size'
                assert any(max(rgb)<90 for rgb in colors), 'Dark lower lip must remain visible at every size'
                assert any(rgb[0]<80 and rgb[1]>150 and rgb[2]>180 for rgb in colors), 'Bright cyan-blue face must survive the bevel'
                if vcs:assert image.get(size//4,size//4)!=base.get(size//4,size//4), 'VCS must be top-left'
            for state,(face,_) in icons.CLOUD_BADGE_COLORS.items():
                base=tk.PhotoImage(width=size,height=size);base.put(face,to=(0,0,size,size))
                provider=icons.ShellIconProvider(size)
                with patch.object(provider,'_load',return_value=base) as load,patch.dict(native_get.__globals__,os=SimpleNamespace(name='nt',path=os.path)):
                    image=provider.get(paths[0],False,cloud=state)
                    assert provider.get(paths[0],False,cloud=state) is image
                    assert load.call_count==1, 'Cached status must not repeat Shell lookup or sampling'
                samples=[base.get(0,0)]*3
                lighter=icons.cloud_badge_needs_lightening(state,samples)
                diameter,x0=icons.cloud_badge_geometry(size)
                badge=tk.PhotoImage(data=base64.b64encode(icons.cloud_badge_png(diameter,state,lighter)).decode(),format='png')
                expected=provider._with_text_gap(base)
                expected.tk.call(str(expected),'copy',str(badge),'-to',x0,0,'-compositingrule','overlay')
                for y in range(size):
                    for x in range(size):assert image.get(x,y)==expected.get(x,y), 'Adaptive face must match bounded lighter variant'
                assert base.get(size-1,0)==base.get(0,size-1), 'Never recolor the source icon'
        for key in ('small','175','xl'):
            app.font_size_var.set(key);app.apply_font_size(save=False);settle(app)
            app.cloud_status.due=0;settle(app,.3)
            rows=pane.tree.get_children()
            pane.tree.selection_set(rows[0]);settle(app)
            assert {Path(pane.tree.item(i,'tags')[0]) for i in rows}==set(paths)
        settle(app)
        original_ids=pane.tree.get_children()
        app.onedrive_overlay_var.set(False); app.apply_column_settings(); settle(app)
        assert all('OneDrive:' not in pane._tooltip_name(iid) for iid in rows)
        app.onedrive_overlay_var.set(True); app.apply_column_settings(); settle(app)
        pane._drag_press_item=rows[0]
        assert not any(p is pane for p,_,_ in app._visible_cloud_rows([pane]))
        pane._drag_press_item=None
        assert pane.tree.get_children()==original_ids
        assert not errors,errors
        if '--pause' in sys.argv: settle(app,20)
        print('PASS: thin/raised/adaptive triangles on native and matching-color fixtures at 100/175/200%; attached corner, bevel/shadow, adaptive cached face, intact source icon, lower corners, fixed width, tooltip and drag deferral',flush=True)
        print('NOTE: offline VM does not validate real OneDrive provider sync transitions.',flush=True)
    finally: app.destroy()
