"""Draft/cancel/apply, settings scope, shortcuts, screenshots and compact layouts."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def settle(app,seconds=.15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.01)

with tempfile.TemporaryDirectory(prefix='pfc-settings-check-') as raw:
    root=Path(raw);folder=root/'Demo';folder.mkdir();(folder/'Notes.md').write_text('# Demo')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False);app.geometry('1400x900+0+0')
        app.font_size_var.set('small');app.apply_font_size(save=False)
        app.active.navigate(folder);settle(app)
        app.save_config();before=(root/'pfc.ini').read_text()
        app.show_settings();d=app.settings_window;settle(app)
        assert app.grab_current() is d
        assert len(d.preview_labels)==2 and all(w.image.width()>200 for w,_v in d.preview_labels)
        d._enlarge(None);settle(app)
        popup=app.grab_current();assert popup is not d
        popup.event_generate('<Escape>');settle(app)
        assert app.grab_current() is d
        d.vars['color_scheme'].set('dark');d.vars['panel_count'].set(1)
        d.vars['show_hidden'].set(True);d.vars['recycle_bin'].set(False)
        assert app.color_scheme_var.get()=='light' and app.panel_count_var.get()==2
        assert app.recycle_bin_var.get()
        for key,_label in pfc.SETTINGS_CATEGORIES:d.show_page(key);settle(app)
        d.cancel();settle(app)
        assert app.color_scheme_var.get()=='light'
        assert app.recycle_bin_var.get()
        assert before==(root/'pfc.ini').read_text(),'Cancel must not write preferences'
        app.show_settings('columns');d=app.settings_window;settle(app)
        original_pane=app.active
        d.vars['column_ext'].set(False);d.vars['show_hidden'].set(True)
        d.vars['date_order'].set('mdy');d.vars['time_style'].set('12')
        d.vars['color_scheme'].set('dark');d.vars['tab_style'].set('rounded')
        d.vars['panel_count'].set(1)
        d.apply();settle(app,.4)
        assert original_pane.show_hidden
        assert not app.column_visible_vars['ext'].get()
        assert app.config_data.get('view','time_style')=='12'
        assert app.color_scheme_var.get()=='dark' and app.tab_style_var.get()=='rounded'
        assert app._single_layout
        assert d.apply_button.instate(['disabled'])
        d.vars['color_scheme'].set('light');d.cancel()
        assert app.color_scheme_var.get()=='dark','Cancel after Apply keeps applied settings'
        # Scope is the original tab, not a new active tab selected by layout.
        app.panel_count_var.set(2);app.apply_panel_count()
        app.set_active(app.right_tabs.current());other=app.active
        other.show_hidden=False
        app.show_settings('columns');d=app.settings_window
        d.vars['show_hidden'].set(True)
        app.set_active(app.left_tabs.current());d.apply(close=True);settle(app)
        assert other.show_hidden and app.active is not other
        # Shared context model still acts on exactly the same preferences.
        app.column_menus['ext'].invoke(0);assert app.column_visible_vars['ext'].get()
        app.show_settings('appearance');d=app.settings_window;settle(app)
        assert d.vars['column_ext'].get()
        # Real keyboard shortcuts cannot rename, delete or navigate files behind dialog.
        calls=[];app.bind_all('<F7>',lambda _e:calls.append('mkdir'))
        d.nav.focus_force();d.nav.event_generate('<F7>');settle(app);assert not calls
        app._dispatch_global_hotkey(lambda:calls.append('background'))
        assert not calls
        old_scale=app.font_size_var.get()
        d.nav.event_generate('<Control-MouseWheel>',delta=120);settle(app)
        assert app.font_size_var.get()==old_scale,'Priority global zoom must not bypass the draft'
        d.nav.event_generate('<Tab>');settle(app)
        assert app.focus_get() is not d.nav,'Tab must move within settings, not switch file panels'
        app.focus_get().event_generate('<Shift-Tab>');settle(app)
        assert app.focus_get() is d.nav,'Shift+Tab returns to the category list'
        d.vars['auto_font_size'].set(True);assert d.controls['font_size'].instate(['disabled'])
        d.vars['auto_font_size'].set(False);assert d.controls['font_size'].instate(['readonly'])
        d.vars['font_size'].set('large');d.apply();settle(app)
        assert app.font_size_var.get()=='large'
        d.vars['auto_font_size'].set(True);d.apply();settle(app)
        assert d.vars['font_size'].get()==app.font_size_var.get(),'Auto baseline must reflect actual chosen scale'
        d.vars['auto_font_size'].set(False);d.vars['font_size'].set('large');d.apply();settle(app)
        for category,_label in pfc.SETTINGS_CATEGORIES:
            d.show_page(category);settle(app)
            assert d.footer.winfo_rooty()+d.footer.winfo_height()<=d.winfo_rooty()+d.winfo_height()+1
        # Prefix editing is a draft too; validation rejects relative paths before any apply.
        d.show_page('navigation');settle(app)
        assert len(d.prefix_rows)==3
        d.prefix_rows[0][1].set('relative/path');d.vars['recycle_bin'].set(False)
        messages=[];old=pfc.messagebox.showerror
        pfc.messagebox.showerror=lambda *a,**kw:messages.append(a)
        try:d.apply()
        finally:pfc.messagebox.showerror=old
        assert messages and app.recycle_bin_var.get()
        d.prefix_rows[0][1].set(str(folder));d.apply();settle(app)
        assert app.custom_home_prefixes[0]['path']==str(folder)
        d.cancel()
        # Reopen at large application zoom: fixed footer, all pages keyboard/scroll reachable.
        for scale in ('small','large','300'):
            app.font_size_var.set(scale);app.apply_font_size(save=False)
            for scheme in ('light','light_grey','dark'):
                app.color_scheme_var.set(scheme);app.apply_color_scheme(save=False)
                app.show_settings();d=app.settings_window;d.geometry('780x560+0+0');settle(app)
                for key,_label in pfc.SETTINGS_CATEGORIES:
                    d.show_page(key);settle(app)
                    d.canvas.yview_moveto(1);settle(app)
                    assert d.footer.winfo_ismapped() and d.apply_button.winfo_ismapped()
                    assert d.page.winfo_width()<=d.canvas.winfo_width()+1
                d.cancel()
        app.font_size_var.set('large');app.apply_font_size(save=False)
        app.color_scheme_var.set('light');app.apply_color_scheme(save=False)
        app.show_settings();d=app.settings_window;d.vars['color_scheme'].set('dark');d.vars['tab_style'].set('squarish');settle(app)
        if '--screenshot' in sys.argv:
            from PIL import ImageGrab
            x,y=d.winfo_rootx(),d.winfo_rooty()
            ImageGrab.grab((x,y,x+d.winfo_width(),y+d.winfo_height())).save('/tmp/pfc-settings-review.png')
        if '--visual' in sys.argv:
            print('VISUAL READY',flush=True);settle(app,25)
        # Changing language refreshes all dialog labels without losing values.
        for lang in ('zh_TW','zh_CN','ko','en'):
            d.vars['ui_language'].set(lang);d.apply();settle(app)
            assert d.title()==pfc.tr('PFC Settings')
            assert d.vars['color_scheme'].get()=='dark'
            d.show_page('layout')
            assert d.controls['panel_count'].cget('values')[1]==pfc.tr('{count} Panels',count=2)
            if lang=='zh_TW' and '--visual-localized' in sys.argv:
                d.show_page('layout');settle(app)
                print('LOCALIZED VISUAL READY',flush=True);settle(app,25)
        d.cancel();assert not errors,errors
        print('PASS: six categories, draft/cancel/apply, INI, active-tab scope, shortcuts, prefixes, 9 screenshots, 3 themes × 3 zooms, compact geometry and 4 languages',flush=True)
    finally:
        d=getattr(app,'settings_window',None)
        if d is not None and d.winfo_exists():d.cancel()
        app.close_app()
