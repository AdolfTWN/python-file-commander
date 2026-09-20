"""Component context menus: routing, shared settings, persistence and cascades."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def settle(app):
    until=time.monotonic()+.15
    while time.monotonic()<until:app.update();time.sleep(.01)

def index(menu,label):
    return next(i for i in range(menu.index('end')+1)
                if menu.type(i)!='separator' and menu.entrycget(i,'label')==pfc.tr(label))

def submenu(menu,label):return menu.nametowidget(menu.entrycget(index(menu,label),'menu'))

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw);folder=root/'files';folder.mkdir()
    (folder/'item.txt').write_text('fixture');(folder/'child').mkdir()
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False);app.geometry('1500x800+0+0')
        left=app.left_tabs.current();right=app.right_tabs.current()
        left.navigate(folder);right.navigate(folder);settle(app)
        row=right.tree.get_children()[0];right.tree.selection_set(row)
        original=right.tree.selection();app.set_active(left)
        x=right.tree.winfo_rootx()+15;y=right.tree.winfo_rooty()+right.tree.winfo_height()-20
        assert not right.tree.identify_row(right.tree.winfo_height()-20)
        event=SimpleNamespace(x=15,y=right.tree.winfo_height()-20,x_root=x,y_root=y)
        # Blank-space menu takes precedence even in Explorer mode; old selection is untouched.
        right._context_click(event);settle(app)
        assert app.active is right and right.tree.selection()==original
        menu=app.panel_context_menu
        assert app.header_popup.popups[0].menu is menu
        for label,model in [('Panel Counts',app.panel_counts_menu),('Right Click Menu',app.right_click_menu),
                            ('File Columns',app.columns_menu),('Font Size',app.font_size_menu),('Color Scheme',app.color_scheme_menu)]:
            assert submenu(menu,label) is model
        assert not any(menu.entrycget(i,'label') in ('Delete','Rename','Cut to Clipboard')
                       for i in range(menu.index('end')+1) if menu.type(i)!='separator')
        app.header_popup.close_all()
        submenu(menu,'Panel View').invoke(1);settle(app)
        assert right.view_mode=='folder' and left.view_mode=='list'
        # Nested settings use the exact same variables/actions as the main menu.
        menu=app._build_panel_context_menu(right)
        submenu(menu,'Right Click Menu').invoke(1)
        assert app.right_click_menu_var.get()=='pfc'
        app.column_visible_vars['ext'].set(False);app.apply_column_settings()
        submenu(submenu(menu,'File Columns'),'Ext').invoke(0)
        assert app.column_visible_vars['ext'].get()
        for count in (4,2,3,2):
            submenu(menu,'Panel Counts').invoke(count-1);settle(app)
            assert len(app.visible_panel_tabs())==count
        # A file row must still dispatch to the chosen native/PFC handler.
        right.set_view_mode('list');settle(app)
        row=right.tree.get_children()[0];box=right.tree.bbox(row);calls=[]
        right.on_context=lambda *a:calls.append('pfc')
        right.on_native_context=lambda *a:calls.append('explorer')
        for mode in ('pfc','explorer'):
            app.right_click_menu_var.set(mode)
            right._context_click(SimpleNamespace(x=20,y=box[1]+box[3]//2,x_root=x,y_root=y))
            assert calls[-1]==mode
        right.tree.selection_remove(*right.tree.selection());right.tree.focus('')
        right._context_keyboard();assert app.header_popup.popups
        app.header_popup.close_all()
        tabs=app.left_tabs
        tabs._popup_keyboard();settle(app)
        tabmenu=tabs._context_menu
        assert submenu(tabmenu,'Tab Style') is app.tab_style_menu
        app.header_popup.close_all()
        submenu(tabmenu,'Tab Color').invoke(1)
        assert tabs._colors[tabs._selected]=='red'
        for value in ('rounded','squarish','right_skirt'):
            style=submenu(tabmenu,'Tab Style');style.invoke(list(pfc.TAB_STYLES).index(value));settle(app)
            assert app.tab_style_var.get()==value
            assert all(t._tab_style==value for t in app.panel_tabs)
        tabmenu.invoke(index(tabmenu,'Lock (open folder in new tab)'))
        assert tabs._locks[tabs._selected]=='locked'
        tabmenu.invoke(index(tabmenu,'Unlocked'))
        # Reopen repeatedly: retained variables and menus, not accumulating popups.
        for _ in range(4):
            tabs._popup_keyboard();settle(app);app.header_popup.close_all()
        empty=tabs._build_context_menu(None)
        assert empty.index('end')==0 and submenu(empty,'Tab Style') is app.tab_style_menu
        # Shared custom cascade renderer: three levels, large fonts, both edges.
        for font in ('small','large','300'):
            app.font_size_var.set(font);app.apply_font_size(save=False);settle(app)
            for scheme in ('light','light_grey','dark'):
                app.color_scheme_var.set(scheme);app.apply_color_scheme(save=False)
                for edge in (0,app.winfo_screenwidth()-2):
                    app.show_panel_context_menu(right,edge,app.winfo_screenheight()-2);settle(app)
                    top=app.header_popup.popups[0]
                    app.header_popup.open_child(top,index(top.menu,'File Columns'))
                    columns=app.header_popup.popups[-1]
                    app.header_popup.open_child(columns,index(columns.menu,'Date Modified'));settle(app)
                    assert len(app.header_popup.popups)==3
                    for popup in app.header_popup.popups:
                        assert popup.top.winfo_viewable()
                        assert popup.top.winfo_rootx()>=0
                    app.header_popup.close_all()
        app._show_zoom_context(SimpleNamespace(widget=app.zoom_combo))
        assert app.header_popup.popups[0].menu is app.font_size_menu
        app.header_popup.close_all();app.save_config()
        saved=pfc.configparser.ConfigParser();saved.read(root/'pfc.ini')
        assert saved.get('view','right_click_menu')=='explorer'
        assert saved.get('view','tab_style')=='right_skirt'
        assert not errors,errors
        print('PASS: background/tab/zoom context routing, row-mode preservation, shared settings/INI, three-level cascades at 100/150/300% and three themes')
    finally:
        app.header_popup.close_all();app.destroy()
