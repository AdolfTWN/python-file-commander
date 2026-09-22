"""Deterministic screenshots and geometry checks for workflow UI dogfooding."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
import os
import subprocess

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def settle(app, seconds=.15):
    end=time.monotonic()+seconds
    while time.monotonic()<end: app.update();time.sleep(.01)

def screenshot(widget, name):
    directory=Path(__file__).resolve().parent/'workflow-visuals' if os.name=='nt' else Path('/tmp/pfc-workflow-visuals')
    directory.mkdir(parents=True,exist_ok=True)
    x,y=widget.winfo_rootx(),widget.winfo_rooty()
    filename=directory/(name+'.png')
    if os.name=='nt':
        # Stock .NET screen capture: the offline guest needs no Pillow install.
        width,height=widget.winfo_width(),widget.winfo_height()
        command=(f'Add-Type -AssemblyName System.Drawing; '
            f'$shot=New-Object Drawing.Bitmap {width},{height}; '
            '$graphics=[Drawing.Graphics]::FromImage($shot); '
            f'$graphics.CopyFromScreen({x},{y},0,0,$shot.Size); '
            f"$shot.Save('{filename.absolute()}',[Drawing.Imaging.ImageFormat]::Png); "
            '$graphics.Dispose(); $shot.Dispose()')
        subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],
                       check=True,creationflags=0x08000000)
    else:
        from PIL import ImageGrab
        ImageGrab.grab((x,y,x+widget.winfo_width(),y+widget.winfo_height())).save(filename)

def inside(widget):
    parent=widget.master
    return (widget.winfo_ismapped() and widget.winfo_width()>5 and
        widget.winfo_rootx()>=parent.winfo_rootx() and
        widget.winfo_rootx()+widget.winfo_width()<=parent.winfo_rootx()+parent.winfo_width()+1 and
        widget.winfo_rooty()+widget.winfo_height()<=parent.winfo_rooty()+parent.winfo_height()+1)

with tempfile.TemporaryDirectory(prefix='pfc-visual-') as raw:
    root=Path(raw);left=root/'Project-A';right=root/'Project-B';left.mkdir();right.mkdir()
    for index in range(12):
        (left/f'report-v{index:02d}.md').write_text(f'# Report\n\nVersion {index}\n',encoding='utf-8')
        (right/f'report-v{index:02d}.md').write_text(f'# Report\n\nVersion {index+1}\n',encoding='utf-8')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[];app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False);app.geometry('1180x760+0+0')
        for index, tabs in enumerate(app.panel_tabs):
            tabs.current().navigate(left if index % 2 == 0 else right)
        for scale in ('small','large','300'):
            app.font_size_var.set(scale);app.apply_font_size(save=False)
            for theme in ('light','dark'):
                app.color_scheme_var.set(theme);app.apply_color_scheme(save=False);settle(app)
                screenshot(app,f'main-{scale}-{theme}')
                app.show_command_palette();settle(app);palette=app.grab_current()
                assert inside(palette.entry) and inside(palette.list) and inside(palette.hint)
                screenshot(palette,f'commands-{scale}-{theme}');palette.close()
                picker=app.show_workspace_picker();settle(app)
                assert inside(picker.open_button) and inside(picker.remove_button)
                screenshot(picker,f'workspaces-{scale}-{theme}');picker.close()
                app.compare_paths(left,right);cw=app.compare_window;cw.geometry('1024x680+0+0');settle(app,.4)
                fc=cw.current_comparison()
                fc.content_var.set(True);fc.start_scan()
                deadline=time.monotonic()+12
                while fc._scanning:
                    assert time.monotonic()<deadline,'Compare did not finish'
                    settle(app,.05)
                settle(app)
                screenshot(cw,f'compare-{scale}-{theme}')
                if '--strict' in sys.argv:
                    for widget in (fc.search,fc.previous_button,fc.next_button,fc.exclude_button):
                        assert inside(widget),(scale,theme,str(widget),'clipped')
                    for tree in fc._trees():
                        widths=sum(tree.column(c,'width') for c in ('#0','action','detail'))
                        assert widths<=tree.winfo_width()+2,(scale, widths, tree.winfo_width())
                cw.close();app.compare_window=None
        assert not errors,errors
        print('Workflow visual matrix captured: 3 zooms × 2 themes',flush=True)
    finally: app.close_app()
