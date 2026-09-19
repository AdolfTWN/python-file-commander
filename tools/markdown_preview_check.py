"""Rendered tables/properties, source roundtrip, search and pixel-font regression."""
import importlib
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

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw)
    path=root/'preview.md'
    source='---\ntitle: Table preview\ntags:\n  - work\n  - notes\nnotes: |\n  first line\n  LASTPROPERTY\n---\n# Heading\n\n'
    source+='Name|Details|Value\n:---|:---:|---:\n**item**|'+('wide text '*30)+'|LASTCELL\n'
    path.write_text(source,encoding='utf-8')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    app=pfc.Commander(); errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        preview=pfc.PreviewWindow(app,app.config_data,lambda:None,[path],path)
        for size in ('small','large','300'):
            app.font_size_var.set(size);app.apply_font_size(save=False)
            preview.apply_scale(1);pump(app)
            text=preview.text.get('1.0','end-1c')
            assert 'LASTPROPERTY' in text and 'LASTCELL' in text
            assert '│' in text and '┌' in text
            assert preview.text.tag_ranges('markdown_table')
            assert preview.text.tag_cget('markdown_table','wrap')=='none'
            base=pfc.tkfont.nametofont('TkFixedFont')
            assert preview.effect_fonts['h1'].metrics('linespace')>base.metrics('linespace')
            preview.search_var.set('LASTCELL');preview.find_all()
            assert len(preview.matches)==1
            preview.find_next();pump(app)
        for theme in ('light','dark'):
            preview.apply_color_scheme(pfc.COLOR_SCHEMES[theme]);pump(app)
            assert preview.text.tag_cget('markdown_table','background')==pfc.COLOR_SCHEMES[theme]['surface_alt']
        preview.markdown_var.set(pfc.tr('Markdown Source'));preview.load();pump(app)
        assert preview.text.get('1.0','end-1c').replace('\r\n','\n')==source
        preview.markdown_var.set(pfc.tr('Rendered'));preview.load();pump(app)
        preview.wrap_var.set(True);preview.set_wrap()
        assert preview.text.tag_cget('markdown_table','wrap')=='none'
        assert path.read_text(encoding='utf-8')==source
        assert not errors, errors
        preview.close()
        print('PASS: full tables/properties, wrapping, search, source roundtrip, themes and pixel-sized headings')
    finally: app.destroy()
