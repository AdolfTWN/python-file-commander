"""Task-based large compare, draft review, workbook and archive GUI checks."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import font, messagebox, simpledialog
from unittest import mock
import zipfile
import subprocess
import configparser

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
portable=len(sys.argv)>1 and sys.argv[1]=='pfc'
api=importlib.import_module('pfc' if portable else 'pycommander.reviewui')
tables=api if portable else importlib.import_module('pycommander.workbookui')
compare=api if portable else importlib.import_module('pycommander.compare')
app=tk.Tk();app.geometry('1360x850+0+0');errors=[];timings={}
app.report_callback_exception=lambda *args:errors.append(str(args))


def pump(seconds=.1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.005)


def until(predicate,seconds=90):
    end=time.monotonic()+seconds
    while not predicate():
        if time.monotonic()>end:raise AssertionError('Timed out: '+str(errors))
        pump(.025)


def shot(name):
    app.lift();app.focus_force();pump(.3)
    if os.name=='nt':
        if name not in ('text-1.75-760','workbook','archive-draft'):return
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
    view=api.ReviewCompare(app,a,b);view.pack(fill='both',expand=True)
    until(lambda:not view.busy)
    assert view.alignment,view.status.cget('text')
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
    # Read-only workbook UI exposes the change, full cell and rule modes.
    ca=root/'left.csv';cb=root/'right.csv'
    ca.write_text('id,value\none,10\ntwo,20\n');cb.write_text('id,value\none,11\ntwo,21\n')
    grid=tables.WorkbookCompare(app,ca,cb);grid.pack(fill='both',expand=True)
    until(lambda:grid.books is not None and grid._rows_job is None)
    assert len(grid.filtered)==2,grid.status.cget('text')
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
    assert not grid.filtered
    grid.destroy();pump()
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
    legacy=next(iter(archive.inner.nested_details.values()))['detail'];legacy.open_review()
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
    pump();shot('archive-draft')
    for child in archive.winfo_children():
        if isinstance(child,tk.Toplevel):child.destroy()
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
