"""Reading-scale controls across menus and persistent popup windows."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import font as tkfont, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = next((arg for arg in sys.argv[1:] if not arg.startswith('--')), 'pycommander.app')
pfc = importlib.import_module(module)
prefs = pfc if module == 'pfc' else importlib.import_module('pycommander.settings')
work = pfc if module == 'pfc' else importlib.import_module('pycommander.workflows')
audit = '--audit' in sys.argv


def settle(app, seconds=.12):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        app.update(); time.sleep(.005)


def face(widget):
    value = widget.cget('font') if 'font' in widget.keys() else ''
    value = value or ttk.Style(widget).lookup(widget.cget('style') or widget.winfo_class(), 'font')
    try: return tkfont.nametofont(str(value), root=widget)
    except tk.TclError: return tkfont.Font(widget, font=value)


def indicator(widget):
    style = ttk.Style(widget)
    def find(layout):
        for element, options in layout:
            if element.endswith('.indicator'):
                return int(style.lookup(widget.cget('style') or widget.winfo_class(), 'indicatorsize') or 0), element
            found = find(options.get('children', []))
            if found: return found
    return find(style.layout(widget.cget('style') or widget.winfo_class()))


def capture(window, name):
    if '--screenshots' not in sys.argv and sys.platform != 'win32': return
    hidden = [w for w in window._root().winfo_children()
              if isinstance(w, tk.Toplevel) and w is not window and w.winfo_ismapped()]
    try:
        for other in hidden: other.withdraw()
        window.lift(); window.update(); time.sleep(.12); window.update()
        x, y = window.winfo_rootx(), window.winfo_rooty()
        path = Path(__file__).parent/('evidence-control-'+name+'.bmp') if sys.platform == 'win32' else Path('/tmp')/('pfc-control-'+name+('-before' if audit else '-after')+'.png')
        if sys.platform == 'win32':
            native_capture(window, path)
        else:
            from PIL import ImageGrab
            ImageGrab.grab((x, y, x+window.winfo_width(), y+window.winfo_height())).save(path)
    finally:
        for other in hidden:
            if other.winfo_exists(): other.deiconify()


def native_capture(window, path):
    # Match the existing review fixture: GDI capture needs no guest packages.
    import ctypes as c
    from ctypes import wintypes as w
    import struct
    user, gdi = c.WinDLL('user32'), c.WinDLL('gdi32')
    user.GetAncestor.argtypes=[w.HWND,w.UINT];user.GetAncestor.restype=w.HWND
    user.SetForegroundWindow.argtypes=[w.HWND]
    user.SetForegroundWindow(user.GetAncestor(window.winfo_id(),2));settle(window._root(), .25)
    user.GetDC.argtypes=[w.HWND];user.GetDC.restype=w.HDC
    user.ReleaseDC.argtypes=[w.HWND,w.HDC]
    gdi.CreateCompatibleDC.argtypes=[w.HDC];gdi.CreateCompatibleDC.restype=w.HDC
    gdi.CreateCompatibleBitmap.argtypes=[w.HDC,c.c_int,c.c_int];gdi.CreateCompatibleBitmap.restype=w.HBITMAP
    gdi.SelectObject.argtypes=[w.HDC,w.HGDIOBJ];gdi.SelectObject.restype=w.HGDIOBJ
    gdi.DeleteObject.argtypes=[w.HGDIOBJ];gdi.DeleteDC.argtypes=[w.HDC]
    gdi.BitBlt.argtypes=[w.HDC,c.c_int,c.c_int,c.c_int,c.c_int,w.HDC,c.c_int,c.c_int,w.DWORD]
    gdi.GetDIBits.argtypes=[w.HDC,w.HBITMAP,w.UINT,w.UINT,c.c_void_p,c.c_void_p,w.UINT]
    width,height=window.winfo_width(),window.winfo_height()
    screen=user.GetDC(None);dc=gdi.CreateCompatibleDC(screen)
    bitmap=gdi.CreateCompatibleBitmap(screen,width,height);old=gdi.SelectObject(dc,bitmap)
    try:
        assert gdi.BitBlt(dc,0,0,width,height,screen,window.winfo_rootx(),window.winfo_rooty(),0x00CC0020)
        gdi.SelectObject(dc,old)
        info=struct.pack('<IiiHHIIiiII',40,width,height,1,32,0,width*height*4,0,0,0,0)
        header=c.create_string_buffer(info);pixels=c.create_string_buffer(width*height*4)
        assert gdi.GetDIBits(dc,bitmap,0,height,pixels,header,0)==height
        assert len(set(pixels.raw))>16, 'Blank native capture is not visual acceptance'
        path.write_bytes(struct.pack('<2sIHHI',b'BM',54+len(pixels.raw),0,0,54)+info+pixels.raw)
    finally:
        gdi.SelectObject(dc,old);gdi.DeleteObject(bitmap);gdi.DeleteDC(dc);user.ReleaseDC(None,screen)


with tempfile.TemporaryDirectory(prefix='pfc-control-scale-') as raw:
    root = Path(raw)
    pfc.Commander._find_ini_path = staticmethod(lambda: root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda *a, **k: True
    pfc.Commander._start_windows_tray = lambda *a: None
    app = pfc.Commander(); errors = []; windows = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False); app.geometry('1280x850+0+0')
        files = [root/'Left.md', root/'Right.md']
        for i, path in enumerate(files): path.write_text('# Notes\n\nvalue '+str(i)+'\n')
        app.active.navigate(root)
        app.font_size_var.set('small'); app.apply_font_size(save=False); settle(app)
        app.search(); search = app.search_window
        search.geometry('1100x760+0+0')
        rename = pfc.MultiRenameWindow(app, files, [], lambda: None); windows.append(rename)
        compare = pfc.CompareWindow(app, app.config_data, lambda: None); windows.append(compare)
        frame = compare.add(*files); compare.geometry('1100x760+0+0')
        picker = work.CommandPalette(app, [('Sample', 'Test', 'Ctrl+P', 'sample', lambda: None)])
        windows.append(picker); picker.grab_release()
        # Covers default controls used by conflicts and the folder-tree header.
        choices = tk.Toplevel(app); windows.append(choices)
        flag = tk.BooleanVar(choices, True); choice = tk.IntVar(choices, 1)
        check = ttk.Checkbutton(choices, text='Enabled', variable=flag); check.pack()
        radio = ttk.Radiobutton(choices, text='Selected', variable=choice, value=1); radio.pack()
        spin = ttk.Spinbox(choices, from_=1, to=5, width=4); spin.pack()
        menu = tk.Menu(choices, tearoff=False)
        pfc.add_scaled_checkbutton(menu, 'Enabled', flag)
        pfc.add_scaled_radiobutton(menu, 'Selected', 1, choice)
        records = []
        for level in ('small', 'large', '175', 'xl', '300', 'small'):
            app.font_size_var.set(level); app.apply_font_size(save=False)
            compare.apply_scale(app._font_scales[level]); settle(app)
            expected = tkfont.nametofont('TkDefaultFont').metrics('linespace')
            widgets = {'Compare': frame.view.search, 'Workflow': picker.entry,
                       'Rename check': next(w for w in rename.winfo_children()[0].winfo_children()
                                            if isinstance(w, ttk.Checkbutton)),
                       'Default check': check, 'Default radio': radio, 'Spinbox': spin}
            result = {'scale': round(app._font_scales[level]*100), 'expected': expected,
                      'fonts': {name: face(widget).metrics('linespace') for name, widget in widgets.items()},
                      'indicators': {name: indicator(widget) for name, widget in widgets.items()
                                     if isinstance(widget, (ttk.Checkbutton, ttk.Radiobutton))}}
            records.append(result)
            if level == 'xl': capture(compare, 'compare-200'); capture(rename, 'rename-200')
            if not audit:
                assert all(value == expected for value in result['fonts'].values()), result
                assert int(ttk.Style(picker).lookup('PFCWorkflow.Treeview', 'rowheight')) == expected+8
                assert rename.apply_button.winfo_ismapped(), ('Rename actions clipped', level)
                assert rename.apply_button.winfo_rooty()+rename.apply_button.winfo_height() <= rename.winfo_rooty()+rename.winfo_height()
                for widget in (check, radio):
                    assert indicator(widget)[0] == max(18, tkfont.nametofont('TkDefaultFont').metrics('linespace')), result
                # Keyboard must toggle the scaled check using the same variable.
                before = flag.get(); check.invoke(); assert flag.get() != before; check.invoke()
                assert str(menu.cget('font')) == 'TkMenuFont'
                assert int(menu.entrycget(0, 'indicatoron')) == 0
                check.focus_force(); settle(app); check.event_generate('<space>'); settle(app)
                assert flag.get() != before; check.invoke()
                # Exercise the actual blocking confirmation API and modal return.
                picker.grab_set()
                def dismiss():
                    dialog = next(w for w in app.winfo_children()
                                  if getattr(w, '_pfc_message_dialog', False))
                    assert face(dialog.buttons['cancel']).metrics('linespace') == expected
                    if level == 'xl': capture(dialog, 'confirmation-200')
                    dialog.choose('cancel')
                app.after(60, dismiss)
                assert pfc.messagebox.askyesnocancel('PFC', 'Save the modified document?', parent=app) is None
                assert app.grab_current() is picker
                picker.grab_release()
            app.show_settings(); dialog = app.settings_window; settle(app)
            if not audit:
                app.font_size_var.set('small' if level != 'small' else 'xl')
                app.apply_font_size(save=False); settle(app)
                assert dialog.font.metrics('linespace') == tkfont.nametofont('TkDefaultFont').metrics('linespace')
                app.font_size_var.set(level); app.apply_font_size(save=False); settle(app)
            for category, _ in pfc.SETTINGS_CATEGORIES:
                dialog.show_page(category); settle(app, .03)
                if not audit:
                    assert dialog.font.metrics('linespace') == expected
                    assert dialog.footer.winfo_rooty()+dialog.footer.winfo_height() <= dialog.winfo_rooty()+dialog.winfo_height()+1
                    if sys.platform == 'win32':
                        assert dialog.footer.winfo_rooty()+dialog.footer.winfo_height() <= dialog._work_area[3]-8
                if level == 'xl' and category in ('appearance', 'layout'):
                    capture(dialog, 'settings-'+category+'-200')
            dialog.cancel()
        print(json.dumps(records))
        assert not errors, errors
        print('PASS: controls and menus follow 100–300% zoom, live resizing, keyboard state and Settings pages' if not audit else 'AUDIT: pre-change reading-scale evidence collected')
    finally:
        for window in reversed(windows):
            if window.winfo_exists(): window.destroy()
        app.close_app()
