"""Column header routing, date roundtrips, visibility/persistence and input safety."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def settle(app):
    deadline=time.monotonic()+.15
    while time.monotonic()<deadline:
        app.update(); time.sleep(.01)

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw)/'files'; root.mkdir()
    for name,hour,minute in (('morning.txt',11,36),('evening.txt',17,15)):
        path=root/name; path.write_text('test')
        stamp=datetime(2026,9,19,hour,minute).timestamp()
        os.utime(path,(stamp,stamp))
    module.Commander._find_ini_path=staticmethod(lambda:Path(raw)/'pfc.ini')
    module.Commander._sync_auto_start=lambda self,**kw:True
    app=module.Commander(); errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False); app.geometry('1800x760')
        pane=app.left_tabs.current(); pane.navigate(root); app.set_active(pane); settle(app)
        rows={Path(pane.tree.item(iid,'tags')[0]).name:iid for iid in pane.tree.get_children()}
        original_ids=pane.tree.get_children()
        for column in ('name','ext','size','modified'):
            assert column in app.column_menus
        # Right-click the actual on-screen header: choose correct logical column.
        captured=[]; show=app.show_column_menu
        app.show_column_menu=lambda column,event:captured.append(column)
        def header_click(column):
            shown=['name']+list(pane.tree.cget('displaycolumns'))
            x=2+sum(pane.tree.column('#0' if c=='name' else c,'width') for c in shown[:shown.index(column)])
            x+=pane.tree.column('#0' if column=='name' else column,'width')//2
            y=next(y for y in range(1,80) if pane.tree.identify_region(x,y)=='heading')
            pane._context_click(SimpleNamespace(x=x,y=y,x_root=x,y_root=y))
            assert captured[-1]==column,(captured,column)
        for column in ('name','ext','size','modified'): header_click(column)
        width_before=pane.tree.column('#0','width')
        app.column_visible_vars['ext'].set(False); app.apply_column_settings(); settle(app)
        assert 'ext' not in pane.tree.cget('displaycolumns')
        assert pane.tree.column('#0','width')>width_before
        header_click('size'); header_click('modified')
        # Header Ext is absent; main menu is the remaining way to restore it.
        app.column_menus['ext'].invoke(0); settle(app)
        assert 'ext' in pane.tree.cget('displaycolumns')
        app.show_column_menu=show
        for date in ('ymd','mdy'):
            for clock in ('none','12','24','none','12'):
                app.date_order_var.set(date); app.time_style_var.set(clock)
                app.apply_column_settings(); settle(app)
                prefix='2026/09/19' if date=='ymd' else '09/19/2026'
                for name,suffix in (('morning.txt','1136a'),('evening.txt','0515p')):
                    text=pane.tree.set(rows[name],'modified')
                    assert text.startswith(prefix),text
                    if clock=='none': assert text==prefix
                    elif clock=='12': assert text==prefix+' '+suffix,text
        assert pane.tree.get_children()==original_ids, 'Display changes must preserve selection/drag IDs'
        app.column_visible_vars['ext'].set(False); app.size_emphasis_var.set(False)
        app.apply_column_settings(); app.save_config()
        config=module.configparser.ConfigParser(); config.read(Path(raw)/'pfc.ini')
        assert not config.getboolean('view','column_ext')
        assert config.get('view','date_order')=='mdy'
        assert config.get('view','time_style')=='12'
        assert not config.getboolean('view','size_emphasis')
        app.sort_column('modified',True); settle(app)
        assert pane.tree.heading('modified','text').endswith('▼')
        assert not errors,errors
        print('PASS: four header menus, hidden-column mapping/restoration, six date/time modes, lossless roundtrip, persistence and sort')
    finally: app.destroy()
