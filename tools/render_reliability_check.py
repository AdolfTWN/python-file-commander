"""Exploratory render regressions: visible matches, boundaries and worker recovery."""
import configparser
import gc
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
import tkinter.font as tkfont
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
                or page.render_view._insert_job or page._format_find_job or getattr(page.render_view.tree,'_layout_job',None)):return
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
    def test_grid_wrap_complete_and_column_widths_stable(self):
        value='first line\n'+('完整內容 device details '*200)+'END-MARKER'
        self.show(core.table_preview('ID,Details\n001,"'+value+'"\n','.csv'))
        tree=self.view.tree;tree.column('c0',width=135,stretch=False)
        self.view.rescale();self.root.update()
        self.assertEqual(tree.column('c0','width'),135,'Font scaling reset manual table width')
        self.view.set_wrap(True);self.root.update()
        self.assertTrue(hasattr(tree,'_layouts'),'Wrap does not render multiline table cells')
        until=time.monotonic()+5
        while tree._layout_job:self.root.update();time.sleep(.005);self.assertLess(time.monotonic(),until)
        self.assertIn('first line',tree._layouts['r0'][1][1])
        self.assertTrue(''.join(tree._layouts['r0'][1][1]).endswith('END-MARKER'))
        self.view.find('END-MARKER');self.root.update()
        while tree._layout_job:self.root.update();time.sleep(.005);self.assertLess(time.monotonic(),until)
        self.assertGreater(tree.yview()[0],0)
        self.view.copy();self.assertEqual(self.root.clipboard_get(),value)
        self.view.choice.set(app.tr('First row: data'));self.view._choose();self.root.update()
        self.assertEqual(self.view.tree.column('c0','width'),135)
        selected=self.view.tree.selection();self.assertEqual(selected,('r1',))
        same=self.view.tree;self.view._choose();self.assertIs(self.view.tree,same)
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
    def test_image_search_does_not_undo_manual_pan_on_redraw(self):
        image=tk.PhotoImage(master=self.root,width=1000,height=2000)
        self.show(dict(kind='image',png=image.tk.call(str(image),'data','-format','png'),content='needle',
                       positions=[dict(start=0,end=6,x=800,y=1600,w=80,h=20)]))
        self.view.find('needle');self.root.update()
        self.assertGreater(self.view.canvas.yview()[0],.5)
        self.view.canvas.yview_moveto(0);self.view.canvas.xview_moveto(0)
        self.view._draw_image();self.root.update()
        self.assertEqual(self.view.canvas.yview()[0],0)
        self.assertEqual(self.view.canvas.xview()[0],0)
        self.assertTrue(self.view.canvas.find_withtag('search_hit'))
    def test_empty_grid_and_nowrap_cells_are_safe(self):
        self.show(core.table_preview('', '.csv'))
        self.assertIn('No matches',self.view.find('needle'))
        self.show(core.table_preview('A,B\n'+('x'*10000)+',next\n','.csv'))
        tree=self.view.tree;font=tk.font.nametofont('TkDefaultFont')
        self.assertLessEqual(font.measure(tree._layouts['r0'][1][0][0]),tree.column('c0','width')-12)
    def test_full_value_large_line_is_bounded_but_copy_is_lossless(self):
        value='x'*150000+'END-MARKER'
        self.show(core.table_preview('Data\n'+value+'\n','.csv'))
        self.view.tree.selection_set('r0');self.view._full_value();self.root.update()
        popup=next(w for w in self.view.winfo_children() if isinstance(w,tk.Toplevel))
        box=next(w for w in popup.winfo_children() if isinstance(w,tk.Text))
        self.assertLessEqual(len(box.get('1.0','end-1c')),16384)
        footer=next(w for w in popup.winfo_children() if isinstance(w,app.ttk.Frame))
        copy=next(w for w in footer.winfo_children() if isinstance(w,app.ttk.Button) and w.cget('text')==app.tr('Copy value'))
        copy.invoke();self.assertEqual(self.root.clipboard_get(),value)
        self.assertTrue(any(isinstance(w,app.ttk.Scrollbar) and str(w.cget('orient'))=='horizontal' for w in popup.winfo_children()))
        popup.destroy()
    def test_crlf_search_reveals_the_actual_line_in_tree_and_table(self):
        value='a\r\n'*1000+'UNIQUE-HIT\r\n'+'b\r\n'*1000
        for kind in ('tree','grid'):
            with self.subTest(kind=kind):
                self.view.set_wrap(True)
                if kind=='grid':
                    self.show(core.table_preview('Data\n"'+value+'"\n','.csv'))
                    self.view.find('UNIQUE-HIT');column=0
                else:
                    source=json.dumps({'text':value})
                    self.show(core.structured_preview(source,'.json'))
                    self.view.apply_tree_search(core.structured_search(source,'.json','UNIQUE-HIT'),key=('UNIQUE-HIT',False));column=1
                tree=self.view.tree;until=time.monotonic()+10
                while tree._layout_job or self.view._insert_job:
                    self.root.update();time.sleep(.005);self.assertLess(time.monotonic(),until)
                self.root.update();iid=tree.selection()[0]
                entry=next(r for r in tree._entries if r[0]==iid)
                line=next(i for i,text in enumerate(entry[4][column]) if 'UNIQUE-HIT' in text)
                y=entry[2]+4+line*tkfont.nametofont('TkDefaultFont').metrics('linespace')
                self.assertLessEqual(tree._offset,y)
                self.assertLess(y,tree._offset+tree._body.winfo_height(),'Search hit is outside the visible viewport')
                self.assertEqual(self.view._value(),value)


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
    def setUp(self):
        # Isolated roots are test-only. Reclaim the previous destroyed root's
        # cycles on the GUI thread before this case starts worker threads.
        gc.collect()
    def test_csv_tsv_wrap_toggle_reload_and_scaled_controls(self):
        with tempfile.TemporaryDirectory() as raw:
            directory=Path(raw);root=tk.Tk();root.geometry('1100x760');errors=[]
            root.report_callback_exception=lambda *exc:errors.append(str(exc))
            config=configparser.ConfigParser();config.add_section('preview');config.set('preview','geometry','1000x700')
            value='第一行\n'+('Full cell content / '*250)+'END-MARKER'
            csv=directory/'sample.csv';csv.write_text('ID,Description\n001,"'+value+'"\n',encoding='utf-8')
            tsv=directory/'sample.tsv';tsv.write_text('ID\tDescription\n001\t"'+value+'"\n',encoding='utf-8')
            window=app.PreviewWindow(root,config,lambda:None,[csv,tsv],csv)
            fonts={n:tkfont.nametofont(n).cget('size') for n in ('TkDefaultFont','TkFixedFont','TkTextFont','TkHeadingFont')}
            try:
                for path in (csv,tsv):
                    window.show([csv,tsv],path);page=window.active_page;ready(root,page);tree=page.render_view.tree
                    self.assertNotIn('disabled',page.wrap_check.state())
                    page.wrap_check.invoke();ready(root,page);self.assertTrue(page.wrap_var.get())
                    self.assertTrue(''.join(tree._layouts['r0'][1][1]).endswith('END-MARKER'))
                    page.search_var.set('END-MARKER');page.find_next();ready(root,page)
                    self.assertGreater(tree.yview()[0],0)
                    page.wrap_check.invoke();ready(root,page);self.assertIn('END-MARKER',tree.item('r0','values')[1])
                    page.wrap_check.invoke();ready(root,page);self.assertGreater(tree.yview()[0],0)
                    tree.column('c0',width=155);page.load();ready(root,page)
                    self.assertEqual(page.render_view.tree.column('c0','width'),155)
                for n,size in fonts.items():tkfont.nametofont(n).configure(size=round(size*2))
                window.geometry('900x700');window.apply_scale(2);ready(root,page)
                tree=page.render_view.tree;tree.yview_moveto(0);root.update();capture(window,'grid-wrap')
                self.assertEqual(tree.column('c0','width'),155)
                self.assertGreater(page.search.winfo_width(),20)
                self.assertLessEqual(page.case_check.winfo_rootx()+page.case_check.winfo_width(),window.winfo_rootx()+window.winfo_width())
                self.assertFalse(errors,errors)
            finally:
                for n,size in fonts.items():tkfont.nametofont(n).configure(size=size)
                window.close();root.destroy()
    def test_grid_reflow_cancel_stops_and_reload_recovers(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'large.csv';path.write_text('ID,Details\n'+''.join(str(i)+','+('long details '*100)+'\n' for i in range(400)),encoding='utf-8')
            root=tk.Tk();errors=[];pulses=[];running=True;pulse_job=None
            root.report_callback_exception=lambda *exc:errors.append(str(exc))
            def pulse():
                nonlocal pulse_job
                if running:pulses.append(time.monotonic());pulse_job=root.after(20,pulse)
            pulse();config=configparser.ConfigParser();config.add_section('preview')
            window=app.PreviewWindow(root,config,lambda:None,[path],path)
            try:
                page=window.active_page;ready(root,page);tree=page.render_view.tree
                page.wrap_check.invoke();self.assertIsNotNone(tree._layout_job)
                root.after(1,page._cancel_format_ui);root.update();time.sleep(.05);root.update()
                self.assertIsNone(tree._layout_job);self.assertIs(page.render_view.tree,tree)
                self.assertIn('Layout canceled',page.status.cget('text'))
                page.load();ready(root,page)
                self.assertEqual(len(page.render_view.tree.get_children()),400)
                self.assertFalse(errors,errors)
                gap=max((b-a for a,b in zip(pulses,pulses[1:])),default=0)
                self.assertLess(gap,1,('Grid reflow blocked event loop',gap))
                print('Grid cancel/reload maximum UI heartbeat gap:',round(gap,4),flush=True)
            finally:
                running=False
                if pulse_job is not None:root.after_cancel(pulse_job)
                window.close();root.destroy()
    def test_direct_destroy_stops_progress_and_page_callbacks(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'test.json';path.write_text('{"value":"safe"}')
            root=tk.Tk();config=configparser.ConfigParser();config.add_section('preview')
            window=app.PreviewWindow(root,config,lambda:None,[path],path)
            page=window.active_page
            try:
                page.activity_progress.start(30)
                timer_ids=set(root.tk.splitlist(root.tk.call('after','info')))
                page_jobs={getattr(page,n) for n in ('_format_poll','_md_poll_job','_refresh_job')}
                progress_jobs={j for j in timer_ids if 'Autoincrement' in str(root.tk.call('after','info',j))}
                self.assertTrue(progress_jobs)
                window.destroy();root.update()
                remaining=set(root.tk.splitlist(root.tk.call('after','info')))
                self.assertFalse(progress_jobs & remaining)
                self.assertFalse(page_jobs & remaining)
            finally:
                if window.winfo_exists():window.close()
                root.destroy()
    def test_structured_ux_is_shared_by_every_structured_extension(self):
        with tempfile.TemporaryDirectory() as raw:
            directory=Path(raw);root=tk.Tk();root.geometry('1000x700');errors=[]
            root.report_callback_exception=lambda *exc:errors.append(str(exc))
            config=configparser.ConfigParser();config.add_section('preview')
            data={'early':list(range(3100)),'items':[{'name':'NEEDLE '+('long value '*30)},{'name':'NEEDLE second'}]}
            sources={'.json':json.dumps(data),
                     '.jsonl':json.dumps(data)+'\n','.ndjson':json.dumps(data)+'\n',
                     '.yaml':'early: ['+','.join(map(str,range(3100)))+']\nitems:\n  - name: "'+data['items'][0]['name']+'"\n  - name: NEEDLE second\n',
                     '.toml':'early = ['+','.join(map(str,range(3100)))+']\n[[items]]\nname="'+data['items'][0]['name']+'"\n[[items]]\nname="NEEDLE second"\n'}
            sources['.yml']=sources['.yaml']
            paths=[]
            for suffix,source in sources.items():
                path=directory/('data'+suffix);path.write_text(source,encoding='utf-8');paths.append(path)
            window=app.PreviewWindow(root,config,lambda:None,paths,paths[0])
            try:
                for path in paths:
                    with self.subTest(suffix=path.suffix):
                        window.show(paths,path);page=window.active_page;ready(root,page);view=page.render_view;tree=view.tree
                        self.assertTrue(view.model['truncated']);self.assertTrue(page.find_all_matched_button.winfo_ismapped())
                        page.search_var.set('NEEDLE');page.find_next();ready(root,page);first=tree.selection()[0]
                        page.find_next();ready(root,page);self.assertNotEqual(first,tree.selection()[0])
                        self.assertTrue(tree.exists(first));parent=tree.parent(first)
                        while parent:self.assertTrue(tree.item(parent,'open'));parent=tree.parent(parent)
                        page.find_all_matched();ready(root,page);self.assertEqual(len(view._tree_search_rows),2)
                        self.assertIs(tree,view.tree);self.assertEqual(page.markdown_values[page.markdown_var.get()],'rendered')
                        tree.column('#0',width=130);view.rescale();ready(root,page);self.assertEqual(tree.column('#0','width'),130)
                        before={iid:tree.item(iid,'open') for iid in view._row_lookup}
                        view._expand_tree(True);page._cancel_format_ui();ready(root,page)
                        self.assertEqual(before,{iid:tree.item(iid,'open') for iid in view._row_lookup})
                        page.case_var.set(True);page.search_var.set('needle');page.find_next();ready(root,page)
                        self.assertIn('No matches',page.status.cget('text'))
                        self.assertEqual(path.read_text(encoding='utf-8'),sources[path.suffix])
                self.assertFalse(errors,errors)
            finally:window.close();root.destroy()
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
