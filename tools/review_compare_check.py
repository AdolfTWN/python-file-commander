"""Task-based large compare, draft review, workbook and archive GUI checks."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import font, messagebox, simpledialog, ttk
from unittest import mock
import zipfile
import subprocess
import configparser
from types import SimpleNamespace
import shutil

if os.name == 'nt':
    import faulthandler
    faulthandler.dump_traceback_later(45, repeat=True)

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
portable=len(sys.argv)>1 and sys.argv[1]=='pfc'
api=importlib.import_module('pfc' if portable else 'pycommander.reviewui')
tables=api if portable else importlib.import_module('pycommander.workbookui')
compare=api if portable else importlib.import_module('pycommander.compare')
app=tk.Tk();app.geometry('1360x850+0+0');errors=[];timings={}
app.report_callback_exception=lambda *args:errors.append(str(args))
print('Compare fixture: Tk ready', flush=True)


def pump(seconds=.1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.005)


def until(predicate,seconds=90):
    end=time.monotonic()+seconds
    while not predicate():
        if time.monotonic()>end:raise AssertionError('Timed out: '+str(errors))
        pump(.025)


def open_context(widget, x, y):
    # Windows tk_popup enters a native modal loop. A statement after
    # event_generate cannot dismiss it; send Escape from a bounded timer like
    # the existing native menu fixtures, then inspect/invoke its real commands.
    timer = None
    done = None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        import threading
        thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        user = ctypes.WinDLL('user32')
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user.EnumThreadWindows.argtypes = [wintypes.DWORD, callback_type, wintypes.LPARAM]
        user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        done = threading.Event()
        def dismiss():
            # Target only this fixture's UI thread. Synthetic global Escape can
            # be delivered to Explorer instead of a background scheduled task.
            @callback_type
            def cancel(hwnd, _):
                user.PostMessageW(hwnd, 0x001F, 0, 0)  # WM_CANCELMODE
                return True
            for _ in range(20):
                if done.wait(.15): return
                user.EnumThreadWindows(thread_id, cancel, 0)
        timer = threading.Thread(target=dismiss, daemon=True)
        timer.start()
    widget.event_generate('<Button-3>', x=x, y=y)
    if timer is not None:
        done.set(); timer.join()
    pump()


def shot(name):
    app.lift();app.focus_force();pump(.3)
    if os.name=='nt':
        if name not in ('text-1.75-760','workbook','archive-draft','folder-pair','text-light','text-dark','workbook-empty'):return
        import ctypes as c
        from ctypes import wintypes as w
        import struct
        u=c.WinDLL('user32');g=c.WinDLL('gdi32')
        u.GetAncestor.argtypes=[w.HWND,w.UINT];u.GetAncestor.restype=w.HWND
        u.SetForegroundWindow.argtypes=[w.HWND]
        u.SetForegroundWindow(u.GetAncestor(app.winfo_id(),2));pump(.4)
        u.GetDC.argtypes=[w.HWND];u.GetDC.restype=w.HDC
        u.ReleaseDC.argtypes=[w.HWND,w.HDC]
        g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
        g.CreateCompatibleBitmap.argtypes=[w.HDC,c.c_int,c.c_int];g.CreateCompatibleBitmap.restype=w.HBITMAP
        g.SelectObject.argtypes=[w.HDC,w.HGDIOBJ];g.SelectObject.restype=w.HGDIOBJ
        g.DeleteObject.argtypes=[w.HGDIOBJ];g.DeleteDC.argtypes=[w.HDC]
        g.BitBlt.argtypes=[w.HDC,c.c_int,c.c_int,c.c_int,c.c_int,w.HDC,c.c_int,c.c_int,w.DWORD]
        g.GetDIBits.argtypes=[w.HDC,w.HBITMAP,w.UINT,w.UINT,c.c_void_p,c.c_void_p,w.UINT]
        width,height=app.winfo_width(),app.winfo_height();screen=u.GetDC(None);dc=g.CreateCompatibleDC(screen)
        bitmap=g.CreateCompatibleBitmap(screen,width,height);old=g.SelectObject(dc,bitmap)
        try:
            assert g.BitBlt(dc,0,0,width,height,screen,app.winfo_rootx(),app.winfo_rooty(),0x00CC0020)
            g.SelectObject(dc,old)
            info=struct.pack('<IiiHHIIiiII',40,width,height,1,32,0,width*height*4,0,0,0,0)
            header=c.create_string_buffer(info);pixels=c.create_string_buffer(width*height*4)
            assert g.GetDIBits(dc,bitmap,0,height,pixels,header,0)==height
            assert len(set(pixels.raw))>16, 'Blank native display capture; not visual acceptance'
            (Path(__file__).parent/('evidence-'+name+'.bmp')).write_bytes(struct.pack('<2sIHHI',b'BM',54+len(pixels.raw),0,0,54)+info+pixels.raw)
        finally:g.SelectObject(dc,old);g.DeleteObject(bitmap);g.DeleteDC(dc);u.ReleaseDC(None,screen)
        return
    if '--screenshots' not in sys.argv:return
    from PIL import ImageGrab
    root=Path(tempfile.gettempdir())/'pfc-review-evidence';root.mkdir(exist_ok=True)
    ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/(name+'.png'))


with tempfile.TemporaryDirectory(prefix='pfc-review-check-') as raw:
    root=Path(raw);a=root/'Left.md';b=root/'Right.md'
    text=''.join(f'{n:06} | Project review | '+('sample '*22)+'\n' for n in range(115000))
    assert len(text.encode())<=20*1024*1024
    a.write_bytes(text.encode());b.write_bytes(text.replace('100000 | Project review','100000 | CHANGED').encode())
    before=(a.read_bytes(),b.read_bytes());started=time.monotonic()
    print('Compare fixture: large text loading', flush=True)
    view=api.ReviewCompare(app,a,b);view.pack(fill='both',expand=True)
    until(lambda:not view.busy)
    assert view.alignment,view.status.cget('text')
    print('Compare fixture: large text aligned', flush=True)
    timings['20MiB_load_diff_seconds']=round(time.monotonic()-started,3)
    assert len(view.alignment.differences)==1
    started=time.monotonic();view.next();pump()
    timings['navigation_seconds_including_100ms_pump']=round(time.monotonic()-started,3)
    assert view.top==100000
    assert len(view.widgets[0].get('1.0','end'))<200000
    view.mark_reviewed();assert len(view.checked)==1
    view.take(0);until(lambda:not view.busy)
    assert view.texts[0]==view.texts[1] and b.read_bytes()==before[1]
    view.undo();until(lambda:not view.busy);assert view.texts[1]!=view.texts[0]
    view.redo();until(lambda:not view.busy)
    with mock.patch.object(messagebox,'askyesno',return_value=True):view.save_side(1)
    until(lambda:not view.busy);assert a.read_bytes()==b.read_bytes()
    view.search_var.set('NOT_A_REAL_MATCH')
    view._find_offset=10
    with mock.patch.object(simpledialog,'askstring',side_effect=AssertionError('No match must not prompt replace')):view.replace()
    # A cancelled generation must never apply an old alignment to a new draft.
    view.change(1,view.texts[1]+'new tail');view.cancel();saved=view.texts[1]
    view.take(0);assert view.texts[1]==saved
    view.recompare();until(lambda:not view.busy)
    view.edit(1);editor=view._editors[0];view.edit(0);assert len(view._editors)==1
    with mock.patch.object(messagebox,'askyesno',return_value=True):editor.close()
    with mock.patch.object(messagebox,'askyesno',return_value=False):view.reload_sources()
    assert view.texts[1]==saved and not view.busy
    with mock.patch.object(messagebox,'askyesno',return_value=True):view.reload_sources()
    until(lambda:not view.busy)
    assert view.texts[0]==view.texts[1] and not view.history
    view.destroy();pump()
    a.write_bytes(''.join(f'{n}\n' for n in range(1000000)).encode())
    b.write_bytes(a.read_bytes().replace(b'999999\n',b'LAST-CHANGE\n'))
    started=time.monotonic();view=api.ReviewCompare(app,a,b);view.pack(fill='both',expand=True)
    until(lambda:not view.busy)
    assert view.alignment,view.status.cget('text')
    timings['million_lines_seconds']=round(time.monotonic()-started,3)
    view.next();assert view.top==999999
    view.destroy();pump()
    # Million-character single lines reveal the changed position, not only head.
    a.write_text('x'*1000000+'LEFT\n',encoding='utf-8');b.write_text('x'*1000000+'RIGHT\n',encoding='utf-8')
    view=api.ReviewCompare(app,a,b);view.pack(fill='both',expand=True);until(lambda:not view.busy)
    view.next();assert view.column[0]>999000 and 'LEFT' in view.widgets[0].get('1.0','end')
    for scale,width in ((1,1360),(1.5,950),(1.75,760),(2,760)):
        for name in ('TkDefaultFont','TkTextFont','TkFixedFont','TkMenuFont','TkHeadingFont'):
            font.nametofont(name).configure(size=round(10*scale))
        view.apply_scale(scale)
        app.geometry(f'{width}x850+0+0');pump(.2)
        assert view.search.winfo_width()>80,(scale,view.search.winfo_width())
        assert view.body.winfo_height()>500
        for scrollbar,frame in zip(view.xbars,view.frames):
            assert scrollbar.winfo_ismapped()
            assert scrollbar.winfo_y()+scrollbar.winfo_height()<=frame.winfo_height()
        assert view.status.winfo_ismapped() and view.status.winfo_rooty()<app.winfo_rooty()+app.winfo_height()
        shot(f'text-{scale}-{width}')
    view.destroy();pump()
    a.write_text('# Review heading\n\n**Important source**\n',encoding='utf-8')
    b.write_text('# Review heading\n\n**Important draft**\n',encoding='utf-8')
    view=api.ReviewCompare(app,a,b);view.pack(fill='both',expand=True);until(lambda:not view.busy)
    view.toggle_preview()
    until(lambda:'Important source' in view.preview_text.get('1.0','end'))
    assert view.preview_text.tag_ranges('markdown_bold') and view.preview_text.cget('state')=='disabled'
    view.active_side=1;view.update_preview()
    until(lambda:'Important draft' in view.preview_text.get('1.0','end'))
    view.toggle_preview();view.destroy();pump()
    for name in ('TkDefaultFont','TkTextFont','TkFixedFont','TkMenuFont','TkHeadingFont'):font.nametofont(name).configure(size=11)
    app.geometry('1360x850+0+0')
    # Real key events belong to Compare, never the Commander's global F3/F8.
    a.write_text('needle one\nneedle two\n');b.write_text('needle one\nneedle changed\n')
    leaked=[]
    app.bind_all('<F3>',lambda e:leaked.append('main preview'))
    app.bind_all('<F8>',lambda e:leaked.append('main VCS'))
    for kind in ('Review','Text'):
        cw=compare.CompareWindow(app,configparser.ConfigParser(),lambda:None)
        frame=cw.add(a,b,requested=kind);target=getattr(frame,'view',frame)
        if kind=='Review':until(lambda:not frame.busy)
        target.search_var.set('needle');target.search.focus_force();pump()
        target.search.event_generate('<F3>');pump()
        first=target._find_offset if kind=='Review' else target.match_index
        target.search.event_generate('<F3>');pump()
        second=target._find_offset if kind=='Review' else target.match_index
        assert second!=first
        target.search.event_generate('<Shift-F3>');pump()
        assert (target._find_offset if kind=='Review' else target.match_index)==first
        target.search.event_generate('<F8>');pump()
        target.search.event_generate('<Control-f>');pump();assert cw.focus_get() is target.search
        if kind=='Review':
            frame.edit(0);editor=frame._editors[0];editor.text.focus_force();pump()
            editor.text.event_generate('<F3>');pump();editor.close()
        assert not leaked,leaked
        cw.close();pump()
    app.unbind_all('<F3>');app.unbind_all('<F8>')
    # Real text tags: readable dark/light highlights and selection precedence.
    colors=api if portable else importlib.import_module('pycommander.tabs')
    a.write_text('# Monitor review\nModel: Alpha 100\nunchanged\nleft-only note\n',encoding='utf-8')
    b.write_text('# Monitor review\nModel: Alpha 200\nunchanged\n',encoding='utf-8')
    text_view=compare.TextCompare(app,a,b);text_view.pack(fill='both',expand=True)
    for theme in ('light','dark'):
        text_view.view.apply_color_scheme(colors.color_scheme(theme));text_view.view.next();pump()
        text=text_view.view.left
        assert text.tag_cget('inline_diff','foreground')!='#ffffff'
        assert not text.tag_cget('current','background')
        assert text.tag_ranges('inline_diff')
        assert text.tag_ranges('orphan') and text_view.view.right.tag_ranges('gap')
        assert text.tag_names()[-1]=='sel'
        shot('text-'+theme)
    text_view.destroy();pump()
    # Read-only workbook UI exposes the change, full cell and rule modes.
    ca=root/'left.csv';cb=root/'right.csv'
    ca.write_text('id,value\none,10\ntwo,20\n');cb.write_text('id,value\none,11\ntwo,21\n')
    grid=tables.WorkbookCompare(app,ca,cb);grid.pack(fill='both',expand=True)
    until(lambda:grid.books is not None and grid._rows_job is None)
    assert len(grid.filtered)==6 and grid.difference_count==2,grid.status.cget('text')
    grid.only.set(True);grid.filter();until(lambda:grid._rows_job is None)
    assert len(grid.filtered)==2
    assert grid.rows[grid.filtered[0]][0]=='B2';shot('workbook')
    grid.search_var.set('B');grid.find_next();until(lambda:grid._rows_job is None)
    first=grid.tree.selection();grid.find_next();assert grid.tree.selection()!=first
    grid.find_previous();assert grid.tree.selection()==first
    grid.destroy();pump()
    for path,value in ((root/'left.xlsx','10'),(root/'right.xlsx','11')):
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" r:id="one"/><sheet name="Review" r:id="two" state="hidden"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="one" Target="worksheets/sheet1.xml"/><Relationship Id="two" Target="worksheets/sheet2.xml"/></Relationships>')
            for n in (1,2):z.writestr(f'xl/worksheets/sheet{n}.xml',f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1"><f>1+9</f><v>{value}</v></c></row></sheetData></worksheet>')
    grid=tables.WorkbookCompare(app,root/'left.xlsx',root/'right.xlsx');grid.pack(fill='both',expand=True)
    until(lambda:grid.books is not None and grid._rows_job is None)
    assert list(grid.sheets.cget('values'))==['Data','Review']
    assert len(grid.filtered)==1
    grid.sheet.set('Review');grid.load_sheet();until(lambda:grid._rows_job is None)
    assert grid.selected[0]['state']=='hidden'
    shot('workbook')
    grid.cell_mode.set('Formulas');grid.filter();until(lambda:grid._rows_job is None)
    assert grid.filtered and grid.difference_count==0
    grid.only.set(True);grid.filter();until(lambda:grid._rows_job is None)
    assert not grid.filtered and grid.empty.winfo_ismapped()
    assert 'No value/formula differences' in grid.empty_text.cget('text')
    shot('workbook-empty')
    grid.show_all_button.invoke();until(lambda:grid._rows_job is None)
    assert grid.filtered and not grid.empty.winfo_ismapped()
    grid.destroy();pump()
    # Strict OOXML is not an empty workbook; equal first sheets stay inspectable.
    for p in (root/'strict-left.xlsx',root/'strict-right.xlsx'):
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('xl/workbook.xml','<workbook xmlns="http://purl.oclc.org/ooxml/spreadsheetml/main" xmlns:r="http://purl.oclc.org/ooxml/officeDocument/relationships"><sheets><sheet name="Monitor list" r:id="one"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="one" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://purl.oclc.org/ooxml/spreadsheetml/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Monitor 型號</t></is></c><c r="B1"><v>200</v></c></row></sheetData><mergeCells><mergeCell ref="A2:C2"/></mergeCells></worksheet>')
    grid=tables.WorkbookCompare(app,root/'strict-left.xlsx',root/'strict-right.xlsx');grid.pack(fill='both',expand=True)
    until(lambda:grid.books is not None and grid._rows_job is None)
    assert len(grid.rows)==2 and len(grid.filtered)==2 and grid.difference_count==0
    assert grid.selected[0]['merged']==['A2:C2']
    for name in ('TkDefaultFont','TkTextFont','TkFixedFont','TkMenuFont','TkHeadingFont'):font.nametofont(name).configure(size=18)
    app.geometry('950x850+0+0');grid.apply_scale(1.75);pump()
    assert grid.search.winfo_width()>100 and grid.only_button.winfo_ismapped()
    assert grid.tree.winfo_height()>600
    assert grid.tree.bbox(grid.tree.get_children()[0])[3]>=font.nametofont('TkDefaultFont').metrics('linespace')+6
    shot('workbook');grid.destroy();pump()
    for name in ('TkDefaultFont','TkTextFont','TkFixedFont','TkMenuFont','TkHeadingFont'):font.nametofont(name).configure(size=11)
    app.geometry('1360x850+0+0')
    # Folder/ZIP/7z: right-click bases are side-specific; files are selected
    # independently, and nested labels retain both different logical names.
    roots=[root/'source-left',root/'source-right']
    for r,version,name,value in ((roots[0],'version-a','old name.md','left'),(roots[1],'version-b','new name.md','right')):
        (r/version).mkdir(parents=True);(r/version/name).write_text(value)
    def pair_factory(host,l,r,**kw):return 'Text',compare.TextCompare(host,l,r,**kw)
    containers=[tuple(roots)]
    for suffix in ('zip','7z'):
        seven=shutil.which('7z') or shutil.which('7zz')
        if os.name=='nt' and not seven:
            candidate=Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'7-Zip/7z.exe'
            if candidate.is_file():seven=str(candidate)
        if suffix=='7z' and not seven:continue
        archives=[]
        for r in roots:
            path=root/(r.name+'.'+suffix)
            if suffix=='zip':
                with zipfile.ZipFile(path,'w') as z:
                    for f in r.rglob('*.md'):z.write(f,f.relative_to(r).as_posix())
            else:subprocess.run([seven,'a',str(path),'.'],cwd=r,check=True,stdout=subprocess.DEVNULL)
            archives.append(path)
        containers.append(tuple(archives))
    for left,right in containers:
        wrapped=left.is_file()
        parent=(compare.ArchiveReviewCompare(app,left,right,compare.FolderCompare,pair_factory,None) if wrapped else
                compare.FolderCompare(app,left,right,pair_factory))
        parent.pack(fill='both',expand=True)
        if wrapped:until(lambda:not parent.busy);folder=parent.inner;assert folder,parent.status.cget('text')
        else:folder=parent
        until(lambda:not folder._scanning);pump()
        for side,version in (('left','version-a'),('right','version-b')):
            tree=getattr(folder,side+'_tree');other='right' if side=='left' else 'left'
            other_root=getattr(folder,other+'_root')
            iid=next(i for i,key in folder.item_keys.items() if key==version)
            tree.see(iid);tree.selection_set(iid);tree.focus(iid);tree.focus_force();pump()
            x,y,w,h=tree.bbox(iid);open_context(tree,x+20,y+h//2)
            menu=folder._context_menu;assert menu.entrycget(0,'state')=='normal'
            menu.invoke(0);menu.unpost();until(lambda:not folder._scanning);pump()
            assert getattr(folder,side+'_root').name==version
            assert getattr(folder,other+'_root')==other_root
        choices=[]
        for side,name in (('left','old name.md'),('right','new name.md')):
            tree=getattr(folder,side+'_tree');iid=next(i for i,key in folder.item_keys.items() if key==name)
            tree.see(iid);pump();x,y,w,h=tree.bbox(iid)
            tree.event_generate('<Button-1>',x=x+20,y=y+h//2);tree.event_generate('<ButtonRelease-1>',x=x+20,y=y+h//2);pump()
            choices.append(iid)
        assert folder.left_tree.selection()==(choices[0],)
        assert folder.right_tree.selection()==(choices[1],)
        assert folder.pair_button.instate(['!disabled'])
        folder.pair_button.invoke();pump()
        detail=list(folder.nested_details.values())[-1]['detail']
        assert 'version-a' in detail.view.left_title and 'old name.md' in detail.view.left_title
        assert 'version-b' in detail.view.right_title and 'new name.md' in detail.view.right_title
        folder._show_summary();pump();shot('folder-pair')
        tree=folder.right_tree;x,y,w,h=tree.bbox(choices[1])
        open_context(tree,x+20,y+h//2)
        assert folder._context_menu.entrycget(4,'state')=='normal'
        folder._context_menu.invoke(4);folder._context_menu.unpost();pump()
        assert len(folder.nested_details)==1,'context pairing must reuse the same session'
        folder._show_summary();pump()
        # Reset only the right base using its header context menu.
        label=folder.right_path_label;open_context(label,10,10)
        folder._context_menu.invoke(2);folder._context_menu.unpost();until(lambda:not folder._scanning)
        assert folder.right_root==folder.right_base_root and folder.left_root.name=='version-a'
        folder.change_base('left',folder.left_base_root.parent)
        assert folder.left_root.name=='version-a','must not escape source/archive root'
        folder.swap_sides();until(lambda:not folder._scanning);pump()
        assert not folder.nested_details
        if wrapped:
            assert parent.sessions[0].root==folder.left_base_root
            assert parent.sessions[1].root==folder.right_base_root
            selected_paths=[]
            for side,tree in enumerate(folder._trees()):
                iid=next(i for i,paths in folder.item_paths.items() if paths[side] and paths[side].is_file())
                tree.selection_set(iid);tree.focus(iid);selected_paths.append(folder.item_paths[iid][side])
            folder.left_tree.focus_force();pump()
            with mock.patch.object(messagebox,'askyesno',return_value=True):parent.delete_selected(1)
            until(lambda:not folder._scanning)
            assert selected_paths[0].is_file() and not selected_paths[1].exists()
            parent.undo_delete(1);until(lambda:not folder._scanning)
            assert selected_paths[1].is_file()
        parent.destroy();pump()
    # Archive drafts are editable but original archive never changes implicitly.
    za=root/'left.zip';zb=root/'right.zip'
    for p,value in ((za,'left'),(zb,'right')):
        with zipfile.ZipFile(p,'w') as z:z.writestr('note.md',value)
    originals=(za.read_bytes(),zb.read_bytes())
    def nested_factory(host,l,r,**kw):
        kind=kw.pop('kind',None)
        return ('Review',api.ReviewCompare(host,l,r,**kw)) if kind=='Review' else ('Text',compare.TextCompare(host,l,r,**kw))
    archive=compare.ArchiveReviewCompare(app,za,zb,compare.FolderCompare,nested_factory,None)
    archive.pack(fill='both',expand=True);until(lambda:not archive.busy)
    assert archive.inner,archive.status.cget('text')
    until(lambda:not archive.inner._scanning)
    archive.inner.open_nested_detail(archive.sessions[0].root/'note.md',archive.sessions[1].root/'note.md','note.md')
    legacy=next(iter(archive.inner.nested_details.values()))['detail']
    legacy.busy=lambda:None  # Tkinter 3.13+ inherited method is not a worker flag.
    legacy.open_review()
    assert len(archive.inner.nested_details)==2
    detail=list(archive.inner.nested_details.values())[-1]['detail'];until(lambda:not detail.busy)
    detail.search_var.set('right');detail.active_side=1;archive.find_next();assert detail._find_offset==0
    detail.next();detail.take(0);until(lambda:not detail.busy)
    with mock.patch.object(messagebox,'askyesno',return_value=False):assert not archive.confirm_close()
    with mock.patch.object(messagebox,'askyesno',return_value=True):detail.save_side(1)
    until(lambda:not detail.busy)
    assert (za.read_bytes(),zb.read_bytes())==originals
    assert archive.sessions[1].changes()==[('note.md','Replace')]
    archive.review_changes();until(lambda:not archive.busy)
    assert getattr(archive, '_review_dialog', None), (archive.status.cget('text'), errors)
    pump();shot('archive-draft')
    dialog=archive._review_dialog;assert dialog.grab_current() is dialog
    before=list(archive.paths);archive.inner.swap_sides();assert archive.paths==before
    cancel=next(w for w in dialog.winfo_children() if isinstance(w,ttk.Button))
    cancel.focus_force();pump()
    expected=str(cancel.tk.call('tk_focusNext',str(cancel)))
    cancel.event_generate('<Tab>');pump();assert str(app.focus_get())==expected
    leaked=[]
    app.bind_all('<F3>',lambda e:leaked.append('main preview'))
    app.bind_all('<F8>',lambda e:leaked.append('main VCS'))
    target=app.focus_get();target.event_generate('<F3>');target.event_generate('<F8>');pump()
    assert not leaked
    target.event_generate('<Escape>');pump()
    assert archive._review_dialog is None and not dialog.winfo_exists()
    app.unbind_all('<F3>');app.unbind_all('<F8>')
    session=archive.sessions[1];backup=session.commit()
    assert backup.read_bytes()==originals[1]
    with zipfile.ZipFile(zb) as z:assert z.read('note.md')==b'left'
    assert archive.close_nested_detail() and len(archive.inner.nested_details)==1
    archive.inner.session_tabs.select(next(iter(archive.inner.nested_details)))
    assert archive.close_nested_detail() and not archive.inner.nested_details
    assert archive.sessions[1].root.exists()
    archive.destroy();pump()
    arch=api if portable else importlib.import_module('pycommander.archivereview')
    exe=arch._seven_zip_executable();timings['seven_zip_available']=bool(exe)
    if exe:
        (root/'notes.txt').write_text('old')
        seven=root/'verify.7z'
        subprocess.run([exe,'a',str(seven),'notes.txt'],cwd=root,check=True,stdout=subprocess.DEVNULL)
        draft=arch.ArchiveReviewSession(seven)
        try:
            (draft.root/'notes.txt').write_text('verified');draft.commit()
            check=arch.ArchiveReviewSession(seven)
            try:assert (check.root/'notes.txt').read_text()=='verified'
            finally:check.cleanup()
        finally:draft.cleanup()
    assert not errors,errors
app.destroy()
print(json.dumps({'status':'passed','timings':timings}))
