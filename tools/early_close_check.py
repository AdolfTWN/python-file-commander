"""Closing/re-scaling before the next idle turn must not leave Tcl callbacks."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')
render=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.renderui')
compare=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.compare')


def pump(app):
    end=time.monotonic()+.2
    while time.monotonic()<end:app.update();time.sleep(.005)


with tempfile.TemporaryDirectory(prefix='pfc-early-close-') as raw:
    root=Path(raw);md=root/'notes.md';md.write_text('# Sample\n\nNEEDLE\n')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(exc[0].__name__)
    # This disposable interpreter captures native Tcl background errors too;
    # Python callback reporting alone cannot observe an already-deleted command.
    app.tk.call('set','::pfc_test_bgerrors',())
    app.tk.call('proc','bgerror','message','lappend ::pfc_test_bgerrors $message')
    try:
        app.auto_font_size_var.set(False);pump(app)
        for n in range(5):
            app.search();window=app.search_window
            window.apply_scale(2.0);window.close();pump(app)
            app.preview_paths([md],md);preview=app.preview_window
            preview.apply_scale(2.0);preview.close();pump(app)
        # Static visual formats schedule their initial raster draw separately
        # from text/structure rendering. Close before that first idle turn.
        image=pfc.tk.PhotoImage(master=app,width=8,height=8)
        png=image.tk.call(str(image),'data','-format','png')
        view=render.FormatRenderView(app)
        view.show(dict(kind='image',png=png,content='',positions=[]))
        view.destroy();pump(app)
        left=root/'left';right=root/'right';left.mkdir();right.mkdir()
        for folder in (left,right):(folder/'note.txt').write_text(folder.name)
        def pair_factory(host,a,b,**kwargs):return 'Text',compare.TextCompare(host,a,b,**kwargs)
        folder_view=compare.FolderCompare(app,left,right,pair_factory)
        folder_view.pack(fill='both',expand=True)
        deadline=time.monotonic()+10
        while folder_view._scanning:
            pump(app)
            assert time.monotonic()<deadline,'Folder comparison did not settle'
        folder_view.open_nested_detail(left/'note.txt',right/'note.txt','note.txt')
        folder_view.close_nested_detail();pump(app)
        folder_view._show_summary();folder_view.destroy();pump(app)
        # Constructor failures leave a real partial toplevel under the root.
        # Cleanup must not require controls whose construction never finished.
        with patch.object(pfc.ttk,'Progressbar',side_effect=pfc.tk.TclError('fixture-constructor-failure')):
            try:app.search()
            except pfc.tk.TclError:pass
            else:raise AssertionError('Fixture did not interrupt Search construction')
        partials=[w for w in app.winfo_children() if isinstance(w,pfc.SearchWindow)]
        assert partials,'Expected a partial Search toplevel'
        for window in partials:window.destroy()
        pump(app)
        native=app.tk.splitlist(app.tk.call('set','::pfc_test_bgerrors'))
        assert not native,('Native Tcl errors after immediate close',native)
        assert not errors,errors
        print('PASS: immediate Search/Preview/image close and nested Compare tab close leave no dangling idle/focus callbacks')
    finally:app.close_app()
