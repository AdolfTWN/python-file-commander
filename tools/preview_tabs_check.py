"""Real Tk: syntax files must render, F3 tabs retain independent reading state."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def settle(app):
    deadline = time.monotonic()+10
    while time.monotonic()<deadline:
        app.update(); time.sleep(.01)
        win = app.preview_window
        if not (win._md_jobs.pending or win._md_queued or win._md_insert or win._span_job):
            app.update(); return
    raise AssertionError('Preview did not finish')

with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)
    pfc.Commander._find_ini_path = staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda self, **kw:True
    pfc.Commander._start_windows_tray = lambda self:None
    app = pfc.Commander(); errors=[]
    app.report_callback_exception = lambda *exc:errors.append(str(exc))
    try:
        paths=[]
        for suffix in ('.yaml','.yml','.py','.json','.xml','.ps1','.txt'):
            path=root/('sample'+suffix)
            path.write_text('name: sample\nversion: 1.0.0\n'+'status: draft\n'*200, encoding='utf-8')
            paths.append(path)
        utf16=root/'wide.yaml'; utf16.write_text('name: 中文測試\n',encoding='utf-16');paths.append(utf16)
        md=root/'Notes.md';md.write_text('# Notes\n\n'+'Paragraph\n\n'*100,encoding='utf-8');paths.append(md)
        second=root/'other'/'Notes.md';second.parent.mkdir();second.write_text('# Other\n',encoding='utf-8');paths.append(second)
        app.active.navigate(root);app.update()
        # Actual multiselect -> F3, not merely a direct PreviewWindow call.
        app.active.tree.selection_set(*(iid for iid in app.active.tree.get_children()
                                       if app.active.tree.item(iid,'tags') and
                                       Path(app.active.tree.item(iid,'tags')[0]) in paths[:3]))
        app.preview();settle(app)
        win=app.preview_window
        assert len(win.pages)==3
        app.search();search=app.search_window
        rows=[search.tree.insert('', 'end', values=(path.name,), tags=(str(path),)) for path in (md,second)]
        search.tree.selection_set(*rows);search.preview_selected();settle(app)
        assert len(win.pages)==5, 'Search-result multi-select must open tabs too'
        search.close()
        win.close();app.preview_window=None
        app.preview_paths(paths,paths[0]);win=app.preview_window
        win.open_paths(paths,paths,paths[0]);settle(app)
        assert len(win.pages)==len(paths)
        assert all(not page._loaded and page._md_jobs.process is None
                   for page in win.pages.values() if page.path in (md,second)), 'Markdown tabs load lazily'
        for path in paths:
            win.show(paths,path);settle(app)
            assert win.text.get('1.0','end-1c').strip(),path
            if path.suffix!='.md':
                assert 'name:' in win.text.get('1.0','end-1c')
                win.mode_var.set(pfc.tr('Text'));win.load();settle(app)
                assert 'name:' in win.text.get('1.0','end-1c')
        win.show(paths,paths[0]);settle(app)
        page=win.active_page;page.wrap_var.set(True);page.set_wrap()
        page.search_var.set('draft');page.find_all();page.text.yview_moveto(.6);app.update()
        position=page.text.yview()
        win.show(paths,md);settle(app)
        win.show(paths,paths[0]);settle(app)
        assert win.active_page is page and page.wrap_var.get() and page.search_var.get()=='draft'
        assert abs(page.text.yview()[0]-position[0])<.01
        assert len(win.pages)==len(paths), 'Repeated F3 must reuse an existing document'
        win.show(paths,md);settle(app)
        mdpage=win.active_page;mdpage.md_outline.current(0);mdpage.markdown_fold()
        folded=set(mdpage._md_folded)
        win.show(paths,paths[0]);settle(app)
        win.show(paths,md);settle(app)
        assert win.active_page is mdpage and mdpage._md_folded==folded
        assert sum(p._md_jobs.process is not None for p in win.pages.values())<=1
        win.show(paths,paths[0]);settle(app)
        win.cycle(1);app.update();assert win.active_page is not page
        win.close_tab();app.update();assert len(win.pages)==len(paths)-1
        win.apply_color_scheme(pfc.COLOR_SCHEMES['dark']);win.apply_scale(1.75);settle(app)
        missing=root/'missing.txt';win.show([missing],missing);settle(app)
        assert pfc.tr('Cannot preview file') in win.text.get('1.0','end-1c')
        assert not errors,errors
        win.close()
        print('PASS: actual multi-select F3; syntax/UTF-16 text; lazy/deduplicated tabs; independent scroll/find/wrap; close/cycle; errors')
    finally: app.destroy()
