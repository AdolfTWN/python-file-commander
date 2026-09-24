"""Reading-scale Settings and persistent source-panel/custom tab groups."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter.font as tkfont

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def settle(app,seconds=.12):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.01)

with tempfile.TemporaryDirectory(prefix='pfc-reading-groups-') as raw:
    root=Path(raw)
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        for scale in ('small','large','175','xl','300'):
            app.font_size_var.set(scale);app.apply_font_size(save=False)
            app.show_settings();d=app.settings_window;settle(app)
            assert d.font.metrics('linespace')==tkfont.nametofont('TkDefaultFont').metrics('linespace')
            for category,_ in pfc.SETTINGS_CATEGORIES:
                d.show_page(category);settle(app)
                assert d.canvas.winfo_height()>=65,(scale,category,d.canvas.winfo_height())
                assert d.footer.winfo_rooty()+d.footer.winfo_height()<=d.winfo_rooty()+d.winfo_height()+1
                if d._whole_page_scroll:
                    assert d.comparison.winfo_rooty()<d.page.winfo_rooty()
                    d.canvas.yview_moveto(1);settle(app)
                    control=list(d.controls.values())[-1]
                    control.focus_force();settle(app)
                    assert d.canvas.winfo_rooty()<=control.winfo_rooty()<d.canvas.winfo_rooty()+d.canvas.winfo_height()
            d.cancel()
        app.font_size_var.set('small');app.apply_font_size(save=False)
        app.show_settings();d=app.settings_window;settle(app)
        original=d.font.metrics('linespace')
        d.vars['font_size'].set('xl');settle(app)
        assert d.font.metrics('linespace')==original,'Draft must not move controls'
        d.apply();settle(app)
        assert d.font.metrics('linespace')==tkfont.nametofont('TkDefaultFont').metrics('linespace')>original
        if '--screenshots' in sys.argv:
            from PIL import ImageGrab
            d.show_page('layout');settle(app)
            x,y=d.winfo_rootx(),d.winfo_rooty()
            ImageGrab.grab((x,y,x+d.winfo_width(),y+d.winfo_height())).save('/tmp/pfc-settings-readable.png')
        d.cancel()
        app.panel_count_var.set(4);app.apply_panel_count(save=False)
        for index,tabs in enumerate(app.panel_tabs):
            path=root/f'Panel-{index+1}';path.mkdir()
            pane=tabs.add_tab(path)
            if index==0:app.set_tab_group(pane,'Documents')
        app.panel_count_var.set(1);app.apply_panel_count(save=False);settle(app)
        shared=app.single_tabs
        assert {shared._group_identity(p)[0] for p in shared._tabs}=={1,2,3,4}
        assert any('Documents' in label for _a,_b,_p,label in shared._group_ranges)
        pane=next(p for p in shared._tabs if p.tab_group=='Documents')
        app.set_tab_group(pane,'研究 · MD')
        assert any('研究 · MD' in label for _a,_b,_p,label in shared._group_ranges)
        menu=shared._build_context_menu(pane)
        assert pfc.tr('Tab Group') in [menu.entrycget(i,'label') for i in range(menu.index('end')+1) if menu.type(i)!='separator']
        # Compare uses the same generic notebook; never expose file-panel group
        # commands on unrelated session tabs.
        unrelated=pfc.ChamferNotebook(app);frame=pfc.ttk.Frame(unrelated)
        unrelated.add(frame,text='Compare session')
        menu=unrelated._build_context_menu(frame)
        assert pfc.tr('Tab Group') not in [menu.entrycget(i,'label') for i in range(menu.index('end')+1) if menu.type(i)!='separator']
        unrelated.destroy()
        for count in (2,3,4,1):
            app.panel_count_var.set(count);app.apply_panel_count(save=False);settle(app)
            assert app._tabs_for(pane).panel_number==1 and pane.tab_group=='研究 · MD'
        app.save_config()
        assert '研究 · MD' in json.loads(app.config_data.get('left','tab_groups'))
        for n in range(5):
            path=root/f'Long project document collection {n}';path.mkdir()
            app.left_tabs.add_tab(path)
        app.geometry('780x650+0+0');settle(app)
        shared.select(shared._tabs[-1]);settle(app)
        assert shared.tab_scroll.winfo_ismapped()
        assert abs(shared.bar.xview()[0]-shared.group_bar.xview()[0])<.01
        left,right,last=shared._hitboxes[-1]
        assert shared._at((left+right)/2-shared.bar.canvasx(0)) is last
        if '--screenshots' in sys.argv:
            from PIL import ImageGrab
            app.geometry('1280x800+0+0');settle(app);shared._scroll_tabs('moveto',0);settle(app)
            x,y=shared.winfo_rootx(),shared.winfo_rooty()
            ImageGrab.grab((x,y,x+shared.winfo_width(),y+shared.winfo_height())).save('/tmp/pfc-tab-groups.png')
        app.close_app()
        # A fresh process on restart has no old Tcl timers. Isolate the two Tk
        # interpreters used by this in-process restart fixture the same way.
        for job in app.tk.call('after','info'):app.tk.call('after','cancel',job)
        app=pfc.Commander();app.report_callback_exception=lambda *exc:errors.append(str(exc));settle(app)
        pane=next(p for p in app.all_panes() if p.tab_group=='研究 · MD')
        assert app._tabs_for(pane).panel_number==1
        app.panel_count_var.set(2);app.apply_panel_count(save=False)
        assert app._move_tab_to_panel(app.left_tabs,pane,app.right_tabs,0)
        moved=next(p for p in app.right_tabs.panes() if p.tab_group=='研究 · MD')
        assert app.right_tabs._group_identity(moved)==(2,'研究 · MD')
        app.set_tab_group(moved,'');assert not moved.tab_group
        assert not errors,errors
        print('PASS: Settings 100–300% font inheritance, Apply, six scrollable pages; P1–P4, custom groups, save/reopen/move/remove and overflow hit testing')
    finally:
        d=getattr(app,'settings_window',None)
        if d is not None and d.winfo_exists():d.cancel()
        if app.winfo_exists():app.close_app()
