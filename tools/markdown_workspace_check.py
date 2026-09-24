"""Real Preview/worker integration: explicit scope, duplicates, backlinks, cancel."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def wait(app, predicate, seconds=10):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.update();time.sleep(.01)
        if predicate():return
    raise AssertionError('UI work did not finish')


with tempfile.TemporaryDirectory() as raw:
    root=Path(raw)/'Project 100%';root.mkdir();note=root/'Notes.md'
    note.write_text('# Notes\n\n[[Spec#Section|Specification]]\n',encoding='utf-8')
    for folder in ('one','two'):
        (root/folder).mkdir();(root/folder/'Spec.md').write_text('# Section\n\nA document.',encoding='utf-8')
    (root/'Reference.md').write_text('[Notes](Notes.md)\n',encoding='utf-8')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    pfc.Commander._start_windows_tray=lambda self:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        for language in ('en','zh_TW','zh_CN','ko'):
            pfc.set_language(language)
            app.auto_font_size_var.set(False)
            app.font_size_var.set('large' if language in ('zh_TW','ko') else 'small')
            app.apply_font_size(save=False)
            app.preview_paths([note],note);win=app.preview_window
            wait(app,lambda:not(win._md_jobs.pending or win._md_queued or win._md_insert))
            page=win.active_page
            page.follow_markdown_link(0);app.update();dialog=page._workspace_dialog
            assert dialog.jobs.process is None,'Opening/hover must not start search'
            assert dialog.depth_var.get()=='3'
            dialog.start();wait(app,lambda:dialog.request is None)
            assert len(dialog.results)==2,dialog.status.cget('text')
            assert not dialog.tree.selection(),'Never choose first ambiguous result automatically'
            assert dialog.open_button.instate(['disabled'])
            assert dialog.open_button.winfo_y()+dialog.open_button.winfo_height()<=dialog.open_button.master.winfo_height()
            dialog.geometry('700x480');app.update()
            assert dialog.tree.winfo_height()>60 and dialog.open_button.winfo_viewable()
            assert dialog.open_button.winfo_rooty()+dialog.open_button.winfo_height()<=dialog.winfo_rooty()+dialog.winfo_height()
            dialog.tree.selection_set('0');dialog.open_selected()
            wait(app,lambda:not(page._md_jobs.pending or page._md_queued or page._md_insert))
            assert page.path.name=='Spec.md' and 'A document.' in page.text.get('1.0','end')
            page.markdown_back();wait(app,lambda:not(page._md_jobs.pending or page._md_queued or page._md_insert))
            assert page.path==note
            assert page._md_boundary==root
            page.markdown_workspace('backlinks');app.update();dialog=page._workspace_dialog
            dialog.start();wait(app,lambda:dialog.request is None)
            assert [r['path'] for r in dialog.results]==['Reference.md'],dialog.status.cget('text')
            dialog.query_var.set('changed');app.update()
            assert not dialog.results and dialog.open_button.instate(['disabled'])
            dialog.start();dialog.cancel_search();app.update()
            assert dialog.request is None and dialog.jobs.pending is None
            dialog.close();win.close();app.preview_window=None
        assert not errors,errors
        print('PASS: explicit bounded scope; wiki duplicates and heading navigation; backlinks; four languages; stale-result clearing; cancellation; footer')
    finally:
        if app.preview_window and app.preview_window.winfo_exists():app.preview_window.close()
        app.destroy()
