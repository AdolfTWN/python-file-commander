"""Every Settings page keeps a safe, responsive draft preview above its options."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def settle(app):
    end=time.monotonic()+.12
    while time.monotonic()<end:
        app.update();time.sleep(.01)


def text_items(sample, tag):
    return [sample.canvas.itemcget(i,'text') for i in sample.canvas.find_withtag(tag)]


with tempfile.TemporaryDirectory(prefix='pfc-settings-previews-') as raw:
    root=Path(raw)
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        app.save_config();before=(root/'pfc.ini').read_bytes()
        app.show_settings('columns');d=app.settings_window;settle(app)
        sample=d.page_preview
        assert len(sample.rows)==4
        d.vars['show_hidden'].set(True);assert len(sample.rows)==5
        d.vars['show_system'].set(True);assert len(sample.rows)==6
        d.vars['show_extensions'].set(False)
        assert any(row['name']=='Notes' for row in sample.rows)
        d.vars['date_order'].set('mdy');d.vars['time_style'].set('12')
        assert '09/22/2026 0515p' in text_items(sample,'modified'),text_items(sample,'modified')
        d.vars['column_modified'].set(False);assert not sample.canvas.find_withtag('modified')
        d.vars['column_ext'].set(False);assert not sample.canvas.find_withtag('heading-ext')
        d.vars['size_emphasis'].set(True);assert text_items(sample,'size-unit')==['GB','TB']
        d.vars['size_emphasis'].set(False);assert not sample.canvas.find_withtag('size-unit')
        d.vars['onedrive_overlay'].set(False);d.vars['vcs_overlay'].set(False)
        off=len([i for i in sample.canvas.find_all() if sample.canvas.type(i)=='image'])
        d.vars['onedrive_overlay'].set(True);d.vars['vcs_overlay'].set(True)
        on=len([i for i in sample.canvas.find_all() if sample.canvas.type(i)=='image'])
        assert on==off+2
        d.show_page('navigation');settle(app);sample=d.page_preview
        d.vars['recycle_bin'].set(False)
        assert 'Permanent' in text_items(sample,'delete-policy')[0]
        d.vars['continue_errors'].set(False)
        assert 'stop' in text_items(sample,'error-policy')[0]
        d.prefix_rows[1][1].set(str(root/'Documents'))
        assert any('Docs' in text for text in text_items(sample,'prefix-sample'))
        d.show_page('preview');settle(app);sample=d.page_preview
        d.vars['extension_effect'].set(True);assert sample.canvas.find_withtag('markdown-table')
        d.vars['extension_effect'].set(False)
        assert '# Notes' in text_items(sample,'markdown-source')
        assert not sample.canvas.find_withtag('markdown-table')
        d.show_page('general');settle(app);sample=d.page_preview
        d.vars['ui_language'].set('zh_TW')
        assert '檔案' in text_items(sample,'language-menu')
        assert pfc.tr('Files')=='Files', 'Draft language must not change running UI'
        d.vars['auto_start'].set(False)
        assert 'manually' in text_items(sample,'startup-flow')[0]
        d.vars['auto_start'].set(True)
        assert 'automatically' in text_items(sample,'startup-flow')[0]
        d.cancel()
        assert (root/'pfc.ini').read_bytes()==before, 'Preview/cancel must not write settings'
        print('PASS: all draft examples react, language stays local, cancel has no effects',flush=True)
        for language in ('en','zh_TW','zh_CN','ko'):
            app.ui_language_var.set(language);app._apply_ui_language_now()
            for scheme in ('light','light_grey','dark'):
                app.color_scheme_var.set(scheme);app.apply_color_scheme(save=False)
                app.font_size_var.set('300');app.apply_font_size(save=False)
                app.show_settings();d=app.settings_window
                for geometry in ('1180x720+0+0','780x560+0+0'):
                    d.geometry(geometry);settle(app)
                    for category,_ in pfc.SETTINGS_CATEGORIES:
                        d.show_page(category);settle(app)
                        assert d.comparison.winfo_ismapped(), category
                        bottom=d.comparison.winfo_rooty()+d.comparison.winfo_height()
                        assert bottom<=d.canvas.winfo_rooty(),(category,geometry)
                        assert d.canvas.winfo_height()>=65,(category,language,geometry,d.canvas.winfo_height())
                        assert d.footer.winfo_rooty()+d.footer.winfo_height()<=d.winfo_rooty()+d.winfo_height()+1
                        top=d.comparison.winfo_rooty();d.canvas.yview_moveto(1);settle(app)
                        assert d.comparison.winfo_rooty()==top
                        if d.page_preview:
                            sample=d.page_preview
                            ids=sample.canvas.find_all();assert ids
                            for _ in range(5):d._changed()
                            assert ids==sample.canvas.find_all(),'Unchanged samples must not repaint'
                            width=sample.canvas.winfo_width();height=sample.canvas.winfo_height()
                            for item in sample.canvas.find_all():
                                if sample.canvas.type(item)=='text':
                                    x1,y1,x2,y2=sample.canvas.bbox(item)
                                    assert -2<=x1<=x2<=width+2,(category,language,geometry,'width',sample.canvas.itemcget(item,'text'),(x1,x2),width)
                                    assert -2<=y1<=y2<=height+2,(category,language,'height')
                        if '--screenshots' in sys.argv and language=='en' and scheme=='light':
                            from PIL import ImageGrab
                            x,y=d.winfo_rootx(),d.winfo_rooty()
                            ImageGrab.grab((x,y,x+d.winfo_width(),y+d.winfo_height())).save(
                                '/tmp/pfc-settings-'+category+('-compact' if '780' in geometry else '')+'.png')
                d.cancel()
            print('PASS: fixed-top previews, readable geometry, stable redraw at 300% in '+language,flush=True)
        assert not errors,errors
    finally:
        dialog=getattr(app,'settings_window',None)
        if dialog is not None and dialog.winfo_exists():dialog.cancel()
        app.close_app()
