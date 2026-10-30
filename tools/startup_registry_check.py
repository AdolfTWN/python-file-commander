"""Isolated startup sorting/refresh and read-only Registry Preview user tasks."""
import configparser
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
module=sys.argv[1] if len(sys.argv)>1 else 'pycommander.app'
if '--case' not in sys.argv:
    for case in ('name','name-desc','modified','filtered','tabs','registry'):
        result=subprocess.run([sys.executable,__file__,module,'--case',case],
                              capture_output=True,text=True,timeout=50)
        assert result.returncode==0,(case,result.stdout,result.stderr)
        print(result.stdout.strip(),flush=True)
    raise SystemExit(0)

api=importlib.import_module(module);case=sys.argv[-1]
def pump(app,seconds=.15):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:app.update();time.sleep(.01)
def settle(app,page):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        app.update();time.sleep(.01)
        if page._span_job is None and not (page._format_jobs.pending or page._format_queued or page._format_request):return
    raise AssertionError('Preview did not settle')
def capture(win,name):
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(win,Path(__file__).parent/('evidence-'+name+'.bmp'))

with tempfile.TemporaryDirectory(prefix='pfc-startup-registry-') as raw:
    root=Path(raw);folders={}
    for name,count in (('left',250),('right',250),('empty',0)):
        folder=root/name;folder.mkdir();folders[name]=folder
        for i in range(count):
            path=folder/f'file-{i:04}.txt';path.write_text('x'*(i+1))
            os.utime(path,(1700000000+i,1700000000+i))
    config=configparser.ConfigParser()
    config.read_dict({'window':{'geometry':'1280x720+0+0'},
        'view':{'panel_count':'2','font_size':'small','auto_font_size':'false','extension_effect':'true'},
        'state':{'active_panel':'right'},'startup':{'auto_start':'false'}})
    for section in api.PANEL_SECTIONS:
        config[section]={'tabs':json.dumps([str(folders.get(section,folders['empty']))]),
            'sort_column':'modified' if case in ('modified','filtered','tabs') else 'name',
            'sort_descending':'true' if case!='name' else 'false'}
    if case=='filtered':config['right']['tab_filters']=json.dumps(['file-01'])
    if case=='tabs':
        config['right']['tabs']=json.dumps([str(folders['empty']),str(folders['right'])])
        config['right']['selected']='1'
    ini=root/'pfc.ini'
    with ini.open('w') as stream:config.write(stream)
    with patch.object(api.Commander,'_find_ini_path',return_value=ini), \
         patch.object(api.Commander,'_sync_auto_start'), \
         patch.object(api.Commander,'_start_windows_tray'):
        app=api.Commander()
    errors=[];app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        pump(app,.6)
        if case!='registry':
            for pane in (app.left,app.right):
                children=pane.tree.get_children()
                assert pane.tree.selection()==(children[0],),(case,pane.path,pane.tree.selection())
                assert pane.tree.yview()[0]==0,(case,pane.tree.yview())
                selected=children[len(children)*3//4]
                pane.tree.selection_set(selected);pane.tree.focus(selected);pane.tree.see(selected);pump(app)
                path=pane.selected_paths()[0];before=pane.tree.yview()[0]
                pane.refresh();pump(app)
                assert pane.selected_paths()==[path],'Normal refresh reset the selection'
                assert abs(pane.tree.yview()[0]-before)<=.008,'Normal refresh reset scroll position'
            if case=='modified':
                app.right.tree.yview_moveto(0);app.left.tree.yview_moveto(0);pump(app)
                capture(app,'startup-fixed')
            print(json.dumps(dict(case=case,startup_top=True,refresh_retained=True)))
        else:
            text=('Windows Registry Editor Version 5.00\r\n\r\n'
                  '; 唯讀測試😀 — never imported\r\n'
                  '[HKEY_CURRENT_USER\\Software\\PFC_Preview_MustNotImport]\r\n'
                  '@="預設😀 Needle"\r\n"Enabled"=dword:00000001\r\n'
                  '"Path"="C:\\\\Temp;#text"\r\n"Binary"=hex:01,ff,\\\r\n  10,00\r\n'
                  '"Multi"=hex(7):41,00,00,00,00,00\r\n"OldValue"=-\r\n'
                  '[-HKEY_CURRENT_USER\\Software\\PFC_Preview_DeleteExample]\r\n')
            registry_key='PFC_Preview_MustNotImport_'+root.name
            text=text.replace('PFC_Preview_MustNotImport',registry_key)
            reg=root/'sample.REG';reg.write_bytes(text.encode('utf-16'));original=reg.read_bytes()
            app.active.navigate(root);app.active.select_path(reg);pump(app)
            with patch.object(api.os,'startfile',create=True,side_effect=AssertionError('Preview attempted OS launch')):
                app.action_button_by_hotkey['F3'].invoke();pump(app)
                win=app.preview_window;page=win.active_page;settle(app,page)
                assert page.text.get('1.0','end-1c')==text
                assert 'syntax' in page.status.cget('text')
                for tag in ('syntax_heading','syntax_keyword','syntax_string','syntax_number','syntax_comment','syntax_deletion'):
                    assert page.text.tag_ranges(tag),(tag,page.status.cget('text'))
                ranges=page.text.tag_ranges('syntax_deletion')
                deleted=[page.text.get(ranges[i],ranges[i+1]) for i in range(0,len(ranges),2)]
                assert deleted==['-','[-HKEY_CURRENT_USER\\Software\\PFC_Preview_DeleteExample]'],deleted
                assert page.markdown_check.winfo_ismapped()
                capture(win,'registry-light')
                page.search_var.set('Needle');page.find_next();assert len(page.matches)==1
                page.wrap_var.set(True);page.set_wrap();assert page.text.cget('wrap')=='word'
                page.markdown_check.invoke();settle(app,page)
                assert page.text.get('1.0','end-1c')==text and not page.text.tag_ranges('syntax_heading')
                page.markdown_check.invoke();settle(app,page);assert page.text.tag_ranges('syntax_heading')
                page.text.tag_add('sel','1.0','end-1c');page._copy_preview()
                assert app.clipboard_get().replace('\r\n','\n')==text.replace('\r\n','\n')
                page.text.tag_remove('sel','1.0','end')
                page.mode_var.set(next(k for k,v in page.mode_values.items() if v=='Hex'));page.load()
                assert '00000000' in page.text.get('1.0','end')
                page.mode_var.set(next(k for k,v in page.mode_values.items() if v=='Auto'));page.load();settle(app,page)
                app.color_scheme_var.set('dark');app.apply_color_scheme(save=False)
                app.font_size_var.set('xl');app.apply_font_size(save=False);pump(app)
                win.geometry('1250x850+0+0');pump(app);capture(win,'registry-dark')
                assert page.text.tag_cget('syntax_deletion','foreground')=='#ff9298'
                large=root/'large.reg';large.write_text('REGEDIT4\n'+('"Blob"=hex:'+('ff,'*20)+'\n')*2000+'"Late"="TAIL_NEEDLE"\n')
                win.show([reg,large],large);page=win.active_page;settle(app,page)
                assert api.tr('Syntax highlighting limited; text and search remain available') in page.status.cget('text')
                page.search_var.set('TAIL_NEEDLE');page.find_next();assert len(page.matches)==1
                win.show([reg,large],reg);page=win.active_page;settle(app,page)
                assert page.text.get('1.0','end-1c')==text
                assert reg.read_bytes()==original
                if os.name=='nt':
                    import winreg
                    try:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Software\\'+registry_key):
                            raise AssertionError('Registry preview imported fixture')
                    except FileNotFoundError:pass
            print(json.dumps(dict(case=case,syntax=True,search=True,source_hex_wrap_tabs=True,read_only=True)))
        assert not errors,errors
    finally:app.destroy()
