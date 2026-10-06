"""Paged source review: bounded Tk content, explicit drafts and safe saves."""
import bisect
import hashlib
import html
import difflib
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter import font as tkfont
from .reviewcore import LineIndex, ReviewAlignment, REVIEW_LIMIT, review_state, restore_review_state
from .reviewjobs import ComparisonJobs
from .textio import TextDocument
from .reviewstorage import safe_review_write
from .tooltip import ToolTip
from .settings import readable_check_style
from .comparecolors import style_comparison_text
from .i18n import tr
from .tabs import add_scaled_checkbutton


class ReviewCompare(ttk.Frame):
    PAGE = 80
    WIDTH = 2048

    def __init__(self, master, left, right, **options):
        super().__init__(master)
        self.paths = [Path(left),Path(right)]; self.view=self
        self.documents=[]; self.texts=[]; self.alignment=None; self.checked=set()
        self.top=0; self.column=[0,0]; self.active_side=0; self.block=None
        self.jobs=ComparisonJobs(); self.serial=None; self.busy=False; self._poll_job=None
        self._saving=False;self._saved=queue.Queue()
        self.history=[]; self.future=[]; self.read_only_sides=set(); self._editors=[]
        self.preview=None; self.palette=None; self.matches=[]; self.find_index=-1
        self.preview_jobs=ComparisonJobs();self._preview_timer=None;self._preview_poll=None
        self.wrap=tk.BooleanVar(value=False); self.sync_x=tk.BooleanVar(value=True)
        self.only_diffs=tk.BooleanVar(value=False); self.case=tk.BooleanVar(value=False)
        self.search_var=tk.StringVar(); self.find_status=tk.StringVar()
        bar=ttk.Frame(self);bar.pack(fill='x',padx=4,pady=3)
        actions=ttk.Menubutton(bar,text=tr('Actions'));actions.pack(side='left')
        menu=tk.Menu(actions,tearoff=False);actions.configure(menu=menu)
        for label,cmd in [('Edit Left',lambda:self.edit(0)),('Edit Right',lambda:self.edit(1)),
                          ('Save Left',lambda:self.save_side(0)),('Save Right',lambda:self.save_side(1)),
                          ('Save As',self.save_as),('Undo',self.undo),('Redo',self.redo),
                          ('Save review',self.save_review),('Open review',self.open_review),
                          ('Export report',self.export_report),('Recompare drafts',self.recompare),
                          ('Reload from disk',self.reload_sources)]:
            menu.add_command(label=tr(label),command=cmd)
        for label,cmd in [('←',lambda:self.take(1)),('→',lambda:self.take(0)),
                          ('✓',self.mark_reviewed),('F7 ◀',self.previous),('F8 ▶',self.next)]:
            b=ttk.Button(bar,text=label,width=0,command=cmd);b.pack(side='left',padx=2)
            ToolTip(b,{'←':tr('Copy current difference to LEFT draft'), '→':tr('Copy current difference to RIGHT draft'),
                       '✓':tr('Toggle reviewed — does not accept or save changes')}.get(label,label))
        view=ttk.Menubutton(bar,text=tr('View'));view.pack(side='left',padx=3)
        vm=tk.Menu(view,tearoff=False);view.configure(menu=vm)
        for label,var,cmd in [('Wrap',self.wrap,self.render),('Sync horizontal scrolling',self.sync_x,self.render),
                             ('Differences only',self.only_diffs,self.filter_changed)]:
            add_scaled_checkbutton(vm, tr(label), var, command=cmd)
        vm.add_command(label=tr('Markdown reading preview'),command=self.toggle_preview)
        vm.add_command(label=tr('Go to line'),command=self.goto_line)
        ttk.Button(bar,text=tr('Cancel'),width=0,command=self.cancel).pack(side='right')
        find=ttk.Frame(self);find.pack(fill='x',padx=4,pady=2)
        ttk.Label(find,text=tr('Find:')).pack(side='left')
        self.search=ttk.Entry(find,textvariable=self.search_var,width=8);self.search.pack(side='left',fill='x',expand=True)
        for label,cmd in [('◀',lambda:self.find(-1)),('▶',lambda:self.find(1))]:
            button=ttk.Button(find,text=label,width=0,command=cmd);button.pack(side='left',padx=2)
            ToolTip(button,tr('Find Prev' if label=='◀' else 'Find Next')+(' · Shift+F3' if label=='◀' else ' · F3'))
        self.case_button=ttk.Checkbutton(find,text='Aa',variable=self.case,
                                       command=lambda:setattr(self,'_find_offset',-1))
        self.case_button.pack(side='left',padx=2);ToolTip(self.case_button,tr('Case sensitive'))
        ttk.Button(find,text=tr('Replace'),width=0,command=self.replace).pack(side='left',padx=2)
        self.search.bind('<Return>',lambda e:self.find(1))
        self.search.bind('<Shift-Return>',lambda e:self.find(-1))
        self.body=tk.PanedWindow(self,orient='horizontal',sashwidth=5,borderwidth=0);self.body.pack(fill='both',expand=True)
        self.frames=[];self.headers=[];self.widgets=[];self.xbars=[]
        for side in (0,1):
            frame=ttk.Frame(self.body);self.body.add(frame,stretch='always');self.frames.append(frame)
            frame.columnconfigure(0,weight=1);frame.rowconfigure(1,weight=1)
            title=str(options.get(('left_title','right_title')[side]) or self.paths[side])
            header=ttk.Label(frame,text=('L · ' if side==0 else 'R · ')+title,anchor='w',width=1)
            header.grid(row=0,column=0,sticky='ew');ToolTip(header,title);self.headers.append(header)
            text=tk.Text(frame,wrap='none',height=12,undo=False,font='TkFixedFont',takefocus=True)
            text.grid(row=1,column=0,sticky='nsew');text.configure(state='disabled');self.widgets.append(text)
            xbar=ttk.Scrollbar(frame,orient='horizontal',command=lambda *args,s=side:self.xscroll(s,*args))
            xbar.grid(row=2,column=0,sticky='ew');self.xbars.append(xbar)
            text.bind('<ButtonRelease-1>',lambda e,s=side:self.select_row(s,e))
            text.bind('<FocusIn>',lambda e,s=side:setattr(self,'active_side',s))
            text.bind('<Double-Button-1>',lambda e,s=side:self.edit(s))
            text.bind('<MouseWheel>',lambda e:self.scroll('scroll',-3 if e.delta>0 else 3,'units'))
            text.bind('<Button-4>',lambda e:self.scroll('scroll',-3,'units'))
            text.bind('<Button-5>',lambda e:self.scroll('scroll',3,'units'))
            text.bind('<Next>',lambda e:self.scroll('scroll',1,'pages'))
            text.bind('<Prior>',lambda e:self.scroll('scroll',-1,'pages'))
            text.bind('<Control-s>',lambda e,s=side:self.save_side(s))
        self.scrollbar=ttk.Scrollbar(self,command=self.scroll);self.scrollbar.pack(side='right',fill='y',before=self.body)
        self.status=ttk.Label(self,text=tr('Loading comparison…'),anchor='w',width=1);self.status.pack(fill='x',padx=4)
        self.bind('<Configure>',self.resize,add='+')
        self.bind('<Destroy>',self._destroyed,add='+')
        self._orientation='horizontal'
        self.apply_color_scheme({'content':'#ffffff','text':'#202020'})
        self.apply_scale(1)
        self.start({'mode':'load','paths':[str(p) for p in self.paths]})

    def resize(self,event):
        if event.widget is not self: return
        orientation='vertical' if event.width<900 else 'horizontal'
        if orientation!=self._orientation:
            self._orientation=orientation;self.body.configure(orient=orientation)
        if self.block is not None and self.current_alignment():self.jump_block(self.block)

    def visible_columns(self,side):
        text=self.widgets[side];font=tkfont.Font(font=text.cget('font'))
        return max(8,int((text.winfo_width()-18)/max(1,font.measure('M')))-9)

    def start(self,request):
        self.busy=True; self.status.configure(text=tr('Comparing… drafts retained; Cancel is available'))
        self.serial=self.jobs.submit(request)
        if self._poll_job is None:self._poll_job=self.after(40,self.poll)

    def poll(self):
        self._poll_job=None
        if self._saving:
            try:error=self._saved.get_nowait()
            except queue.Empty:self._poll_job=self.after(40,self.poll);return
            self._saving=False;self.busy=False;self.render()
            if error:messagebox.showerror(tr('Save failed'),error,parent=self)
            return
        try:
            serial,result=self.jobs.results.get_nowait()
        except queue.Empty:
            if self.busy:self._poll_job=self.after(40,self.poll)
            return
        if serial!=self.serial:
            if self.busy:self._poll_job=self.after(40,self.poll)
            return
        self.busy=False
        if 'error' in result:self.status.configure(text=result['error']);return
        if 'documents' in result:
            self.documents=[TextDocument(p,**dict(d,bom=bytes.fromhex(d['bom']),limit=REVIEW_LIMIT))
                            for p,d in zip(self.paths,result['documents'])]
            self.texts=[d.text for d in self.documents]
            self.history.clear();self.future.clear();self.checked.clear();self.top=0;self.column=[0,0]
        self.alignment=ReviewAlignment(*self.texts,result['opcodes'])
        self.block=None;self.rebuild_visible();self.render()

    def cancel(self):
        if self._saving:self.status.configure(text=tr('Finishing atomic save; please wait'));return
        self.jobs.cancel();self.busy=False;self.status.configure(text=tr('Cancelled — drafts retained; use Actions to save'))

    def recompare(self):
        if self._editors or self._saving:return
        self.start({'mode':'diff','texts':self.texts} if self.documents else
                   {'mode':'load','paths':[str(p) for p in self.paths]})

    def reload_sources(self):
        if self.busy or self._editors:return
        if any(t!=d.text for t,d in zip(self.texts,self.documents)) and not messagebox.askyesno(
                tr('Reload from disk'),tr('Discard unsaved comparison drafts?'),default='no',parent=self):return
        # Keep current drafts until both files have loaded successfully.
        self.start({'mode':'load','paths':[str(p) for p in self.paths]})

    def current_alignment(self):
        return bool(self.alignment) and not self.busy and all(
            lines.text==text for lines,text in zip(self.alignment.lines,self.texts))

    def rebuild_visible(self):
        # Compact ranges, not one object per source/aligned row.
        ops=self.alignment.opcodes;self.ranges=[];self.range_ends=[];total=0
        for n,op in enumerate(ops):
            if self.only_diffs.get() and op[0]=='equal':continue
            count=self.alignment.starts[n+1]-self.alignment.starts[n]
            self.ranges.append((total,self.alignment.starts[n]));total+=count;self.range_ends.append(total)
        self.total=total;self.top=min(self.top,max(0,total-1))

    def actual_row(self,row):
        n=bisect.bisect_right(self.range_ends,row)
        start,actual=self.ranges[n];return actual+row-start

    def filter_changed(self):
        if not self.current_alignment():return
        self.top=0;self.rebuild_visible();self.render()

    def render(self):
        if not self.current_alignment():return
        end=min(self.total,self.top+self.PAGE); rendered=[[],[]];self.row_blocks=[];maxwidth=[1,1];reviewed={}
        for row in range(self.top,end):
            block,a,b=self.alignment.row(self.actual_row(row));self.row_blocks.append(block)
            if block not in reviewed:reviewed[block]=bool(self.checked) and self.alignment.block_key(block) in self.checked
            for side,index in enumerate((a,b)):
                line=self.alignment.lines[side][index] if index is not None else ''
                maxwidth[side]=max(maxwidth[side],len(line))
                segment=line[self.column[side]:self.column[side]+self.WIDTH]
                mark='✓' if reviewed[block] else ' '
                rendered[side].append(f'{mark}{index+1:>7} {segment}' if index is not None else '         ')
        for side,text in enumerate(self.widgets):
            text.configure(state='normal',wrap='word' if self.wrap.get() else 'none')
            text.delete('1.0','end');text.insert('1.0','\n'.join(rendered[side]))
            for i,block in enumerate(self.row_blocks,1):
                if self.alignment.opcodes[block][0]!='equal':text.tag_add('diff',f'{i}.0',f'{i}.end')
                if not rendered[side][i-1].strip():text.tag_add('gap',f'{i}.0',f'{i}.end')
                if block==self.block:text.tag_add('current',f'{i}.0',f'{i}.end')
            text.configure(state='disabled');text.yview_moveto(0);text.xview_moveto(0)
            self.xbars[side].set(min(1,self.column[side]/maxwidth[side]),min(1,(self.column[side]+self.visible_columns(side))/maxwidth[side]))
            dirty=self.documents and self.texts[side]!=self.documents[side].text
            state=tr('Read-only') if side in self.read_only_sides or (self.documents and self.documents[side].reason) else (tr('Draft') if dirty else tr('Saved'))
            self.headers[side].configure(text=f'{"L" if side==0 else "R"} · {self.paths[side].name} · {state}')
        budget=100000
        for row,block in enumerate(self.row_blocks,1):
            if self.alignment.opcodes[block][0]=='equal':continue
            _,a,b=self.alignment.row(self.actual_row(self.top+row-1))
            if a is None or b is None:
                self.widgets[0 if a is not None else 1].tag_add('orphan',f'{row}.0',f'{row}.end')
                continue
            left,right=self.alignment.lines[0][a],self.alignment.lines[1][b]
            if max(len(left),len(right))>2000 or len(left)+len(right)>budget:continue
            budget-=len(left)+len(right)
            for tag,a0,a1,b0,b1 in difflib.SequenceMatcher(None,left,right,autojunk=True).get_opcodes():
                if tag=='equal':continue
                for side,lo,hi in ((0,a0,a1),(1,b0,b1)):
                    lo=max(0,lo-self.column[side]);hi=min(self.WIDTH,hi-self.column[side])
                    if hi>lo:self.widgets[side].tag_add('inline_diff',f'{row}.{lo+9}',f'{row}.{hi+9}')
        self.maxwidth=maxwidth
        self.scrollbar.set(self.top/max(1,self.total),end/max(1,self.total))
        self.status.configure(text=f'{len(self.alignment.differences)} '+tr('difference blocks')+
            f' · {len(self.checked)} '+tr('reviewed')+f' · {self.top+1}–{end}/{self.total} · '+
            tr('Column')+f' {self.column[self.active_side]+1}–{self.column[self.active_side]+self.WIDTH} · '+tr('Wide lines: use horizontal bar'))
        self.update_preview()

    def scroll(self,*args):
        if not self.current_alignment():return 'break'
        self.top=(int(float(args[1])*self.total) if args[0]=='moveto' else
                  self.top+int(args[1])*(self.PAGE if args[2]=='pages' else 1))
        self.top=max(0,min(max(0,self.total-1),self.top));self.render();return 'break'

    def xscroll(self,side,*args):
        self.active_side=side
        value=int(float(args[1])*self.maxwidth[side]) if args[0]=='moveto' else self.column[side]+int(args[1])*(self.visible_columns(side) if args[2]=='pages' else 4)
        value=max(0,min(max(0,self.maxwidth[side]-1),value))
        for s in ((0,1) if self.sync_x.get() else (side,)):self.column[s]=value
        self.render()

    def select_row(self,side,event):
        self.active_side=side
        if self.busy or not self.alignment:return
        row=int(self.widgets[side].index(f'@{event.x},{event.y}').split('.')[0])-1
        if row<len(self.row_blocks):self.block=self.row_blocks[row];self.render()

    def jump_block(self,block):
        self.block=block;actual=self.alignment.starts[block]
        for n,(start,source) in enumerate(self.ranges):
            if source<=actual<source+self.range_ends[n]-start:
                self.top=start+actual-source;break
        # Reveal the first changed character even in a million-character line.
        _,a,b,c,d=self.alignment.opcodes[block]
        left=self.alignment.lines[0][a] if a<b else '';right=self.alignment.lines[1][c] if c<d else ''
        prefix=0
        for x,y in zip(left,right):
            if x!=y:break
            prefix+=1
        context=min(20,min(self.visible_columns(0),self.visible_columns(1))//3)
        self.column=[max(0,prefix-context)]*2;self.render()

    def next(self,direction=1):
        if not self.current_alignment() or not self.alignment.differences:return
        items=self.alignment.differences
        index=items.index(self.block) if self.block in items else (-1 if direction>0 else 0)
        self.jump_block(items[(index+direction)%len(items)])

    def previous(self):self.next(-1)

    def mark_reviewed(self):
        if not self.current_alignment() or self.block is None or self.block not in self.alignment.differences:return
        key=self.alignment.block_key(self.block)
        if key in self.checked:self.checked.remove(key)
        else:self.checked.add(key)
        self.render()

    def writable(self,side):
        return bool(self.documents) and side not in self.read_only_sides and not self.documents[side].reason

    def change(self,side,text):
        if self.busy or not self.writable(side):return False
        doc=self.documents[side]
        try:encoded=doc.bom+text.replace('\n',doc.ending).encode(doc.encoding)
        except UnicodeError as exc:
            messagebox.showerror(tr('Compare'),str(exc),parent=self);return False
        if len(encoded)>REVIEW_LIMIT:
            messagebox.showerror(tr('Compare'),tr('Draft exceeds 20 MiB; no change applied'),parent=self);return False
        if text==self.texts[side]:return True
        self.history.append((side,self.texts[side]));self.future.clear()
        while sum(len(t) for _,t in self.history)>100*1024*1024 and len(self.history)>1:self.history.pop(0)
        self.texts[side]=text;self.checked.clear()
        self._find_offset=-1
        self.start({'mode':'diff','texts':self.texts})
        return True

    def take(self,source):
        if self._editors or not self.current_alignment() or self.block is None or not self.writable(1-source):return
        self.change(1-source,self.alignment.take(self.block,source))

    def undo(self):
        if self.busy or self._editors or not self.history:return
        side,text=self.history.pop();self.future.append((side,self.texts[side]));self.texts[side]=text
        self.checked.clear();self.start({'mode':'diff','texts':self.texts})

    def redo(self):
        if self.busy or self._editors or not self.future:return
        side,text=self.future.pop();self.history.append((side,self.texts[side]));self.texts[side]=text
        self.checked.clear();self.start({'mode':'diff','texts':self.texts})

    def edit(self,side):
        if self._editors:self._editors[0].lift();self._editors[0].focus_set();return
        if not self.current_alignment() or not self.writable(side):return
        index=0
        if self.total:
            _,a,b=self.alignment.row(self.actual_row(self.top));index=(a,b)[side] or 0
        start=self.alignment.lines[side].starts[index]+self.column[side]
        ReviewDraftEditor(self,side,min(start,len(self.texts[side])))

    def save_side(self,side):
        if self.busy or self._editors or not self.writable(side) or not self.texts:return 'break'
        if self.texts[side]==self.documents[side].text:return 'break'
        if not messagebox.askyesno(tr('Save'),tr('Write this draft to the original file?')+'\n'+str(self.paths[side]),parent=self):return 'break'
        self.busy=True;self._saving=True;draft=self.texts[side]
        self.status.configure(text=tr('Saving verified draft…'))
        def save():
            try:self.documents[side].save(draft);error=None
            except Exception as exc:error=str(exc)
            self._saved.put(error)
        threading.Thread(target=save,daemon=True).start()
        if self._poll_job is None:self._poll_job=self.after(40,self.poll)
        return 'break'

    def save_as(self):
        if self.busy or self._editors or not self.documents:return
        side=self.active_side;path=filedialog.asksaveasfilename(parent=self,initialfile=self.paths[side].name)
        if not path:return
        target=Path(path)
        if target.resolve() in [p.resolve() for p in self.paths]:
            messagebox.showerror(tr('Save As'),tr('Use Save Left/Right to overwrite a compared source'),parent=self);return
        doc=self.documents[side]
        if doc.reason:messagebox.showerror(tr('Save As'),doc.reason,parent=self);return
        try:
            data=doc.bom+self.texts[side].replace('\n',doc.ending).encode(doc.encoding)
            if len(data)>REVIEW_LIMIT:raise OSError('Encoded draft exceeds 20 MiB')
            safe_review_write(target,data,self.paths)
        except OSError as exc:messagebox.showerror(tr('Save failed'),str(exc),parent=self)

    def find(self,direction):
        if not self.current_alignment() or not self.search_var.get():return None
        side=self.active_side;needle=self.search_var.get();text=self.texts[side]
        import re
        # Regex IGNORECASE preserves source offsets (casefold can change length).
        pattern=re.compile(re.escape(needle),0 if self.case.get() else re.IGNORECASE)
        signature=(side,needle,self.case.get(),text)
        current=getattr(self,'_find_offset',-1) if getattr(self,'_find_signature',None)==signature else -1
        self._find_signature=signature
        found=None
        if direction>0:found=pattern.search(text,current+1) or pattern.search(text)
        else:
            for match in pattern.finditer(text,0,max(0,current)) :found=match
            if found is None:
                for match in pattern.finditer(text):found=match
        if not found:self._find_offset=-1;self.status.configure(text=tr('No matches'));return None
        self._find_offset=found.start();lines=self.alignment.lines[side]
        line=bisect.bisect_right(lines.starts,found.start())-1
        self.jump_line(side,line);self.column[side]=max(0,found.start()-lines.starts[line]-20)
        self.render();self.status.configure(text=tr('Match at line')+f' {line+1}, '+tr('column')+f' {found.start()-lines.starts[line]+1}')
        return found.span()

    def find_next(self):return self.find(1)
    def find_previous(self):return self.find(-1)

    def replace(self):
        if self._editors or not self.current_alignment() or not self.writable(self.active_side) or not self.search_var.get():return
        match=self.find(1)
        if match is None:return
        replacement=simpledialog.askstring(tr('Replace'),tr('Replace current match with:'),parent=self)
        if replacement is None:return
        side=self.active_side;lo,hi=match
        self.change(side,self.texts[side][:lo]+replacement+self.texts[side][hi:])

    def jump_line(self,side,line):
        self.only_diffs.set(False);self.rebuild_visible()
        for n,op in enumerate(self.alignment.opcodes):
            start,end=(op[1],op[2]) if side==0 else (op[3],op[4])
            if start<=line<end:self.top=self.alignment.starts[n]+line-start;self.block=n;break

    def goto_line(self):
        if not self.alignment:return
        number=simpledialog.askinteger(tr('Go to line'),tr('Source line number'),parent=self,minvalue=1,maxvalue=len(self.alignment.lines[self.active_side]))
        if number:self.jump_line(self.active_side,number-1);self.column=[0,0];self.render()

    def save_review(self):
        if self.busy or not self.texts:return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.pfc-review.json')
        if path:
            try:
                data=json.dumps(review_state(self.texts,self.checked)).encode()
                if len(data)>8*1024*1024:raise OSError('Review file exceeds 8 MiB safety limit')
                safe_review_write(Path(path),data,self.paths)
            except OSError as exc:messagebox.showerror(tr('Save failed'),str(exc),parent=self)

    def open_review(self):
        if self.busy or not self.texts:return
        path=filedialog.askopenfilename(parent=self,filetypes=[('PFC review','*.pfc-review.json')])
        if path:
            try:
                if Path(path).stat().st_size>8*1024*1024:raise ValueError('Review file exceeds safety limit')
                self.checked=restore_review_state(json.loads(Path(path).read_text()),self.texts);self.render()
            except (OSError,ValueError) as exc:messagebox.showerror(tr('Open review'),str(exc),parent=self)

    def export_report(self):
        if not self.current_alignment():return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.html',filetypes=[('HTML','*.html'),('Text','*.txt')])
        if not path:return
        content=messagebox.askyesno(tr('Export report'),tr('Include source text in this report? Choose No for summary only.'),default='no',parent=self)
        parts=[f'{self.paths[0].name} ↔ {self.paths[1].name}',f'{len(self.alignment.differences)} difference blocks']
        for n in self.alignment.differences:
            tag,a,b,c,d=self.alignment.opcodes[n];checked=self.alignment.block_key(n) in self.checked
            parts.append(f'{tag}: L {a+1}–{b}, R {c+1}–{d} · {"reviewed" if checked else "unreviewed"}')
            if content:
                for side,lo,hi in ((0,a,b),(1,c,d)):
                    parts.append(('LEFT\n' if side==0 else 'RIGHT\n')+self.texts[side][slice(*self.alignment.lines[side].span(lo,hi))])
        output='\n\n'.join(parts)
        if Path(path).suffix.lower()=='.html':output='<!doctype html><meta charset="utf-8"><title>PFC review</title><pre>'+html.escape(output)+'</pre>'
        try:
            safe_review_write(Path(path),output.encode(),self.paths)
        except OSError as exc:messagebox.showerror(tr('Export report'),str(exc),parent=self)

    def toggle_preview(self):
        if self.preview is not None:
            self.preview_jobs.cancel()
            for job in (self._preview_timer,self._preview_poll):
                if job is not None:self.after_cancel(job)
            self._preview_timer=self._preview_poll=None
            self.preview.destroy();self.preview=None;return
        if not any(p.suffix.lower()=='.md' for p in self.paths):return
        self.preview=tk.Toplevel(self);self.preview.title(tr('Markdown reading preview'))
        self.preview.geometry('800x600');self.preview.protocol('WM_DELETE_WINDOW',self.toggle_preview)
        self.preview.bind('<KeyPress>',lambda e:'break')
        self.preview.bind('<Escape>',lambda e:self.toggle_preview())
        self.preview_caption=ttk.Label(self.preview,text=tr('Current source segment · follows active side · read-only'),width=1)
        self.preview_caption.pack(fill='x')
        body=ttk.Frame(self.preview);body.pack(fill='both',expand=True)
        body.rowconfigure(0,weight=1);body.columnconfigure(0,weight=1)
        self.preview_text=tk.Text(body,wrap='none',font='TkFixedFont');self.preview_text.grid(row=0,column=0,sticky='nsew')
        x=ttk.Scrollbar(body,orient='horizontal',command=self.preview_text.xview);x.grid(row=1,column=0,sticky='ew');self.preview_text.configure(xscrollcommand=x.set)
        y=ttk.Scrollbar(body,command=self.preview_text.yview);y.grid(row=0,column=1,sticky='ns');self.preview_text.configure(yscrollcommand=y.set)
        self._preview_fonts=[]
        for name,scale,weight in (('h1',1.5,'bold'),('h2',1.3,'bold'),('h3',1.15,'bold'),('bold',1,'bold'),('italic',1,'normal')):
            f=tkfont.Font(font='TkFixedFont');size=f.cget('size')
            f.configure(size=(-1 if size<0 else 1)*max(8,round(abs(size)*scale)),weight=weight,slant='italic' if name=='italic' else 'roman')
            self._preview_fonts.append(f);self.preview_text.tag_configure('markdown_'+name,font=f)
        self.preview_text.tag_configure('markdown_link',foreground='#2380bd',underline=True)
        self.preview_text.tag_configure('markdown_code',background='#e6e9ed',foreground='#20303a')
        self.update_preview()

    def update_preview(self):
        if self.preview is None or not self.alignment or not self.total:return
        if self._preview_timer is not None:self.after_cancel(self._preview_timer)
        self._preview_timer=self.after(150,self.prepare_preview)

    def prepare_preview(self):
        self._preview_timer=None
        if self.preview is None or not self.current_alignment() or not self.total:return
        side=self.active_side;_,a,b=self.alignment.row(self.actual_row(self.top));line=(a,b)[side] or 0
        index=self.alignment.lines[side];first=max(0,line-20);last=min(len(index),line+self.PAGE)
        lo,hi=index.span(first,last)
        if len(index[line])>64000:
            lo=index.starts[line]+self.column[side];first=line
        self._preview_fragment=self.texts[side][lo:min(hi,lo+64000)]
        self.preview_caption.configure(text=f'{"L" if side==0 else "R"} · '+tr('Read-only excerpt')+f' · {first+1}–{last} · '+tr('Source comparison remains authoritative'))
        self._preview_serial=self.preview_jobs.submit({'mode':'preview','text':self._preview_fragment})
        if self._preview_poll is None:self._preview_poll=self.after(40,self.poll_preview)

    def poll_preview(self):
        self._preview_poll=None
        if self.preview is None:return
        try:serial,result=self.preview_jobs.results.get_nowait()
        except queue.Empty:self._preview_poll=self.after(40,self.poll_preview);return
        if serial!=self._preview_serial:self._preview_poll=self.after(40,self.poll_preview);return
        rendered=result.get('content',self._preview_fragment)
        self.preview_text.configure(state='normal');self.preview_text.delete('1.0','end');self.preview_text.insert('1.0',rendered)
        for lo,hi,tag in result.get('spans',[]):self.preview_text.tag_add(tag,f'1.0+{lo}c',f'1.0+{hi}c')
        self.preview_text.configure(state='disabled')
        if 'error' in result:self.preview_caption.configure(text=tr('Rendering unavailable; showing source excerpt'))

    def set_read_only(self,left=False,right=False):
        self.read_only_sides={s for s,v in enumerate((left,right)) if v};self.render()

    def focus_search(self):self.search.focus_set();return 'break'
    def apply_scale(self,scale):
        dark=sum(int(self.palette['content'][i:i+2],16) for i in (1,3,5))<330
        self.case_button.configure(style=readable_check_style(self,tkfont.nametofont('TkDefaultFont'),dark,'Review'))
    def apply_language(self,old):pass

    def apply_color_scheme(self,palette):
        self.palette=palette
        for text in self.widgets:
            style_comparison_text(text,palette)

    def confirm_close(self):
        if self._saving:self.status.configure(text=tr('Finishing atomic save; please wait'));return False
        for editor in list(self._editors):
            if not editor.close():return False
        dirty=any(t!=d.text for t,d in zip(self.texts,self.documents))
        return not dirty or messagebox.askyesno(tr('Unsaved changes'),tr('Discard unsaved comparison drafts?'),parent=self)

    def _destroyed(self,event):
        if event.widget is not self:return
        self.jobs.cancel()
        self.preview_jobs.cancel()
        for job in (self._preview_timer,self._preview_poll):
            if job is not None:self.after_cancel(job)
        if self._poll_job is not None:self.after_cancel(self._poll_job)
        if self.preview is not None:self.preview.destroy()
        # Release Tk resources on the UI thread, not later when a worker's
        # allocations happen to trigger cyclic garbage collection.
        self.wrap=self.sync_x=self.only_diffs=self.case=self.search_var=self.find_status=None
        self._preview_fonts=[]


class ReviewDraftEditor(tk.Toplevel):
    """Edit bounded source segments, never alignment padding or display prefixes."""
    CHUNK=32000
    def __init__(self,owner,side,start):
        super().__init__(owner);self.owner=owner;self.side=side;self.draft=owner.texts[side];self.start=start
        owner._editors.append(self);self.title(tr('Edit draft')+' · '+owner.paths[side].name);self.geometry('1000x650')
        bar=ttk.Frame(self);bar.pack(fill='x')
        for label,cmd in [('◀',lambda:self.page(-1)),('▶',lambda:self.page(1)),('Undo',lambda:self.text.edit_undo()),
                          ('Redo',lambda:self.text.edit_redo()),('Apply to draft',self.apply)]:
            ttk.Button(bar,text=tr(label),width=0,command=cmd).pack(side='left',padx=2)
        self.position=ttk.Label(bar,width=1);self.position.pack(side='left',fill='x',expand=True)
        self.text=tk.Text(self,wrap='word',undo=True,font='TkFixedFont');self.text.pack(fill='both',expand=True)
        scroll=ttk.Scrollbar(self,command=self.text.yview);scroll.pack(side='right',fill='y');self.text.configure(yscrollcommand=scroll.set)
        self.protocol('WM_DELETE_WINDOW',self.close);self.load()
        self.bind('<KeyPress>',lambda e:'break')
        self.bind('<Escape>',lambda e:self.close())

    def load(self):
        self.end=min(len(self.draft),self.start+self.CHUNK);self.original=self.draft[self.start:self.end]
        self.text.delete('1.0','end');self.text.insert('1.0',self.original);self.text.edit_reset()
        self.position.configure(text=f'{self.start+1}–{self.end} / {len(self.draft)} '+tr('characters'))

    def capture(self):
        value=self.text.get('1.0','end-1c');self.draft=self.draft[:self.start]+value+self.draft[self.end:];self.end=self.start+len(value)

    def page(self,direction):
        self.capture();self.start=max(0,self.start-self.CHUNK) if direction<0 else min(len(self.draft),self.end);self.load()

    def apply(self):
        self.capture()
        if self.owner.change(self.side,self.draft):self.owner._editors.remove(self);self.destroy()

    def close(self):
        self.capture()
        if self.draft!=self.owner.texts[self.side] and not messagebox.askyesno(tr('Unsaved changes'),tr('Discard these editor changes?'),parent=self):return False
        self.owner._editors.remove(self);self.destroy();return True
