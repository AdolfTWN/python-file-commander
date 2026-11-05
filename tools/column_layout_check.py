"""Sizing preserves exact labels/widths; no all-row rewrites or persistent cache."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def pump(app):
    end=time.monotonic()+.15
    while time.monotonic()<end:app.update();time.sleep(.005)


with tempfile.TemporaryDirectory(prefix='pfc-column-check-') as raw:
    folder=Path(raw);(folder/'nested').mkdir()
    for n in range(80):
        (folder/f'{n:03} Report 報告.txt').write_bytes(b'x'*(n%4+1))
    target=folder/'nested'/'same report.txt';target.write_text('Nested data')
    pfc.Commander._find_ini_path=staticmethod(lambda:folder/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander()
    try:
        app.auto_font_size_var.set(False);pump(app)
        pane=app.left_tabs.current();pane.navigate(folder);pump(app)
        tree=pane.tree;original=tree.item;calls=[]
        def item(*args,**kwargs):
            calls.append((args,kwargs));return original(*args,**kwargs)
        font=pfc.tkfont.nametofont('TkDefaultFont')
        for level in ('small','large','300'):
            app.font_size_var.set(level);app.select_manual_font_size();pump(app)
            for visible in (('ext','size','modified'),('ext',),('size',),('modified',)):
                # Use the actual preferences; a folder watcher may legitimately
                # refresh this fixture after the font change saves its INI.
                # Direct Treeview configuration would then be reset by design.
                for col,var in app.column_visible_vars.items():var.set(col in visible)
                app.apply_column_settings();pump(app)
                labels={iid:tree.item(iid,'text') for iid in tree.get_children()}
                expected={}
                for col in visible:
                    if col=='ext':expected[col]=pfc.extension_column_width(font.measure);continue
                    index=pane.columns.index(col)
                    padding=max(8,font.measure(' ')*2) if col=='size' else max(18,font.measure('MM'))
                    measure=pane.size_units.measure if col=='size' else font.measure
                    expected[col]=max([font.measure(tree.heading(col,'text'))+padding]+
                                      [measure(str(tree.item(iid,'values')[index]))+padding for iid in tree.get_children()])
                calls.clear();tree.item=item
                try:pane._autosize_columns()
                finally:tree.item=original
                assert not any(kwargs for _,kwargs in calls),'Sizing rewrote row data'
                assert len(calls)==(len(labels) if any(c!='ext' for c in visible) else 0),(visible,len(calls),len(labels))
                assert {col:tree.column(col,'width') for col in visible}==expected
                assert labels=={iid:tree.item(iid,'text') for iid in tree.get_children()}
        for var in app.column_visible_vars.values():var.set(True)
        app.apply_column_settings();pump(app)
        # This legacy search view deliberately carries relative paths. Geometry
        # must never replace those identifiers with basename-only labels.
        pane.search('same report');pump(app)
        iid=tree.get_children()[0];label=tree.item(iid,'text')
        assert 'nested' in label
        pane._autosize_columns();pump(app)
        assert tree.item(iid,'text')==label
        print('PASS: exact widths at 100/150/300%, hidden columns, read-only one-pass snapshot, relative labels retained')
    finally:app.close_app()
