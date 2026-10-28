"""Representative task/configuration walkthrough and actual-size visual evidence.

The baseline checkout may be supplied through PFC_AUDIT_ROOT. Never touches the
VM, production folders or operator settings. Not exhaustive pairwise coverage.
"""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

sys.path.insert(0,os.environ.get('PFC_AUDIT_ROOT',str(Path(__file__).resolve().parents[1])))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')
dialogs=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.dialogs')
work=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.workflows')
data=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.workflowdata')
baseline='--baseline' in sys.argv

def pump(root,seconds=.12):
    end=time.monotonic()+seconds
    while time.monotonic()<end:root.update();time.sleep(.005)

def capture(window,name):
    window.lift();pump(window,.2)
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/('evidence-deep-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save(
            '/tmp/pfc-deep-'+name+('-before' if baseline else '-after')+'.png')

def reachable(widget,window):
    assert widget.winfo_ismapped(),str(widget)
    x,y=widget.winfo_rootx()-window.winfo_rootx(),widget.winfo_rooty()-window.winfo_rooty()
    assert 0<=x and 0<=y and x+widget.winfo_width()<=window.winfo_width()+2 and y+widget.winfo_height()<=window.winfo_height()+2,(str(widget),x,y,window.geometry())

with tempfile.TemporaryDirectory(prefix='pfc-surface-') as raw:
    root=Path(raw);folder=root/'Deep project';folder.mkdir()
    files=[folder/'notes.md',folder/'settings.json',folder/'report.csv']
    for path,text in zip(files,('# Notes\n\nalpha beta\n',json.dumps(dict(device=dict(name='alpha',description='long value '*40))), 'Name,Value\nalpha,1\n')):path.write_text(text,encoding='utf-8')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True;pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();app.auto_font_size_var.set(False);errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc));records=[]
    try:
        for index,(scale,width,language,theme,panels) in enumerate((
            ('small',1500,'en','light',2),('large',1280,'zh_TW','dark',1),
            ('xl',760,'en','light',2),('300',900,'zh_CN','dark',1),
            ('large',1500,'ko','light',4),('medium',1000,'en','dark',3))):
            app.ui_language_var.set(language);app.apply_ui_language()
            app.color_scheme_var.set(theme);app.apply_color_scheme(save=False)
            app.font_size_var.set(scale);app.apply_font_size(save=False)
            app.panel_count_var.set(panels);app.apply_panel_count(save=False)
            app.geometry(f'{width}x900+0+0');app.active.navigate(folder);pump(app)
            # All settings categories and draft isolation, not just initial page.
            app.show_settings();settings=app.settings_window;settings.geometry(f'{width}x850+0+0');pump(app)
            for category,_ in pfc.SETTINGS_CATEGORIES:
                settings.show_page(category);pump(app,.06)
                if not baseline:
                    reachable(settings.footer,settings)
                    assert settings.canvas.winfo_height()>80,'No usable settings content'
            settings.cancel();pump(app)
            long_path=folder/('Long context '+('build evidence '*8))/('Unicode_說明_'+('module '*12)+'.md')
            dialog=pfc.ConflictDialog(app,long_path,root/'Archive'/long_path.name)
            dialog.geometry(f'{min(width,dialog.winfo_reqwidth() if dialog.winfo_reqwidth()>100 else width)}x600');pump(app)
            if index==1:capture(dialog,'conflict')
            if not baseline:
                for button in dialog.buttons.values():reachable(button,dialog)
                assert dialog.all_check.winfo_reqwidth()<dialog.winfo_width()
                assert str(long_path) in dialog.path_text.get('1.0','end')
            dialog.choose('cancel');pump(app)
            message=dialogs.ScaledMessageDialog(app,dict(type='yesnocancel',title='Isolated recovery',
                message='Review before changing files',detail=str(long_path)))
            pump(app)
            if index==1:capture(message,'confirmation')
            if not baseline:
                for button in message.buttons.values():reachable(button,message)
            message.choose('cancel');pump(app)
            if hasattr(dialogs,'ScaledInputDialog'):
                prompt=dialogs.ScaledInputDialog(app,'Input','Choose a name\n'+str(long_path),'string',dict(initialvalue='Project review'))
                pump(app)
                if index==1:capture(prompt,'input')
                reachable(prompt.entry,prompt);reachable(prompt.ok_button,prompt);prompt.cancel()
                prompt=dialogs.ScaledInputDialog(app,'Number','Choose a bounded value','integer',dict(minvalue=0,maxvalue=999999))
                prompt.geometry(f'{min(width,900)}x500');prompt.entry.insert(0,'invalid');prompt.accept();pump(app)
                for control in (prompt.error,prompt.entry,prompt.ok_button,prompt.cancel_button):reachable(control,prompt)
                prompt.cancel()
            records_store=data.WorkflowRecords(app.config_data,'audit')
            for n in range(30):records_store.put('Project '+str(n),dict(path=str(long_path)+str(n)))
            picker=work.WorkflowPicker(app,'Workspaces',records_store,lambda:None,lambda:None,lambda d:False,lambda d:d['path'])
            picker.geometry(f'{min(width,1100)}x750+0+0');pump(app)
            if index==1:capture(picker,'saved-workflows')
            if not baseline:
                picker.query.set('Project 29');pump(app);assert len(picker.entries)==1
                for b in (picker.open_button,picker.remove_button,picker.save_button,picker.details_button):reachable(b,picker)
            picker.close()
            result=pfc.OperationResult(skipped=[long_path],failures=[pfc.OperationFailure(long_path,root/'Archive', 'Destination is read-only. '+('Full recoverable detail '*12))])
            before=set(app.winfo_children())
            window=app._show_operation_result('Copy',result,retry=lambda paths:None)
            if window is None:window=next(w for w in app.winfo_children() if w not in before and isinstance(w,pfc.tk.Toplevel))
            pump(app)
            if index==1:capture(window,'operation-result')
            if not baseline:
                for b in (window.copy_button,window.retry_button,window.close_button):reachable(b,window)
            window.destroy();pump(app)
            if not baseline:
                gate=threading.Event()
                def slow(items,target,resolver,continue_errors):
                    gate.wait(4);return pfc.OperationResult(skipped=list(items))
                progress=pfc.TransferProgress(app,'Copy',slow,files,root/'Destination',lambda *a:'skip',True)
                progress.geometry(f'{min(width,1000)}x650');pump(app)
                if index==1:capture(progress,'transfer')
                for control in (progress.status,progress.cancel_button,progress.target_entry,progress.detail):reachable(control,progress)
                progress.cancel();gate.set();deadline=time.monotonic()+5
                while progress.winfo_exists():
                    assert time.monotonic()<deadline,'Transfer cancellation did not settle';pump(app,.02)
            app.show_command_palette();palette=app.grab_current();pump(app)
            if not baseline:
                palette.query.set('no command could have this label');pump(app)
                assert not palette.filtered
                palette.entry.event_generate('<Return>');pump(app);assert palette.winfo_exists()
            palette.close()
            app.show_debug_log();pump(app)
            for child in list(app.winfo_children()):
                if isinstance(child,pfc.tk.Toplevel) and child.winfo_exists():child.destroy()
            records.append(dict(scale=scale,width=width,language=language,theme=theme,panels=panels,settings_categories=len(pfc.SETTINGS_CATEGORIES)))
        if not baseline:assert not errors,errors
        print(json.dumps(dict(baseline=baseline,configurations=records,callback_errors=errors)))
    finally:app.close_app()
