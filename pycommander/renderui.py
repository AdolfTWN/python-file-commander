"""One compact read-only view for structured, tabular, textual and image models."""
import base64
from itertools import chain,islice
import re
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from .i18n import tr
from .tooltip import ToolTip
from .rendercore import STRUCTURE_REVEAL_LIMIT
from .wraptree import WrappedTreeview


def preview_cell_text(value):
    """Single-line display only; the original value remains available to copy."""
    return value.replace('\r\n','\n').replace('\r','\n').replace('\n',' ↵ ')


def preview_match_excerpt(value,start,end):
    left=max(0,start-12);right=min(len(value),end+80,left+200)
    return ('… ' if left else '')+preview_cell_text(value[left:right])+(' …' if right<len(value) else '')


class FormatRenderView(ttk.Frame):
    def __init__(self,master):
        super().__init__(master)
        self.model={};self.images=[];self.match_index=-1;self._generation=0;self._insert_job=None
        self._row_lookup={};self._search_extra=[]
        self._structured_widths=None
        self._expand_restore=None
        self._tree_search_key=None;self._tree_search_rows=set();self._tree_revealing=False
        self._grid_search_row=None;self._header_match=None;self._image_match=None;self._image_view_key=None
        self._grid_header=True;self.wrap=False
        self.header=ttk.Frame(self,padding=(6,3));self.header.pack(fill='x')
        self.detail=ttk.Label(self.header,width=1);self.detail.pack(side='left',fill='x',expand=True)
        self.choice=ttk.Combobox(self.header,state='readonly',width=16)
        self.choice.bind('<<ComboboxSelected>>',lambda e:self._choose())
        self.copy_button=ttk.Button(self.header,text=tr('Copy'),width=0,command=self.copy)
        self.copy_button.pack(side='right',padx=(4,0))
        self.tree_actions=ttk.Frame(self.header)
        self.expand_button=ttk.Button(self.tree_actions,width=0,command=lambda:self._expand_tree(True))
        self.collapse_button=ttk.Button(self.tree_actions,width=0,command=lambda:self._expand_tree(False))
        self.expand_button.pack(side='left');self.collapse_button.pack(side='left',padx=(3,0))
        ToolTip(self.expand_button,lambda:tr('Expand loaded nodes only; omitted entries are not loaded'))
        ToolTip(self.collapse_button,lambda:tr('Collapse all'))
        self.body=ttk.Frame(self);self.body.pack(fill='both',expand=True)
        self.tree=None;self.text=None;self.canvas=None;self.scale=1
        self.bind('<Destroy>',self._destroyed,add='+')
        ToolTip(self.copy_button,lambda:tr('Copy')+' (Ctrl+C)')
    def _destroyed(self,event):
        if event.widget is self:
            self._generation+=1
            if self._insert_job is not None:
                try:self.after_cancel(self._insert_job)
                except tk.TclError:pass
    def clear(self):
        self.cancel_tree_reveal()
        self._generation+=1
        if self._insert_job is not None:
            self.after_cancel(self._insert_job);self._insert_job=None
        if isinstance(self.tree,WrappedTreeview):self._structured_widths=tuple(self.tree.column(c,'width') for c in ('#0','value','type'))
        for child in self.body.winfo_children():child.destroy()
        if getattr(self,'menu',None) is not None:self.menu.destroy();self.menu=None
        self.images=[];self.tree=None;self.text=None;self.canvas=None;self.choice.pack_forget();self.tree_actions.pack_forget();self.match_index=-1
        self._row_lookup={};self._search_extra=[]
        self._tree_search_key=None;self._tree_search_rows=set();self._tree_revealing=False
        self._grid_search_row=None;self._header_match=None;self._image_match=None;self._image_view_key=None
        for name in ('original','display_image'):
            if hasattr(self,name):delattr(self,name)
    def show(self,model):
        self.clear();self.model=model;kind=model['kind']
        self.detail.configure(text=tr({'tree':'Structure','grid':'Table','document':'Document','image':'Static visual preview'}[kind]))
        if kind=='tree' and model.get('truncated'):self.detail.configure(text=tr('Structure')+' · '+tr('Partial tree'))
        if kind in {'tree','grid'}:self._show_tree(kind)
        elif kind=='image':self._show_image()
        else:self._show_document()
    def _scrollbars(self,widget):
        self.body.rowconfigure(0,weight=1);self.body.columnconfigure(0,weight=1)
        widget.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(self.body,orient='vertical',command=widget.yview)
        horizontal=ttk.Scrollbar(self.body,orient='horizontal',command=widget.xview)
        widget.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        widget.bind('<Control-c>',lambda e:self.copy())
        widget.bind('<Control-C>',lambda e:self.copy())
    def _show_tree(self,kind):
        if getattr(self,'menu',None) is not None:self.menu.destroy();self.menu=None
        self._grid_search_row=None;self._header_match=None;self.match_index=-1
        if kind=='tree':
            columns=('value','type');self.tree=WrappedTreeview(self.body,columns=columns,show='tree headings',selectmode='browse')
            self.tree.heading('#0',text=tr('Key / index'));self.tree.heading('value',text=tr('Value'));self.tree.heading('type',text=tr('Type'))
            for row in self.model['rows']:
                self._row_lookup[row['id']]=row
                self.tree.insert(row['parent'],'end',iid=row['id'],text=row['label'],values=(row['value'],row['kind']),open=row['path'].count('/')<=1)
            self.tree_actions.pack(side='right',padx=4)
        else:
            columns=tuple('c'+str(i) for i in range(len(self.model['columns'])))
            headers=self.model['columns'] if self._grid_header else ['Column '+str(i+1) for i in range(len(columns))]
            self._grid_headings=headers
            self._grid_rows=self.model['rows'] if self._grid_header else [self.model['columns']]+self.model['rows']
            self.tree=ttk.Treeview(self.body,columns=columns,show='headings',selectmode='browse')
            for index,(key,label) in enumerate(zip(columns,headers)):
                self.tree.heading(key,text=preview_cell_text(label)[:500])
            for index,row in enumerate(self._grid_rows):
                self.tree.insert('','end',iid='r'+str(index),values=tuple(preview_cell_text(v)[:500] for v in row))
            self.choice.configure(values=(tr('First row: header'),tr('First row: data')))
            self.choice.set(tr('First row: header') if self._grid_header else tr('First row: data'))
            self.choice.pack(side='right',padx=4)
        self.rescale();self._scrollbars(self.tree)
        self.tree.bind('<Double-1>',self._full_value)
        self.tree.bind('<ButtonRelease-1>',self._select_cell,add='+')
        self.tree.bind('<Return>',self._full_value)
        self.menu=tk.Menu(self,tearoff=False,font='TkMenuFont')
        self.menu.add_command(label=tr('Copy value'),command=self.copy)
        self.menu.add_command(label=tr('Full value…'),command=self._full_value)
        if kind=='tree':self.menu.add_command(label=tr('Copy path'),command=self._copy_path)
        self.tree.bind('<Button-3>',self._context)
        self.tree.bind('<Shift-F10>',self._context)
        self._cell=0
    def rescale(self):
        if not self.tree:return
        font=tkfont.nametofont('TkDefaultFont');unit=max(8,font.measure('M'))
        if self.model['kind']=='tree':
            size=max(18,font.metrics('linespace'));self._tree_icons=[]
            # Font-independent, scalable outlined stacked boxes: + / −.
            color=ttk.Style(self).lookup('TLabel','foreground') or '#243746'
            # PhotoImage.put rejects Windows symbolic system colors even though
            # widgets accept them. Resolve through Tk before drawing pixels.
            color='#%02x%02x%02x'%tuple(c//257 for c in self.winfo_rgb(color))
            for expanded,button in ((True,self.expand_button),(False,self.collapse_button)):
                icon=tk.PhotoImage(master=self,width=size,height=size)
                def line(x0,y0,x1,y1):
                    icon.put(color,to=(round(size*x0),round(size*y0),max(round(size*x0)+1,round(size*x1)),max(round(size*y0)+1,round(size*y1))))
                t=max(1,round(size*.06))/size
                for x0,y0,x1,y1 in ((.27,.12,.86,.12+t),(.86-t,.12,.86,.65),(.12,.27,.72,.27+t),(.12,.27,.12+t,.88),(.12,.88-t,.72,.88),(.72-t,.27,.72,.88),(.26,.57,.58,.57+t)):
                    line(x0,y0,x1,y1)
                if expanded:line(.42,.42,.42+t,.74)
                self._tree_icons.append(icon);button.configure(image=icon)
            if not getattr(self.tree,'_columns_initialized',False):
                widths=self._structured_widths or (22*unit,34*unit,10*unit)
                self.tree.column('#0',width=widths[0],minwidth=4*unit,stretch=False)
                self.tree.column('value',width=widths[1],minwidth=6*unit,stretch=True)
                self.tree.column('type',width=widths[2],minwidth=4*unit,stretch=False)
                self.tree._columns_initialized=True
            self.tree._invalidate()
            selected=self.tree.selection()
            if selected:self.tree.see(selected[0])
        else:
            columns=self.tree['columns']
            for index,key in enumerate(columns):
                examples=[self.tree.heading(key,'text')]+[r[index] for r in self._grid_rows[:50] if index<len(r)]
                width=max(9*unit,min(34*unit,max((font.measure(preview_cell_text(v)[:120]) for v in examples),default=0)+2*unit))
                self.tree.column(key,width=width,stretch=index==len(columns)-1)
    def _select_cell(self,event):
        column=self.tree.identify_column(event.x)
        if column:self._cell=max(0,int(column[1:])-1)
    def _context(self,event):
        if getattr(event,'num',None)==3:
            row=self.tree.identify_row(event.y)
            if not row:return 'break'
            self.tree.selection_set(row)
            column=self.tree.identify_column(event.x)
            if column:self._cell=max(0,int(column[1:])-1)
        x=getattr(event,'x_root',self.winfo_rootx()+20);y=getattr(event,'y_root',self.winfo_rooty()+40)
        try:self.menu.tk_popup(x,y)
        finally:self.menu.grab_release()
        return 'break'
    def _value(self):
        selection=self.tree.selection() if self.tree else ()
        if not selection and self._header_match is not None:return self._header_match
        if not selection:return self.model.get('content','') if not self.tree else ''
        iid=selection[0]
        if self.model['kind']=='tree':
            row=self._row_lookup[iid]
            return row['value']
        row=self._grid_rows[int(iid[1:])]
        return row[min(getattr(self,'_cell',0),len(row)-1)] if row else ''
    def copy(self):
        if self.tree:value=self._value()
        elif self.text:
            try:value=self.text.get('sel.first','sel.last')
            except tk.TclError:value=self.model.get('content','')
        else:value=self.model.get('content','')
        self.clipboard_clear();self.clipboard_append(value);return 'break'
    def _copy_path(self):
        selected=self.tree.selection()
        if selected:
            value=self._row_lookup[selected[0]]['path']
            self.clipboard_clear();self.clipboard_append(value)
    def _full_value(self,event=None):
        if event is not None and getattr(event,'num',None)==1:
            iid=self.tree.identify_row(event.y)
            if not iid:return 'break'
            self.tree.selection_set(iid)
            column=self.tree.identify_column(event.x)
            if column:self._cell=max(0,int(column[1:])-1)
        if self.model['kind']=='tree' and self.tree.selection():
            row=self._row_lookup[self.tree.selection()[0]]
            if row['kind'] in {'object','array','mapping','sequence'}:return None  # Native expand/collapse.
        popup=tk.Toplevel(self);popup.title(tr('Full value'));popup.geometry('800x480');popup.minsize(400,250)
        value=self._value()
        box=tk.Text(popup,wrap='none' if any(len(line)>32768 for line in value.splitlines()) else 'word',font=tkfont.nametofont('TkFixedFont'),padx=8,pady=8)
        scrollbar=ttk.Scrollbar(popup,command=box.yview);scrollbar.pack(side='right',fill='y');box.configure(yscrollcommand=scrollbar.set)
        box.pack(fill='both',expand=True);box.insert('1.0',value);box.configure(state='disabled')
        ttk.Button(popup,text=tr('Close'),command=popup.destroy).pack(side='right',padx=6,pady=6)
        popup.bind('<Escape>',lambda e:popup.destroy());return 'break'
    def _show_document(self):
        self.model['wrap_limited']=any(len(line)>32768 for line in self.model.get('content','').splitlines())
        self.text=tk.Text(self.body,wrap='word' if self.wrap and not self.model['wrap_limited'] else 'none',state='disabled',font=tkfont.nametofont('TkFixedFont'),padx=8,pady=6)
        self._scrollbars(self.text)
        self.text.tag_configure('render_add',background='#e5f4e9',foreground='#165b2e')
        self.text.tag_configure('render_remove',background='#fce7e7',foreground='#8b1b27')
        self.text.tag_configure('render_heading',foreground='#165d99',font='TkDefaultFont')
        self.text.tag_configure('render_hunk',background='#e4edf8',foreground='#1a4e86')
        self.text.tag_configure('format_match',background='#ffcc66',foreground='#17202a')
        generation=self._generation;content=self.model.get('content','');offset=0
        self._document_offset=0
        if self.model['wrap_limited']:content=content[:16384]
        def insert():
            nonlocal offset
            self._insert_job=None
            if generation!=self._generation or not self.winfo_exists():return
            self.text.configure(state='normal');self.text.insert('end',content[offset:offset+65536]);self.text.configure(state='disabled');offset+=65536
            if offset<len(content):self._insert_job=self.after(1,insert)
            else:
                for start,end,tag in self.model.get('spans',[]):
                    if start<len(content):self.text.tag_add(tag,f'1.0+{start}c',f'1.0+{min(end,len(content))}c')
        insert()
        sections=self.model.get('sections',[])
        if sections:
            self.choice.configure(values=tuple(s['title'][:100] for s in sections));self.choice.set(tr('Changes'))
            self.choice.pack(side='right',padx=4)
            self.text.bind('<F7>',lambda e:self._section(-1));self.text.bind('<F8>',lambda e:self._section(1))
    def set_wrap(self,enabled):
        self.wrap=bool(enabled)
        if self.text:self.text.configure(wrap='word' if self.wrap and not self.model.get('wrap_limited') else 'none')
    def _document_position(self,offset):
        if self.model.get('wrap_limited'):
            content=self.model['content'];start=max(0,offset-512)
            self._document_offset=start
            self.text.configure(state='normal');self.text.delete('1.0','end')
            self.text.insert('1.0',content[start:start+16384]);self.text.configure(state='disabled')
            for a,b,tag in self.model.get('spans',[]):
                if b>start and a<start+16384:self.text.tag_add(tag,f'1.0+{max(0,a-start)}c',f'1.0+{min(b-start,16384)}c')
        return f'1.0+{offset-self._document_offset}c'
    def _section(self,direction):
        sections=self.model.get('sections',[])
        if sections:
            index=(max(-1,self.choice.current())+direction)%len(sections)
            self.choice.current(index);self._choose()
        return 'break'
    def _show_image(self):
        self.original=tk.PhotoImage(data=self.model['png'],format='png');self.images=[self.original]
        self.canvas=tk.Canvas(self.body,background='#e6e9ed',highlightthickness=0)
        self._scrollbars(self.canvas)
        self.choice.configure(values=(tr('Fit width'),'100%','200%'));self.choice.set('100%')
        self.choice.pack(side='right',padx=4)
        self.canvas.bind('<Configure>',lambda e:self._draw_image())
        self.canvas.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-int(e.delta/120) if e.delta else 0,'units'))
        self.canvas.bind('<Button-4>',lambda e:self.canvas.yview_scroll(-3,'units'))
        self.canvas.bind('<Button-5>',lambda e:self.canvas.yview_scroll(3,'units'))
        self.after_idle(self._draw_image)
    def _draw_image(self):
        if not self.canvas or not self.canvas.winfo_exists():return
        value=self.choice.get();width=self.original.width()
        factor=2 if value=='200%' else 1
        divisor=max(1,(width+max(100,self.canvas.winfo_width()-12)-1)//max(100,self.canvas.winfo_width()-12)) if value==tr('Fit width') else 1
        # Integer subsampling keeps Tk memory bounded, original raster stays available.
        key=(self._generation,factor,divisor)
        if self._image_view_key!=key:
            self.display_image=self.original.subsample(divisor) if divisor>1 else self.original.zoom(factor) if factor>1 else self.original
            self._image_view_key=key
            self.images=[self.original,self.display_image];self.scale=factor/divisor
            self.canvas.delete('all');self.canvas.create_image(0,0,image=self.display_image,anchor='nw')
            self.canvas.configure(scrollregion=(0,0,self.display_image.width(),self.display_image.height()))
        self._paint_image_match()
    def _paint_image_match(self):
        self.canvas.delete('search_hit')
        node=self._image_match
        if node:
            x,y,w,h=(node[k]*self.scale for k in ('x','y','w','h'))
            self.canvas.create_rectangle(x,y,x+w,y+h,outline='#db6c00',width=3,tags='search_hit')
            self.canvas.yview_moveto(max(0,(y-20)/max(1,self.display_image.height())))
            self.canvas.xview_moveto(max(0,(x-20)/max(1,self.display_image.width())))
    def _choose(self):
        if self.canvas:self._draw_image()
        elif self.tree and self.model['kind']=='grid':
            self._grid_header=self.choice.get()==tr('First row: header')
            for child in self.body.winfo_children():child.destroy()
            self._show_tree('grid')
        elif self.text:
            index=self.choice.current();sections=self.model.get('sections',[])
            if 0<=index<len(sections):self.text.see(self._document_position(sections[index]['offset']))
    def _expand_tree(self,expanded):
        if self.tree and self.model.get('kind')=='tree':
            self.cancel_tree_reveal()
            tree=self.tree;tree.begin_batch();restore=[];self._expand_restore=restore
            rows=iter(tuple(self._row_lookup));self._tree_revealing=True
            def completed():
                if self._expand_restore is restore:self._expand_restore=None
            tree._layout_finished=completed
            def batch():
                if self._expand_restore is not restore:return
                self._insert_job=None;start=time.monotonic();count=0
                try:
                    while count<100 and time.monotonic()-start<.008:
                        try:iid=next(rows)
                        except StopIteration:
                            self._tree_revealing=False;tree.end_batch();return
                        count+=1;before=bool(tree.item(iid,'open'))
                        if before!=expanded:
                            restore.append((iid,before));tree.item(iid,open=expanded)
                    self._insert_job=self.after(1,batch)
                except (tk.TclError,ValueError):
                    self.cancel_tree_reveal();raise
            batch()
    def cancel_tree_reveal(self):
        if self._tree_revealing and self._insert_job is not None:
            self.after_cancel(self._insert_job);self._insert_job=None
        self._tree_revealing=False
        if self._expand_restore is not None and self.tree:
            self.tree.begin_batch()
            for iid,opened in self._expand_restore:
                if self.tree.exists(iid):self.tree.item(iid,open=opened)
            self._expand_restore=None;self.tree._layout_finished=None
            self.tree.end_batch(commit=False)
    def _tree_match_text(self,row,match):
        iid=row['id']
        if isinstance(self.tree,WrappedTreeview):
            self.tree.item(iid,text=row['label'],values=(row['value'],row['kind']))
            if match:self.tree._match[iid]=(match.get('field'),match.get('start',0),match.get('end',0))
            else:self.tree._match.pop(iid,None)
            return
        label=preview_cell_text(row['label'])[:500]
        value=preview_cell_text(row['value'])[:500]
        field=match.get('field')
        if field in {'label','value'}:
            snippet=preview_match_excerpt(row[field],match['start'],match['end'])
            if field=='value':value=snippet
            else:label=snippet
        self.tree.item(iid,text=label,values=(value,row['kind']))
    def apply_tree_search(self,result,*,key=None,complete=None,current=None):
        """Retain this query's visited branches; reveal bulk results in UI batches."""
        if not self.tree or self.model.get('kind')!='tree':return
        self.cancel_tree_reveal()
        if key!=self._tree_search_key:
            for iid in self._tree_search_rows:
                row=self._row_lookup.get(iid)
                if row:self._tree_match_text(row,{})
            for iid in reversed(self._search_extra):
                if self.tree.exists(iid):self.tree.delete(iid)
                self._row_lookup.pop(iid,None)
            self._search_extra=[];self._tree_search_rows=set();self._tree_search_key=key
        matches={m['id']:m for m in result.get('matches',[])}
        # Compatibility with one-branch callers; selected need not be the last
        # row when a bulk result contains several sibling branches.
        selected=result.get('selected',result['rows'][-1]['id'] if result['rows'] else None)
        if selected:matches[selected]=dict(id=selected,field=result.get('field'),start=result.get('start',0),end=result.get('end',0))
        missing=[r for r in result['rows'] if r['id'] not in self._row_lookup]
        limited=result.get('display_limited',False)
        if len(self._search_extra)+len(missing)>STRUCTURE_REVEAL_LIMIT:
            # Preserve previous matches rather than silently evicting them.
            if complete:complete(True,0)
            return
        generation=self._generation;cursor=0;self._tree_revealing=True
        def insert_rows():
            nonlocal cursor
            self._insert_job=None
            if generation!=self._generation or not self._tree_revealing:return
            if current and not current():
                self._tree_revealing=False
                if complete:complete(limited,-1)
                return
            started=time.monotonic();count=0
            while cursor<len(result['rows']) and count<100 and time.monotonic()-started<.008:
                row=result['rows'][cursor];cursor+=1;count+=1;iid=row['id']
                if iid not in self._row_lookup:
                    siblings=self.tree.get_children(row['parent'])
                    position=next((i for i,other in enumerate(siblings) if int(other[1:])>int(iid[1:])),len(siblings))
                    self.tree.insert(row['parent'],position,iid=iid,text=row['label'],
                                     values=(row['value'],row['kind']))
                    self._row_lookup[iid]=row;self._search_extra.append(iid)
                # Every returned row is on a matched path; unrelated initial
                # branches keep their own expansion state.
                if row['kind'] in {'object','array','mapping','sequence'}:self.tree.item(iid,open=True)
                if iid in matches:
                    self._tree_match_text(row,matches[iid]);self._tree_search_rows.add(iid)
            if cursor<len(result['rows']):self._insert_job=self.after(1,insert)
            else:
                self._tree_revealing=False
                if selected and self.tree.exists(selected):
                    self.tree.selection_set(selected);self.tree.focus(selected);self.tree.see(selected);self._cell=0
                elif not result['rows']:self.tree.selection_remove(*self.tree.selection())
                if complete:complete(limited,len(matches))
        def insert():
            try:insert_rows()
            except (tk.TclError,ValueError,UnicodeError) as exc:
                self._insert_job=None;self._tree_revealing=False
                if complete:complete(limited,-2,exc)
                else:raise
        insert()
    def find(self,needle,case=False,direction=1):
        self._clear_find_display()
        if not needle:return tr('Enter search text')
        flags=0 if case else re.I;pattern=re.compile(re.escape(needle),flags);hits=[]
        if self.tree and self.model['kind']=='grid':
            cells=((-1,c,label) for c,label in enumerate(self._grid_headings))
            cells=chain(cells,((r,c,value) for r,row in enumerate(self._grid_rows) for c,value in enumerate(row)))
            for row,column,value in cells:
                for match in pattern.finditer(value):
                    hits.append((row,column,match.start(),match.end()))
                    if len(hits)>5000:break
                if len(hits)>5000:break
        elif self.tree:
            for index,row in enumerate(self.model['rows'] if self.model['kind']=='tree' else self._grid_rows):
                values=(row['label'],row['value'],row['path']) if self.model['kind']=='tree' else row
                for column,value in enumerate(values):
                    if pattern.search(value):hits.append((index,column));break
        else:hits=[m.start() for m in islice(pattern.finditer(self.model.get('content','')),5001)]
        limited=len(hits)>5000;hits=hits[:5000]
        key=(needle,case)
        if getattr(self,'_find_key',None)!=key:self.match_index=-1;self._find_key=key
        if not hits:return tr('No matches')
        self.match_index=((0 if direction>0 else len(hits)-1) if self.match_index<0 else (self.match_index+direction)%len(hits));hit=hits[self.match_index]
        header=False
        if self.tree and self.model['kind']=='grid':
            index,column,start,end=hit;key=self.tree['columns'][column]
            self._cell=column
            if index<0:
                header=True;self._header_match=self._grid_headings[column]
                self.tree.selection_remove(*self.tree.selection())
                self.tree.heading(key,text='▶ '+preview_match_excerpt(self._header_match,start,end))
            else:
                self._grid_search_row=index;iid='r'+str(index)
                shown=[preview_cell_text(v)[:500] for v in self._grid_rows[index]]
                shown[column]=preview_match_excerpt(self._grid_rows[index][column],start,end)
                self.tree.item(iid,values=shown);self.tree.selection_set(iid);self.tree.focus(iid);self.tree.see(iid)
            left=sum(self.tree.column(k,'width') for k in self.tree['columns'][:column])
            total=sum(self.tree.column(k,'width') for k in self.tree['columns'])
            self.tree.xview_moveto(left/max(1,total))
        elif self.tree:
            index,column=hit;iid=self.model['rows'][index]['id'] if self.model['kind']=='tree' else 'r'+str(index)
            parent=self.tree.parent(iid)
            while parent:self.tree.item(parent,open=True);parent=self.tree.parent(parent)
            self.tree.selection_set(iid);self.tree.focus(iid);self.tree.see(iid);self._cell=column
        elif self.text:
            # Native Windows Tk also measures an unwrapped megabyte line during
            # repaint; display an exact bounded slice while retaining full data.
            self._document_position(hit)
            local_hit=hit-self._document_offset
            self.text.tag_remove('format_match','1.0','end');self.text.tag_add('format_match',f'1.0+{local_hit}c',f'1.0+{local_hit+len(needle)}c')
            self.text.see(f'1.0+{local_hit}c')
        elif self.canvas:
            self._image_match=next((p for p in self.model.get('positions',[]) if p['start']<=hit<p['end']),None)
            self._draw_image()
        detail=tr('Match {current} of {total}',current=self.match_index+1,total=len(hits))
        if header:detail=tr('Column header')+' · '+detail
        if limited:detail=tr('Showing the first 5,000 search matches')+' · '+detail
        return detail
    def _clear_find_display(self):
        if self.tree and self.model['kind']=='grid':
            if self._grid_search_row is not None:
                index=self._grid_search_row
                self.tree.item('r'+str(index),values=tuple(preview_cell_text(v)[:500] for v in self._grid_rows[index]))
            for column,label in zip(self.tree['columns'],self._grid_headings):self.tree.heading(column,text=preview_cell_text(label)[:500])
        self._grid_search_row=None;self._header_match=None;self._image_match=None
        if self.text:self.text.tag_remove('format_match','1.0','end')
        if self.canvas:self.canvas.delete('search_hit')
