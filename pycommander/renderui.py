"""One compact read-only view for structured, tabular, textual and image models."""
import base64
import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from .i18n import tr
from .tooltip import ToolTip


def preview_cell_text(value):
    """Single-line display only; the original value remains available to copy."""
    return value.replace('\r\n','\n').replace('\r','\n').replace('\n',' ↵ ')


class FormatRenderView(ttk.Frame):
    def __init__(self,master):
        super().__init__(master)
        self.model={};self.images=[];self.match_index=-1;self._generation=0;self._insert_job=None
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
        ToolTip(self.expand_button,lambda:tr('Expand all'))
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
        self._generation+=1
        if self._insert_job is not None:
            self.after_cancel(self._insert_job);self._insert_job=None
        for child in self.body.winfo_children():child.destroy()
        if getattr(self,'menu',None) is not None:self.menu.destroy();self.menu=None
        self.images=[];self.tree=None;self.text=None;self.canvas=None;self.choice.pack_forget();self.tree_actions.pack_forget();self.match_index=-1
        for name in ('original','display_image'):
            if hasattr(self,name):delattr(self,name)
    def show(self,model):
        self.clear();self.model=model;kind=model['kind']
        self.detail.configure(text=tr({'tree':'Structure','grid':'Table','document':'Document','image':'Static visual preview'}[kind]))
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
        if kind=='tree':
            columns=('value','type');self.tree=ttk.Treeview(self.body,columns=columns,show='tree headings',selectmode='browse')
            self.tree.heading('#0',text=tr('Key / index'));self.tree.heading('value',text=tr('Value'));self.tree.heading('type',text=tr('Type'))
            for row in self.model['rows']:
                shown=preview_cell_text(row['value'])
                self.tree.insert(row['parent'],'end',iid=row['id'],text=row['label'],values=(shown[:500],row['kind']),open=row['path'].count('/')<=1)
            self.tree_actions.pack(side='right',padx=4)
        else:
            columns=tuple('c'+str(i) for i in range(len(self.model['columns'])))
            headers=self.model['columns'] if self._grid_header else ['Column '+str(i+1) for i in range(len(columns))]
            self._grid_rows=self.model['rows'] if self._grid_header else [self.model['columns']]+self.model['rows']
            self.tree=ttk.Treeview(self.body,columns=columns,show='headings',selectmode='browse')
            for index,(key,label) in enumerate(zip(columns,headers)):
                self.tree.heading(key,text=label)
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
            self.tree.column('#0',width=22*unit,minwidth=16*unit)
            self.tree.column('value',width=34*unit,minwidth=12*unit)
            self.tree.column('type',width=10*unit,minwidth=8*unit,stretch=False)
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
        if not selection:return self.model.get('content','') if not self.tree else ''
        iid=selection[0]
        if self.model['kind']=='tree':
            row=self.model['rows'][int(iid[1:])]
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
            value=self.model['rows'][int(selected[0][1:])]['path']
            self.clipboard_clear();self.clipboard_append(value)
    def _full_value(self,event=None):
        if event is not None and getattr(event,'num',None)==1:
            iid=self.tree.identify_row(event.y)
            if not iid:return 'break'
            self.tree.selection_set(iid)
            column=self.tree.identify_column(event.x)
            if column:self._cell=max(0,int(column[1:])-1)
        if self.model['kind']=='tree' and self.tree.selection():
            row=self.model['rows'][int(self.tree.selection()[0][1:])]
            if row['kind'] in {'object','array','mapping','sequence'}:return None  # Native expand/collapse.
        popup=tk.Toplevel(self);popup.title(tr('Full value'));popup.geometry('800x480');popup.minsize(400,250)
        box=tk.Text(popup,wrap='word',font=tkfont.nametofont('TkFixedFont'),padx=8,pady=8)
        scrollbar=ttk.Scrollbar(popup,command=box.yview);scrollbar.pack(side='right',fill='y');box.configure(yscrollcommand=scrollbar.set)
        box.pack(fill='both',expand=True);box.insert('1.0',self._value());box.configure(state='disabled')
        ttk.Button(popup,text=tr('Close'),command=popup.destroy).pack(side='right',padx=6,pady=6)
        popup.bind('<Escape>',lambda e:popup.destroy());return 'break'
    def _show_document(self):
        self.text=tk.Text(self.body,wrap='word' if self.wrap else 'none',state='disabled',font=tkfont.nametofont('TkFixedFont'),padx=8,pady=6)
        self._scrollbars(self.text)
        self.text.tag_configure('render_add',background='#e5f4e9',foreground='#165b2e')
        self.text.tag_configure('render_remove',background='#fce7e7',foreground='#8b1b27')
        self.text.tag_configure('render_heading',foreground='#165d99',font='TkDefaultFont')
        self.text.tag_configure('render_hunk',background='#e4edf8',foreground='#1a4e86')
        self.text.tag_configure('format_match',background='#ffcc66',foreground='#17202a')
        generation=self._generation;content=self.model.get('content','');offset=0
        def insert():
            nonlocal offset
            self._insert_job=None
            if generation!=self._generation or not self.winfo_exists():return
            self.text.configure(state='normal');self.text.insert('end',content[offset:offset+65536]);self.text.configure(state='disabled');offset+=65536
            if offset<len(content):self._insert_job=self.after(1,insert)
            else:
                for start,end,tag in self.model.get('spans',[]):self.text.tag_add(tag,f'1.0+{start}c',f'1.0+{end}c')
        insert()
        sections=self.model.get('sections',[])
        if sections:
            self.choice.configure(values=tuple(s['title'][:100] for s in sections));self.choice.set(tr('Changes'))
            self.choice.pack(side='right',padx=4)
            self.text.bind('<F7>',lambda e:self._section(-1));self.text.bind('<F8>',lambda e:self._section(1))
    def set_wrap(self,enabled):
        self.wrap=bool(enabled)
        if self.text:self.text.configure(wrap='word' if self.wrap else 'none')
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
        self.display_image=self.original.subsample(divisor) if divisor>1 else self.original.zoom(factor) if factor>1 else self.original
        self.images=[self.original,self.display_image];self.scale=factor/divisor
        self.canvas.delete('all');self.canvas.create_image(0,0,image=self.display_image,anchor='nw')
        self.canvas.configure(scrollregion=(0,0,self.display_image.width(),self.display_image.height()))
    def _choose(self):
        if self.canvas:self._draw_image()
        elif self.tree and self.model['kind']=='grid':
            self._grid_header=self.choice.get()==tr('First row: header')
            for child in self.body.winfo_children():child.destroy()
            self._show_tree('grid')
        elif self.text:
            index=self.choice.current();sections=self.model.get('sections',[])
            if 0<=index<len(sections):self.text.see(f"1.0+{sections[index]['offset']}c")
    def _expand_tree(self,expanded):
        if self.tree and self.model.get('kind')=='tree':
            for row in self.model['rows']:self.tree.item(row['id'],open=expanded)
    def find(self,needle,case=False,direction=1):
        if not needle:return tr('Enter search text')
        flags=0 if case else re.I;pattern=re.compile(re.escape(needle),flags);hits=[]
        if self.tree:
            for index,row in enumerate(self.model['rows'] if self.model['kind']=='tree' else self._grid_rows):
                values=(row['label'],row['value'],row['path']) if self.model['kind']=='tree' else row
                for column,value in enumerate(values):
                    if pattern.search(value):hits.append((index,column));break
        else:hits=[m.start() for m in pattern.finditer(self.model.get('content',''))][:5000]
        key=(needle,case)
        if getattr(self,'_find_key',None)!=key:self.match_index=-1;self._find_key=key
        if not hits:return tr('No matches')
        self.match_index=((0 if direction>0 else len(hits)-1) if self.match_index<0 else (self.match_index+direction)%len(hits));hit=hits[self.match_index]
        if self.tree:
            index,column=hit;iid=self.model['rows'][index]['id'] if self.model['kind']=='tree' else 'r'+str(index)
            parent=self.tree.parent(iid)
            while parent:self.tree.item(parent,open=True);parent=self.tree.parent(parent)
            self.tree.selection_set(iid);self.tree.focus(iid);self.tree.see(iid);self._cell=column
        elif self.text:
            self.text.tag_remove('format_match','1.0','end');self.text.tag_add('format_match',f'1.0+{hit}c',f'1.0+{hit+len(needle)}c');self.text.see(f'1.0+{hit}c')
        elif self.canvas:
            self.canvas.delete('search_hit')
            node=next((p for p in self.model.get('positions',[]) if p['start']<=hit<p['end']),None)
            if node:
                x,y,w,h=(node[k]*self.scale for k in ('x','y','w','h'))
                self.canvas.create_rectangle(x,y,x+w,y+h,outline='#db6c00',width=3,tags='search_hit')
                self.canvas.yview_moveto(max(0,(y-20)/max(1,self.display_image.height())))
        return tr('Match {current} of {total}',current=self.match_index+1,total=len(hits))
