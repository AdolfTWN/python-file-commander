"""Exploratory render regressions: visible matches, boundaries and worker recovery."""
import configparser
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
portable='pfc' in sys.argv
if portable:sys.argv.remove('pfc')
app=importlib.import_module('pfc' if portable else 'pycommander.app')
ui=app if portable else importlib.import_module('pycommander.renderui')
core=app if portable else importlib.import_module('pycommander.rendercore')


def ready(root,page,timeout=35):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        root.update();time.sleep(.01)
        if not (page._format_jobs.pending or page._format_queued or page._format_request
                or page.render_view._insert_job or page._format_find_job):return
    raise AssertionError('Preview did not settle: '+page.status.cget('text'))


def capture(window,name):
    window.update();window.lift();window.update();time.sleep(.15);window.update()
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/('evidence-reliability-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save('/tmp/pfc-reliability-'+name+'.png')


class WidgetReliability(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('780x480');self.errors=[]
        self.root.report_callback_exception=lambda *exc:self.errors.append(str(exc))
        self.view=ui.FormatRenderView(self.root);self.view.pack(fill='both',expand=True)
    def tearDown(self):
        self.root.destroy()
        self.assertFalse(self.errors)
    def show(self,model):
        self.view.show(model)
        until=time.monotonic()+5
        while self.view._insert_job and time.monotonic()<until:self.root.update();time.sleep(.01)
        self.root.update()
    def test_grid_search_visibly_reveals_late_cell_and_other_columns(self):
        self.show(core.table_preview('Left,Right\n'+('x'*1500)+'NEEDLE,NEEDLE\n','.csv'))
        self.assertIn('of 2',self.view.find('NEEDLE'))
        self.assertIn('NEEDLE',self.view.tree.item('r0','values')[0])
        capture(self.root,'grid-match')
        self.assertIn('Match 2 of 2',self.view.find('NEEDLE'))
        self.assertEqual(self.view._cell,1)
        self.view.copy();self.assertEqual(self.root.clipboard_get(),'NEEDLE')
    def test_grid_header_is_searchable(self):
        self.show(core.table_preview('HeaderNeedle,Other\n1,2\n','.csv'))
        self.assertIn('Match 1 of 1',self.view.find('HeaderNeedle'))
        self.view.copy();self.assertEqual(self.root.clipboard_get(),'HeaderNeedle')
    def test_wide_table_scrolls_to_matching_column(self):
        self.show(core.table_preview(','.join('C'+str(i) for i in range(30))+'\n'+','.join(['x']*29+['NEEDLE']),'.csv'))
        self.view.find('NEEDLE');self.root.update()
        self.assertGreater(self.view.tree.xview()[0],0)
        self.assertEqual(self.view._cell,29)
        self.view.copy();self.assertEqual(self.root.clipboard_get(),'NEEDLE')
    def test_large_header_display_is_bounded_but_losslessly_searchable(self):
        header='x'*150000+'NEEDLE'
        self.show(core.table_preview(header+'\nvalue\n','.csv'))
        self.assertLessEqual(len(self.view.tree.heading('c0','text')),500)
        self.view.find('NEEDLE');self.assertIn('NEEDLE',self.view.tree.heading('c0','text'))
        self.view.copy();self.assertEqual(self.root.clipboard_get(),header)
    def test_unicode_source_and_patch_highlight_exact_text(self):
        for content in ('😀中 NEEDLE\n😀 NEEDLE','🎯\n+中😀 NEEDLE\n'):
            self.show(dict(kind='document',content=content,spans=[],sections=[]))
            self.view.find('NEEDLE')
            self.assertEqual(self.view.text.get(*self.view.text.tag_ranges('format_match')),'NEEDLE')
    def test_no_match_removes_previous_source_highlight(self):
        self.show(dict(kind='document',content='old match',spans=[]))
        self.view.find('old');self.view.find('missing')
        self.assertFalse(self.view.text.tag_ranges('format_match'))
    def test_excessive_matches_are_bounded_and_explicit(self):
        self.show(dict(kind='document',content='a'*200000,spans=[]))
        self.assertIn('5,000',self.view.find('a'))
    def test_image_zoom_retains_search_highlight(self):
        image=tk.PhotoImage(master=self.root,width=100,height=100);image.put('white',to=(0,0,100,100))
        self.show(dict(kind='image',png=image.tk.call(str(image),'data','-format','png'),content='Visible needle',
                       positions=[dict(start=0,end=14,x=5,y=5,w=80,h=15)]))
        self.view.find('needle');self.assertTrue(self.view.canvas.find_withtag('search_hit'))
        self.view.choice.set('200%');self.view._choose();self.root.update()
        self.assertTrue(self.view.canvas.find_withtag('search_hit'))
        displayed=self.view.display_image;self.view._draw_image()
        self.assertIs(self.view.display_image,displayed,'Unchanged resize must reuse raster instead of reallocating it')


class ParserReliability(unittest.TestCase):
    def test_large_but_bounded_csv_cell_is_not_misclassified_as_invalid(self):
        value='x'*150000
        self.assertEqual(core.table_preview('Data\n'+value+'\n','.csv')['rows'],[[value]])
    def test_notebook_output_limits_are_explicit(self):
        data={'nbformat':4,'cells':[{'cell_type':'code','source':'x',
              'outputs':[{'text':'Output '+str(i)} for i in range(31)]}]}
        _,notice=core.notebook_preview_html(json.dumps(data))
        self.assertIn('30',notice)
        _,_,partial=core.notebook_preview_html(json.dumps(data),with_limits=True)
        self.assertTrue(partial)


class LifecycleReliability(unittest.TestCase):
    def test_timed_out_worker_keeps_tree_and_reload_recovers(self):
        with tempfile.TemporaryDirectory() as raw:
            directory=Path(raw);path=directory/'test.json';path.write_text('{"needle":"value"}')
            root=tk.Tk();errors=[];root.report_callback_exception=lambda *exc:errors.append(str(exc))
            config=configparser.ConfigParser();config.add_section('preview')
            window=app.PreviewWindow(root,config,lambda:None,[path],path)
            try:
                page=window.active_page;ready(root,page);tree=page.render_view.tree
                original=page._format_jobs;original.close()
                slow=directory/'slow_worker.py';slow.write_text('import time\ndef format_worker_main(): time.sleep(60)\n')
                page._format_jobs=type(original)(slow,False,'format_worker_main')
                page.search_var.set('needle');page.find_next()
                deadline=time.monotonic()+3
                while not page._format_jobs.pending:
                    root.update();time.sleep(.01);self.assertLess(time.monotonic(),deadline)
                page._format_jobs.started-=31;ready(root,page)
                self.assertIs(page.render_view.tree,tree)
                self.assertEqual(page.markdown_values[page.markdown_var.get()],'rendered')
                self.assertIn('timed out',page.status.cget('text'))
                page._format_jobs.close();page._format_jobs=original
                page.load();ready(root,page)
                page.find_next();ready(root,page)
                self.assertIn('Match 1 of 1',page.status.cget('text'))
                self.assertFalse(errors,errors)
            finally:window.close();root.destroy()

    def test_invalid_render_recovers_and_search_scope_is_honest(self):
        with tempfile.TemporaryDirectory() as raw:
            root=tk.Tk();root.geometry('1100x700');errors=[]
            root.report_callback_exception=lambda *exc:errors.append(str(exc))
            directory=Path(raw);config=configparser.ConfigParser();config.add_section('preview')
            fixtures={
                'bad.json':'{"unfinished":', 'good.json':'{"needle":"value"}',
                'bad.yaml':'x: [unfinished', 'good.yaml':'needle: value',
                'bad.toml':'[unfinished', 'good.toml':'needle="value"',
                'bad.csv':'Data\n"unfinished', 'good.csv':'Data\nvalue',
                'bad.svg':'<svg', 'good.svg':'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"><text x="3" y="25">Needle</text></svg>',
                'bad.mmd':'not a diagram', 'good.mmd':'flowchart LR\n A[Needle] --> B[Result]',
                'bad.ipynb':'{"nbformat":3}', 'good.ipynb':json.dumps({'nbformat':4,'cells':[{'cell_type':'markdown','source':'# Needle'}]}),
                'partial.ipynb':json.dumps({'nbformat':4,'cells':[{'cell_type':'code','source':'x','outputs':[{'text':'value'}]*30+[{'text':'NOT_INDEXED'}]}]}),
                'dense.html':'<div style="font-size:1px">'+''.join('<span>x</span>' for _ in range(3100))+'<span>NOT_INDEXED</span></div>',
            }
            paths=[]
            for name,value in fixtures.items():
                path=directory/name;path.write_text(value,encoding='utf-8');paths.append(path)
            window=app.PreviewWindow(root,config,lambda:None,paths,paths[0])
            try:
                for suffix in ('json','yaml','toml','csv','svg','mmd','ipynb'):
                    window.show(paths,directory/('bad.'+suffix));page=window.active_page;ready(root,page)
                    self.assertTrue(page.render_view.model.get('fallback'),suffix)
                    window.show(paths,directory/('good.'+suffix));page=window.active_page;ready(root,page)
                    self.assertFalse(page.render_view.model.get('fallback'),(suffix,page.status.cget('text')))
                window.show(paths,directory/'dense.html');page=window.active_page;ready(root,page)
                self.assertEqual(page.render_view.model.get('kind'),'image')
                self.assertTrue(page.render_view.model.get('truncated'),'Raster text-node cap must mark search scope partial')
                page.search_var.set('NOT_INDEXED');page.find_next()
                self.assertIn('rest of the file was not searched',page.status.cget('text'))
                window.show(paths,directory/'partial.ipynb');page=window.active_page;ready(root,page)
                self.assertTrue(page.render_view.model.get('truncated'))
                page.search_var.set('NOT_INDEXED');page.find_next()
                self.assertIn('rest of the file was not searched',page.status.cget('text'))
                capture(window,'partial-notebook')
                for codec,bom in (('utf-16-le',b'\xff\xfe'),('utf-32-le',b'\xff\xfe\0\0'),('utf-32-be',b'\0\0\xfe\xff')):
                    path=directory/(codec+'.json');path.write_bytes(bom+'{"emoji":"😀 NEEDLE"}'.encode(codec))
                    window.show([path],path);page=window.active_page;ready(root,page)
                    self.assertEqual(page.render_view.model['kind'],'tree')
                    page.search_var.set('NEEDLE');page.find_next();ready(root,page)
                    self.assertIn('Match 1 of 1',page.status.cget('text'))
                page.load();root.update();page._cancel_format_ui();root.update()
                self.assertIsNone(page._format_jobs.pending)
                page.load();ready(root,page)
                page.load();root.update();window.close();root.update()
                self.assertFalse(errors,errors)
            finally:
                if window.winfo_exists():window.close()
                root.destroy()


if __name__=='__main__':unittest.main(verbosity=2)
