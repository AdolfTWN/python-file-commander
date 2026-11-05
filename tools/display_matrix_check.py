"""Lease-only native display modes; no registry writes; worker restores on timeout."""
import ctypes as c
from ctypes import wintypes as w
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time


class DevMode(c.Structure):
    _fields_ = [('dmDeviceName',w.WCHAR*32),('dmSpecVersion',w.WORD),('dmDriverVersion',w.WORD),
                ('dmSize',w.WORD),('dmDriverExtra',w.WORD),('dmFields',w.DWORD),
                ('display_union',c.c_byte*16),('dmColor',c.c_short),('dmDuplex',c.c_short),
                ('dmYResolution',c.c_short),('dmTTOption',c.c_short),('dmCollate',c.c_short),
                ('dmFormName',w.WCHAR*32),('dmLogPixels',w.WORD),('dmBitsPerPel',w.DWORD),
                ('dmPelsWidth',w.DWORD),('dmPelsHeight',w.DWORD),('dmDisplayFlags',w.DWORD),
                ('dmDisplayFrequency',w.DWORD),('dmICMMethod',w.DWORD),('dmICMIntent',w.DWORD),
                ('dmMediaType',w.DWORD),('dmDitherType',w.DWORD),('dmReserved1',w.DWORD),
                ('dmReserved2',w.DWORD),('dmPanningWidth',w.DWORD),('dmPanningHeight',w.DWORD)]


class NativeModes:
    def __init__(self):
        assert os.name=='nt' and c.sizeof(DevMode)==220
        self.user=c.WinDLL('user32',use_last_error=True)
        self.user.EnumDisplaySettingsW.argtypes=[w.LPCWSTR,w.DWORD,c.POINTER(DevMode)]
        self.user.EnumDisplaySettingsW.restype=w.BOOL
        self.user.ChangeDisplaySettingsExW.argtypes=[w.LPCWSTR,c.POINTER(DevMode),w.HWND,w.DWORD,w.LPVOID]
        self.user.ChangeDisplaySettingsExW.restype=w.LONG
        self.original=self.current()

    def get(self,index):
        mode=DevMode();mode.dmSize=c.sizeof(mode)
        return mode if self.user.EnumDisplaySettingsW(None,index,c.byref(mode)) else None

    def current(self):
        mode=self.get(0xffffffff)
        if mode is None:raise OSError('Cannot read current display mode')
        return mode

    @staticmethod
    def dimensions(mode):
        return (mode.dmPelsWidth,mode.dmPelsHeight,mode.dmBitsPerPel,mode.dmDisplayFrequency)

    def modes(self):
        found={}
        for index in range(1024):
            mode=self.get(index)
            if mode is None:break
            if mode.dmBitsPerPel==32:found.setdefault((mode.dmPelsWidth,mode.dmPelsHeight),mode)
        return found

    def set(self,mode,test=False):
        clone=DevMode.from_buffer_copy(bytes(mode))
        clone.dmFields=0x40000|0x80000|0x100000  # bpp, width, height only
        return self.user.ChangeDisplaySettingsExW(None,c.byref(clone),None,2 if test else 0,None)

    def restore(self):
        if self.dimensions(self.current())[:3]!=self.dimensions(self.original)[:3]:
            result=self.set(self.original)
            if result!=0:raise OSError('Display restoration failed: '+str(result))
        assert self.dimensions(self.current())[:3]==self.dimensions(self.original)[:3]


def pump(app,seconds=.4):
    until=time.monotonic()+seconds
    while time.monotonic()<until:app.update();time.sleep(.01)


def controls(app):
    for item in [app.zoom_combo,*(b for b,_,_ in app.action_buttons)]:
        assert item.winfo_ismapped(),('Control unmapped',str(item))
        assert item.winfo_rootx()+item.winfo_width()<=app.winfo_rootx()+app.winfo_width()+1,'Control beyond right edge'
        assert item.winfo_rooty()+item.winfo_height()<=app.winfo_rooty()+app.winfo_height()+1,'Control below bottom edge'


def main():
    if os.name!='nt':
        print('SKIP: native display changes require leased Windows');return
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')
    modes=NativeModes();inventory=modes.modes()
    print(json.dumps({'event':'native.display.inventory','current':modes.dimensions(modes.original),
                      'modes':list(inventory),'heads':modes.user.GetSystemMetrics(80)}),flush=True)
    selected=[s for s in ((1280,720),(1366,768),(1600,900),(1920,1080),(2560,1440),(3840,2160)) if s in inventory]
    with tempfile.TemporaryDirectory(prefix='pfc-native-display-') as raw:
        folder=Path(raw);ini=folder/'pfc.ini'
        ini.write_text('[window]\ngeometry=1800x1000+0+0\n[view]\nauto_font_size=false\n',encoding='utf-8')
        for i in range(60):(folder/f'Report {i:03} 長檔名.txt').write_text('Synthetic data')
        pfc.Commander._find_ini_path=staticmethod(lambda:ini)
        pfc.Commander._sync_auto_start=lambda *a,**k:True
        pfc.Commander._start_windows_tray=lambda *a:None
        app=pfc.Commander();errors=[]
        app.report_callback_exception=lambda *exc:errors.append(str(exc))
        try:
            app.auto_font_size_var.set(False)
            for pane in app.visible_panes():pane.navigate(folder)
            pump(app)
            for resolution in selected:
                mode=inventory[resolution];test=modes.set(mode,test=True)
                print(json.dumps({'event':'native.display.mode.test','resolution':resolution,'result':test}),flush=True)
                if test!=0:continue
                assert modes.set(mode)==0
                pump(app,2.6)
                assert modes.dimensions(modes.current())[:2]==resolution
                for level in ('medium','large','xl','300'):
                    app.font_size_var.set(level);app.select_manual_font_size()
                    app._window_visibility.recover();pump(app);controls(app)
                app.font_size_var.set('large');app.select_manual_font_size()
                app.search();pump(app);s=app.search_window
                s._window_visibility.recover();pump(app)
                assert s.winfo_ismapped() and s.mask_entry.winfo_width()>=60
                s.close()
                print(json.dumps({'event':'native.display.mode.passed','resolution':resolution,
                                  'client':[app.winfo_width(),app.winfo_height()]}),flush=True)
            assert not errors,errors
        finally:
            app.close_app();modes.restore()
            print(json.dumps({'event':'native.display.restored','mode':modes.dimensions(modes.current())}),flush=True)


if __name__=='__main__':main()
