"""Markdown UI dogfood: read-only features, guarded navigation, cancellation."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def settle(app,preview):
    start=time.monotonic()
    while time.monotonic()-start<9:
        app.update();time.sleep(.01)
        if time.monotonic()-start>.2 and not (preview._md_jobs.pending or preview._md_queued
                or preview._md_insert or preview._span_job): return
    raise AssertionError('Preview failed to settle: '+preview.status.cget('text'))

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw);start=root/'start.md';child=root/'child.md'
    source='# Work 😀\n- [ ] Pending\n- [x] Done\n> [!warning]- Important\n> Always visible\n\n'
    source+='[Child](child.md#Details) [Missing](absent.md) [Escape](../outside.md) [[#End]]\n\n'
    source+='## Nested\n'+('Paragraph\n'*50)+'NEEDLE\n# End\nThe end\n'
    start.write_text(source,encoding='utf-8');child.write_text('# Child\n## Details\nTarget\n',encoding='utf-8')
    before=(start.read_bytes(),child.read_bytes())
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    preview=None
    try:
        app.auto_font_size_var.set(False);app.geometry('1400x850+0+0')
        preview=pfc.PreviewWindow(app,app.config_data,lambda:None,[start,child],start)
        settle(app,preview)
        assert preview._md_model.get('tasks')==[1,2],preview.status.cget('text')
        assert len(preview._md_model['links'])==4
        assert 'Always visible' in preview.text.get('1.0','end')
        for size in ('small','large','300'):
            app.font_size_var.set(size);app.apply_font_size(save=False);preview.apply_scale(1)
            preview.geometry('1100x720+0+0');app.update()
            assert preview.md_cancel.winfo_ismapped(),'Cancel must remain accessible'
            for widget in (preview.md_back,preview.md_outline,preview.md_fold,preview.md_more,preview.md_cancel):
                assert widget.winfo_rootx()+widget.winfo_width()<=preview.winfo_rootx()+preview.winfo_width(),(size,str(widget))
            preview.geometry('640x400+0+0');app.update();app.update_idletasks()
            assert preview.md_cancel.winfo_ismapped(),('narrow',size)
            assert preview.md_cancel.winfo_rootx()+preview.md_cancel.winfo_width()<=preview.winfo_rootx()+preview.winfo_width(),('narrow',size)
            preview.geometry('1100x720+0+0');app.update()
            for theme in ('light','dark','light_grey'):
                preview.apply_color_scheme(pfc.COLOR_SCHEMES[theme]);app.update()
                preview.md_outline.current(0);preview.markdown_fold()
                assert preview._md_folded=={0}
                preview.search_var.set('NEEDLE');preview.find_next()
                assert not preview._md_folded,'Search must reveal folded matches'
                preview.md_outline.current(0);preview.markdown_fold()
                preview._copy_select_all();preview._copy_preview()
                assert 'NEEDLE' in app.clipboard_get(),'Copy must include folded text'
                preview.markdown_expand_all();preview.text.tag_remove('sel','1.0','end')
        print('PASS: tasks/callouts, 100/150/300%, three themes, folding, search and lossless copy',flush=True)
        preview.toggle_markdown_source();settle(app,preview)
        assert preview.text.get('1.0','end-1c')==before[0].decode('utf-8')
        preview.set_extension_effect(False);settle(app,preview)
        assert not preview._md_model['rendered'] and not preview._md_model['spans']
        preview.set_extension_effect(True)
        preview.toggle_markdown_source();settle(app,preview)
        # Unicode before a link must not shift its clickable range.
        assert preview.text.get(*preview.text.tag_ranges('md_link_0'))=='Child'
        preview.text.yview_moveto(.5);app.update();position=preview.text.yview()[0]
        preview.follow_markdown_link(0);settle(app,preview)
        assert preview.path==child,preview.status.cget('text')
        assert 'Target' in preview.text.get('1.0','end')
        assert preview.md_outline.current()==1
        preview.markdown_back();settle(app,preview)
        assert preview.path==start and not preview._md_history
        assert abs(preview.text.yview()[0]-position)<.08
        original=preview.text.get('1.0','end')
        preview.follow_markdown_link(1);settle(app,preview)
        assert preview.path==start and preview.text.get('1.0','end')==original
        assert not preview._md_history
        preview.follow_markdown_link(2);app.update()
        assert 'boundary' in preview.status.cget('text').lower()
        preview.follow_markdown_link(3);app.update()
        assert preview.md_outline.current()==2
        print('PASS: exact linked read, heading target, Back/position, missing target and boundary refusal',flush=True)
        # Superseded work must never repaint a new document.
        preview.load();app.update();preview.show([child],child);settle(app,preview)
        assert preview.path==child and 'Target' in preview.text.get('1.0','end')
        preview.load();app.update();preview.cancel_markdown();app.update()
        assert preview._md_jobs.pending is None and not preview._md_queued
        preview.load();settle(app,preview)
        assert 'Target' in preview.text.get('1.0','end')
        # A deliberately unresponsive private worker must time out without
        # replacing the document or accumulating processes; F5 can recover.
        original_jobs=preview._md_jobs;original_jobs.close()
        slow=root/'slow_worker.py'
        slow.write_text('import time\ndef markdown_worker_main(): time.sleep(30)\n',encoding='utf-8')
        preview.active_page._md_jobs=type(original_jobs)(slow,False)
        preview.load()
        until=time.monotonic()+2
        while not preview._md_jobs.pending:
            app.update();time.sleep(.01);assert time.monotonic()<until
        preview._md_jobs.started-=6
        settle(app,preview)
        assert 'timed out' in preview.status.cget('text').lower()
        assert 'Target' in preview.text.get('1.0','end')
        preview._md_jobs.close();preview.active_page._md_jobs=original_jobs
        preview.load();settle(app,preview)
        # Archive paths allow anchors only, never following extraction paths.
        archive=root/'pfc-archive-fixture';archive.mkdir()
        archived=archive/'note.md';archived.write_text('[Other](other.md) [[#Here]]\n# Here\n',encoding='utf-8')
        preview.show([archived],archived);settle(app,preview)
        assert 'pfc-archive-' not in preview._markdown_boundary_label()
        preview._describe_markdown_link(preview._md_model['links'][1])
        assert 'pfc-archive-' not in preview.status.cget('text')
        preview.follow_markdown_link(0)
        assert 'archives' in preview.status.cget('text').lower()
        assert preview.path==archived and not preview._md_history
        preview.follow_markdown_link(1);assert preview.md_outline.current()==0
        # Oversized renderer input uses bounded, explicitly marked source fallback.
        large=root/'large.md';large.write_text('x'*600000,encoding='utf-8')
        preview.show([large],large);settle(app,preview)
        assert not preview._md_model['rendered'] and preview._md_model['truncated']
        assert 'limit' in preview.status.cget('text').lower()
        assert len(preview.text.get('1.0','end-1c'))==512*1024
        assert (start.read_bytes(),child.read_bytes())==before
        assert not errors,errors
        jobs=[page._md_jobs for page in preview.pages.values()]
        preview.close();app.update()
        assert all(job.process is None for job in jobs)
        print('PASS: stale-job rejection, cancel/timeout/retry, archive boundary, bounded fallback, unchanged source and cleanup',flush=True)
    finally:
        if preview is not None:
            for page in preview.pages.values(): page._md_jobs.close()
        app.destroy()
