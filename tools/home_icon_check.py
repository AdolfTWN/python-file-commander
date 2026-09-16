"""Check equal navigation buttons and font-sized icons in every UI surface."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def settle(app):
    end = time.monotonic()+.1
    while time.monotonic()<end:
        app.update(); time.sleep(.01)


def main():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        module.Commander._find_ini_path = staticmethod(lambda: root/'pfc.ini')
        module.Commander._sync_auto_start = lambda self, **kw: True
        app = module.Commander(); errors = []
        app.report_callback_exception = lambda *exc: errors.append(str(exc))
        try:
            app.geometry('1200x800'); app.auto_font_size_var.set(False)
            pane = app.left_tabs.current()
            app.edit_home_prefixes(); dialog = app._prefix_preferences
            widths = []
            for scale in module.FONT_SCALES:
                app.font_size_var.set(scale); app.apply_font_size(save=False); settle(app)
                size = module.prefix_icon_size(pane)
                widths.append(size)
                assert pane.home_button.winfo_height() == pane.up_button.winfo_height()
                assert pane.home_button.winfo_width() == pane.up_button.winfo_width()
                for button in (pane.home_button, pane.up_button):
                    name = button.cget('image')[0]
                    assert int(app.tk.call('image', 'height', name)) == size
                assert {img.width() for img in dialog.images.values()} == {size}
                # Validate menu construction without native TrackPopupMenu's modal loop.
                with patch.object(module.tk.Menu, 'tk_popup'):
                    pane.show_home_prefixes()
                assert {img.width() for img in pane._home_menu_images.values()} == {size}
                dialog.rows[0][0].current(1)
                dialog.rows[0][0].event_generate('<<ComboboxSelected>>'); settle(app)
                assert str(dialog.previews[0].cget('image')[0]) == str(dialog.images['cloud'])
            assert all(a<b for a,b in zip(widths,widths[1:])), widths
            for scheme in ('light','light_grey','dark'):
                app.color_scheme_var.set(scheme); app.apply_color_scheme(save=False); settle(app)
                assert pane.home_button.winfo_height() == pane.up_button.winfo_height()
            app.font_size_var.set('175'); app.apply_font_size(save=False); settle(app)
            if '--screenshot' in sys.argv:
                from PIL import ImageGrab
                ImageGrab.grab().save('/tmp/pfc-home-icon-dialog.png')
            dialog.destroy()
            if '--screenshot' in sys.argv:
                gallery = module.tk.Toplevel(app); gallery.title('PFC icon rendering — native sizes')
                gallery.geometry('1000x390+20+20'); gallery.configure(background='#f0f2f4')
                images = []
                for row, size in enumerate((24, 40, 64)):
                    module.tk.Label(gallery, text=f'{size}px', background='#f0f2f4').grid(row=row,column=0,padx=12,pady=8)
                    for col, kind in enumerate(('parent','root',*module.PREFIX_ICONS),1):
                        img = module.prefix_icon(gallery,kind,size); images.append(img)
                        module.tk.Label(gallery,image=img,text=kind,compound='top',background='#f0f2f4').grid(row=row,column=col,padx=12,pady=8)
                settle(app)
                ImageGrab.grab().save('/tmp/pfc-home-icon-gallery.png')
                gallery.destroy()
            assert not errors, errors
            print('PASS: equal Parent/Home button dimensions; toolbar/menu/dialog icon parity at 100–300%; live dialog zoom and icon selection; three themes')
        finally:
            app.close_app()


if __name__ == '__main__': main()
