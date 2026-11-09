"""Rendered tables/properties, source roundtrip, search and pixel-font regression."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def pump(app):
    started=time.monotonic()
    while time.monotonic()-started<8:
        app.update();time.sleep(.01)
        previews=[w for w in app.winfo_children() if isinstance(w,pfc.PreviewWindow)]
        if time.monotonic()-started>.25 and not any(
                w._md_jobs.pending or w._md_queued or w._md_insert or w._span_job for w in previews):return
    raise AssertionError('Markdown preview did not settle')


def assert_pixel_columns(text, first):
    coordinates = []
    for n in range(first, first+5):
        if text.bbox(f'{n}.0') is None:
            text.yview(f'{n}.0')
            text.update_idletasks()
        line = text.get(f'{n}.0', f'{n}.end')
        pieces = line.split('\t')
        assert pieces[::2] == ['│']*4, line
        offset, x = 0, []
        for i, piece in enumerate(pieces):
            if i % 2 == 0:
                box = text.bbox(f'{n}.0+{offset}c')
                assert box is not None, (line, offset, text.xview(), text.yview())
                x.append(box[0])
            offset += len(piece)+1
        coordinates.append(x)
    assert all(x == coordinates[0] for x in coordinates), coordinates
    print('Shared pixel columns:', coordinates[0], flush=True)


def capture(preview, name):
    if os.name == 'nt':
        from folder_native_test_support import capture_window
        capture_window(preview, Path(__file__).parent/f'evidence-md-table-{name}.bmp')
    elif os.environ.get('PFC_MARKDOWN_EVIDENCE'):
        from PIL import ImageGrab
        x,y = preview.winfo_rootx(), preview.winfo_rooty()
        ImageGrab.grab((x,y,x+preview.winfo_width(),y+preview.winfo_height())).save(
            Path(os.environ['PFC_MARKDOWN_EVIDENCE'])/f'md-table-{name}.png')


with tempfile.TemporaryDirectory() as raw:
    root=Path(raw)
    path=root/'preview.md'
    source='---\ntitle: Table preview\ntags:\n  - work\n  - notes\nnotes: |\n  first line\n  LASTPROPERTY\n---\n# Device reference 😀\n\n'
    source+='Port ID|裝置名稱 / Device|Count\n:---|:---:|---:\n'
    source+='\x60usb-c-1\x60|Display Port|123\n**中文接頭**|混合 é 字😀|9\nusb-a|第一行<br>second line|\n\n'
    source+='## Wide table\n\n'+ '|'.join('Column '+str(i) for i in range(1,9))+'\n'+'|'.join(['---']*8)+'\n'
    source+='|'.join(['**item**', 'wide text '*30]+['path_segment_'+str(i) for i in range(5)]+['LASTCELL'])+'\n'
    path.write_text(source,encoding='utf-8')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    app=pfc.Commander(); errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        preview=pfc.PreviewWindow(app,app.config_data,lambda:None,[path],path)
        preview.geometry('1140x800+10+10')
        preview.lift()
        for size in ('small','large','300'):
            app.font_size_var.set(size);app.apply_font_size(save=False)
            preview.apply_scale(1);pump(app)
            page=preview.active_page
            text=preview.text.get('1.0','end-1c')
            assert 'LASTPROPERTY' in text and 'LASTCELL' in text
            assert preview.text.tag_ranges('markdown_table')
            assert preview.text.tag_cget('markdown_table','wrap')=='none'
            base=pfc.tkfont.nametofont('TkFixedFont')
            assert preview.effect_fonts['h1'].metrics('linespace')>base.metrics('linespace')
            first=int(str(preview.text.tag_ranges('md_table_1')[0]).split('.')[0])
            for wrap in (True, False):
                preview.wrap_var.set(wrap);preview.set_wrap()
                preview.text.xview_moveto(0);preview.text.yview(f'{first-2}.0');pump(app)
                assert_pixel_columns(preview.text, first)
            if size=='large':
                preview.wrap_var.set(True);preview.set_wrap();pump(app)
                capture(preview, 'mixed-150')
            preview.search_var.set('LASTCELL');preview.find_all()
            assert len(preview.matches)==1
            preview.find_next();pump(app)
            a,b=preview.matches[0]
            assert preview.text.bbox(a) is not None
            preview.text.tag_add('sel',a,b);page._copy_preview()
            assert preview.clipboard_get()=='LASTCELL'
            preview.text.tag_remove('sel','1.0','end')
        app.font_size_var.set('large');app.apply_font_size(save=False);preview.apply_scale(1)
        preview.geometry('680x660+10+10')
        preview.wrap_var.set(True);preview.set_wrap();pump(app)
        wide=str(preview.text.tag_ranges('md_table_2')[0])
        preview.text.yview(wide);pump(app)
        preview.text.xview_moveto(0);pump(app)
        assert preview.text.xview()[1] < 1
        preview.text.xview_moveto(1);pump(app)
        assert preview.text.bbox(preview.matches[0][0]) is not None
        preview.text.xview_moveto(0);pump(app)
        preview.find_next();pump(app)
        assert preview.text.xview()[0] > 0 and preview.text.bbox(preview.matches[0][0]) is not None
        capture(preview, 'wide-150')
        for theme in ('light','dark'):
            preview.apply_color_scheme(pfc.COLOR_SCHEMES[theme]);pump(app)
            assert preview.text.tag_cget('markdown_table_stripe','background')==pfc.COLOR_SCHEMES[theme]['surface_alt']
            assert preview.text.tag_cget('markdown_table_header','background')==pfc.COLOR_SCHEMES[theme]['header']
        preview.markdown_var.set(pfc.tr('Markdown Source'));preview.load();pump(app)
        assert preview.text.get('1.0','end-1c').replace('\r\n','\n')==source
        assert not any(t.startswith('md_table_') for t in preview.text.tag_names())
        preview.markdown_var.set(pfc.tr('Rendered'));preview.load();pump(app)
        preview.wrap_var.set(True);preview.set_wrap()
        assert preview.text.tag_cget('markdown_table','wrap')=='none'
        assert path.read_text(encoding='utf-8')==source
        assert not errors, errors
        preview.close()
        print('PASS: shared pixel columns for CJK, ASCII, combining marks and emoji; wide-table scroll, search/copy, Source, themes and scale')
    finally: app.destroy()
