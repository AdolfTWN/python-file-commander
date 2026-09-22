"""Capture sanitized PFC style samples. Build-only Pillow/Xvfb; no runtime dependency."""
import base64
import io
from pathlib import Path
import sys
import tempfile
import time
from PIL import ImageGrab

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pycommander import app as pfc

def settle(app):
    end=time.monotonic()+.5
    while time.monotonic()<end:app.update();time.sleep(.01)

with tempfile.TemporaryDirectory(prefix='pfc-style-demo-') as raw:
    folder=Path(raw)/'Projects';folder.mkdir()
    for name in ('Design','Documents'):(folder/name).mkdir()
    (folder/'Notes.md').write_text('# Demo only\n')
    (folder/'Release.txt').write_text('Sample files, no personal data.\n')
    pfc.Commander._find_ini_path=staticmethod(lambda:Path(raw)/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander()
    try:
        app.auto_font_size_var.set(False);app.font_size_var.set('small');app.apply_font_size(save=False)
        app.geometry('1100x700+0+0')
        pane=app.left_tabs.current();pane.navigate(folder);app.left_tabs.add_tab(folder/'Documents')
        app.left_tabs.select(pane);app.set_active(pane)
        app.custom_home_prefixes=[{'icon':'code','path':str(folder)}]
        pane.path_bar.redraw()
        pane.sort_column='name';pane.reverse=False;pane.refresh()
        shots={}
        for scheme in pfc.COLOR_SCHEMES:
            app.color_scheme_var.set(scheme);app.apply_color_scheme(save=False)
            for style in pfc.TAB_STYLES:
                app.tab_style_var.set(style);app.apply_tab_style(save=False);settle(app)
                widget=app.left_tabs
                x,y=widget.winfo_rootx(),widget.winfo_rooty()
                shot=ImageGrab.grab((x,y,x+min(540,widget.winfo_width()),y+210))
                buffer=io.BytesIO();shot.save(buffer,format='PNG',optimize=True)
                shots[scheme+'/'+style]=base64.b64encode(buffer.getvalue()).decode('ascii')
        content='"""Generated sanitized PFC screenshots at 100%; do not hand edit.\nBuild: xvfb-run -a python3 tools/build_settings_shots.py\n"""\nSETTINGS_SHOTS = {\n'
        content+=''.join(f'    {key!r}: {value!r},\n' for key,value in shots.items())+'}\n'
        (ROOT/'pycommander'/'settingsshots.py').write_text(content,encoding='utf-8')
        print('Generated',len(shots),'PFC screenshots;',len(content),'bytes')
    finally:app.close_app()
