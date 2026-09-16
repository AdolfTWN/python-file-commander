"""GUI regression for name animation, event forwarding and context preferences."""
import configparser
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def settle(app, seconds=.15):
    end = time.monotonic()+seconds
    while time.monotonic()<end:
        app.update(); time.sleep(.01)


def main():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)/'files'; root.mkdir()
        long = root / ('Project_2026_Draft_' + 'long_descriptive_name_'*5 + 'v1.9.0_R4.6.zip')
        long.write_text('not an archive')
        cjk = root / ('中文長檔名測試_'*5 + 'v2.3_Final.txt'); cjk.write_text('text')
        short = root/'short.txt'; short.write_text('text')
        folder = root/('Folder_with_a_long_readable_name_'*3); folder.mkdir()
        for index in range(35): (root/f'z-{index:02}.txt').write_text('text')
        module.Commander._find_ini_path = staticmethod(lambda: Path(raw)/'pfc.ini')
        module.Commander._sync_auto_start = lambda self, **kw: True
        app = module.Commander(); errors = []
        app.report_callback_exception = lambda *exc: errors.append(str(exc))
        try:
            app.auto_font_size_var.set(False); app.geometry('1200x720')
            app.font_size_var.set('small'); app.apply_font_size(save=False)
            pane = app.left_tabs.current(); pane.navigate(root); app.set_active(pane)
            tree = pane.tree; m = pane.name_marquee
            def choose(path):
                def find(parent=''):
                    for row in tree.get_children(parent):
                        if tree.item(row,'tags') and Path(tree.item(row,'tags')[0]) == path:
                            return row
                        nested=find(row)
                        if nested: return nested
                row=find(); assert row,path
                tree.selection_set(row); tree.focus(row); tree.see(row)
                tree.focus_force(); m.request(); settle(app)
                return tree.focus()
            iid = choose(long)
            assert tree.item(iid,'text') == long.name, (iid, tree.item(iid,'text'),long.name)
            assert m.item == iid and m.canvas.winfo_ismapped(), (m.item, iid, tree.focus_get())
            assert m.canvas.coords(m.text_id)[0] == 0
            assert not pane._tooltip_name(iid)
            settle(app,1.15)
            assert m.canvas.coords(m.text_id)[0] < -5
            assert tree.item(iid,'text') == long.name
            assert len([p for p in app.all_panes() if p.name_marquee.item]) == 1
            # The UI never rewrites an identifier to create the animation.
            assert pane.selected_paths() == [long]
            other_row=next(row for row in tree.get_children() if tree.item(row,'text') == short.name)
            tree.selection_add(other_row); settle(app)
            assert m.item == tree.focus() and len(tree.selection()) == 2
            tree.yview_moveto(1); settle(app); assert not m.item and m.job is None
            choose(long)
            pane.refresh(); settle(app)
            iid=tree.focus()
            assert pane.selected_paths() == [long] and tree.item(iid,'text') == long.name and m.item == iid
            assert not hasattr(pane,'_context_dwell_job')
            calls=[]
            original_context, original_native = pane.on_context, pane.on_native_context
            pane.on_context=lambda *args: calls.append(('pfc',args))
            pane.on_native_context=lambda *args: calls.append(('explorer',args))
            for mode in ('pfc','explorer'):
                app.right_click_menu_var.set(mode); choose(long)
                canvas=m.canvas
                canvas.event_generate('<ButtonRelease-3>',x=12,y=6)
                settle(app)
                assert calls[-1][0] == mode and calls[-1][1][1] == long
                pane._context_keyboard(); assert calls[-1][0] == mode
            # Pointer forwarding preserves coordinates and modifier state.
            choose(long); forwarded=[]
            binding=tree.bind('<Motion>',lambda e: forwarded.append((e.x_root,e.y_root,e.state)),add='+')
            m.canvas.event_generate('<Motion>',x=8,y=7,state=4)
            assert forwarded[-1] == (m.canvas.winfo_rootx()+8,m.canvas.winfo_rooty()+7,4)
            tree.unbind('<Motion>',binding)
            # Double-click is recognized from raw presses, not separately replayed.
            opened=[]
            tree.bind('<Double-1>',lambda e: opened.append(tree.identify_row(e.y)))
            choose(long)
            x=m.canvas.winfo_rootx()+8; y=m.canvas.winfo_rooty()+7
            for stamp in (10000,10100):
                if not m.item: m.start()
                event=SimpleNamespace(x_root=x,y_root=y,state=0,time=stamp)
                m._forward(event,'<ButtonPress-1>'); m._forward(event,'<ButtonRelease-1>')
                settle(app,.03)
            assert opened == [iid], opened
            choose(long); gestures=[]
            original_drag=pane.on_drag
            pane.on_drag=lambda action,*args: gestures.append(action)
            event=SimpleNamespace(x_root=m.canvas.winfo_rootx()+8,
                                  y_root=m.canvas.winfo_rooty()+7,state=0,time=20000)
            try:
                m._forward(event,'<ButtonPress-1>')
                event.x_root+=30; event.state=256; event.time+=100
                m._forward(event,'<Motion>')
                m._forward(event,'<ButtonRelease-1>')
                assert gestures == ['start','drop'],gestures
                assert pane._drag_press_item is None
            finally: pane.on_drag=original_drag
            choose(short); assert not m.item and m.job is None
            choose(cjk); assert m.item and tree.item(tree.focus(),'text') == cjk.name
            for mode, target in (('folder',folder),('file',long),('list',long)):
                pane.set_view_mode(mode); choose(target)
                assert m.item and m.canvas.winfo_x() > tree.bbox(tree.focus(),'#0')[0]
            for scale in module.FONT_SCALES:
                app.font_size_var.set(scale); app.apply_font_size(save=False); choose(long)
                assert m.item and m.speed == 36*module.FONT_SCALES[scale]
            for scheme in ('light','light_grey','dark'):
                app.color_scheme_var.set(scheme); app.apply_color_scheme(save=False); choose(long)
                assert m.item
            app.font_size_var.set('small'); app.apply_font_size(save=False); choose(long)
            pane.path_bar.begin_edit(); settle(app); assert not m.item and m.job is None
            pane.path_bar.cancel(); choose(long)
            pane._inline_editor = object(); m.tick(); assert not m.item
            pane._inline_editor=None; choose(long)
            pane._drag_press_item=iid; m.tick(); assert not m.item
            pane._drag_press_item=None; choose(long)
            other=app.right_tabs.current(); app.set_active(other); other.tree.focus_force()
            settle(app); assert not m.item
            app.set_active(pane); iid=choose(long)
            app.long_name_scrolling_var.set(False); app.set_long_name_scrolling(); settle(app)
            assert not m.item and m.job is None and tree.item(iid,'text') == long.name
            assert pane._tooltip_name(iid) == long.name
            app.right_click_menu_var.set('pfc'); app.save_config()
            config=configparser.ConfigParser(); config.read(Path(raw)/'pfc.ini',encoding='utf-8')
            assert config.get('view','right_click_menu') == 'pfc'
            assert not config.getboolean('view','long_name_scrolling')
            app.long_name_scrolling_var.set(True); app.set_long_name_scrolling(); choose(long)
            m.started -= 4; m.tick()
            if '--screenshot' in sys.argv:
                from PIL import ImageGrab
                app.update_idletasks()
                ImageGrab.grab().save('/tmp/pfc-marquee.png')
            # No path/stat lookup or list re-render is needed on an animation tick.
            original=pane._full_item_name
            pane._full_item_name=lambda _iid: (_ for _ in ()).throw(AssertionError('per-frame file I/O'))
            try: m.tick()
            finally: pane._full_item_name=original
            m.stop(); assert m.job is None and m.pending is None
            if os.name == 'nt':
                import ctypes
                import threading
                pane.on_context, pane.on_native_context = original_context, original_native
                for mode in ('pfc','explorer'):
                    app.right_click_menu_var.set(mode); choose(long)
                    def dismiss():
                        time.sleep(.6)
                        ctypes.windll.user32.keybd_event(0x1B,0,0,0)
                        ctypes.windll.user32.keybd_event(0x1B,0,2,0)
                    threading.Thread(target=dismiss,daemon=True).start()
                    pane._context_keyboard(); settle(app)
                print('PASS: Windows PFC and native Explorer menus open and dismiss')
            app.long_name_scrolling_var.set(False); app.right_click_menu_var.set('pfc')
            assert not errors,errors
            print('PASS: marquee timing, full names, active row only, input forwarding, context choices, zoom/themes, pauses and INI')
        finally:
            app.close_app()
        reopened=module.Commander()
        try:
            assert reopened.right_click_menu_var.get() == 'pfc'
            assert not reopened.long_name_scrolling_var.get()
        finally: reopened.close_app()
        config.read(Path(raw)/'pfc.ini',encoding='utf-8')
        config.set('view','right_click_menu','unknown')
        config.set('view','long_name_scrolling','invalid')
        with (Path(raw)/'pfc.ini').open('w',encoding='utf-8') as stream: config.write(stream)
        fallback=module.Commander()
        try:
            assert fallback.right_click_menu_var.get() == 'explorer'
            assert fallback.long_name_scrolling_var.get()
        finally: fallback.close_app()


if __name__ == '__main__': main()
