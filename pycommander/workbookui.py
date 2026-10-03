"""Read-only, paged worksheet cell comparisons; no Office automation."""
import html
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog, font as tkfont
from .reviewjobs import ComparisonJobs
from .workbook import workbook_rows, cell_position, cell_values_equal
from .reviewstorage import safe_review_write
from .i18n import tr
from .tooltip import ToolTip
from .settings import readable_check_style
from .comparecolors import comparison_colors


class WorkbookCompare(ttk.Frame):
    PAGE=200
    def __init__(self,master,left,right,**options):
        super().__init__(master);self.view=self;self.paths=[Path(left),Path(right)]
        self.jobs=ComparisonJobs();self.books=None;self.rows=[];self.filtered=[];self.top=0;self._job=None
        self._generation=0;self._row_results=queue.Queue();self._rows_job=None
        self.sheet=tk.StringVar();self.only=tk.BooleanVar(value=False);self.search_var=tk.StringVar()
        self.keys=();self.header_row=1;self.cell_mode=tk.StringVar(value='Both')
        self._filter_needle='';self._pending_find=None;self.difference_count=0
        bar=ttk.Frame(self);bar.pack(fill='x',padx=4,pady=3)
        ttk.Label(bar,text=tr('Worksheet')).pack(side='left')
        self.sheets=ttk.Combobox(bar,state='readonly',textvariable=self.sheet,width=20)
        self.sheets.pack(side='left',fill='x',expand=True);self.sheets.bind('<<ComboboxSelected>>',lambda e:self.load_sheet())
        menu_button=ttk.Menubutton(bar,text=tr('Rules'));menu_button.pack(side='left')
        menu=tk.Menu(menu_button,tearoff=False);menu_button.configure(menu=menu)
        menu.add_checkbutton(label=tr('Differences only'),variable=self.only,command=self.filter)
        for value in ('Both','Values','Formulas'):
            menu.add_radiobutton(label=tr(value),value=value,variable=self.cell_mode,command=self.filter)
        menu.add_command(label=tr('Row key columns…'),command=self.set_keys)
        ttk.Button(bar,text=tr('Export report'),command=self.export_report).pack(side='left',padx=2)
        ttk.Button(bar,text=tr('Cancel'),command=self.cancel).pack(side='left')
        find=ttk.Frame(self);find.pack(fill='x',padx=4)
        ttk.Label(find,text=tr('Find:')).pack(side='left')
        self.search=ttk.Entry(find,textvariable=self.search_var,width=8);self.search.pack(side='left',fill='x',expand=True)
        self.search.bind('<Return>',lambda e:self.find_next())
        self.search.bind('<Shift-Return>',lambda e:self.find_previous())
        self.only_button=ttk.Checkbutton(find,text=tr('Differences only'),variable=self.only,command=self.filter,
            style=readable_check_style(self,tkfont.nametofont('TkDefaultFont'),prefix='Workbook'))
        self.only_button.pack(side='right',padx=4)
        for label,cmd in [('Find',self.filter),('◀',self.find_previous),('▶',self.find_next)]:
            button=ttk.Button(find,text=tr(label),width=0,command=cmd);button.pack(side='left',padx=2)
            ToolTip(button,tr('Find Prev')+' · Shift+F3' if label=='◀' else tr('Find Next')+' · F3' if label=='▶' else tr('Find:'))
        self.tree=ttk.Treeview(self,columns=('status','left','value_l','formula_l','right','value_r','formula_r'),show='headings',style='Workbook.Treeview')
        self.apply_scale(1)
        for name,title,width in [('status','Status',90),('left','L Cell',70),('value_l','L Value / cached result',220),
                                 ('formula_l','L Formula',220),('right','R Cell',70),('value_r','R Value / cached result',220),('formula_r','R Formula',220)]:
            self.tree.heading(name,text=tr(title));self.tree.column(name,width=width,minwidth=60,stretch=name in ('value_l','value_r'))
        self.tree.pack(fill='both',expand=True)
        self.empty=ttk.Frame(self.tree,padding=12)
        self.empty_text=ttk.Label(self.empty,text='',anchor='center',wraplength=520)
        self.empty_text.pack()
        self.show_all_button=ttk.Button(self.empty,text=tr('Show all cells'),command=self.show_all)
        x=ttk.Scrollbar(self,orient='horizontal',command=self.tree.xview);x.pack(fill='x');self.tree.configure(xscrollcommand=x.set)
        self.scrollbar=ttk.Scrollbar(self,command=self.scroll);self.scrollbar.pack(side='right',fill='y',before=self.tree)
        self.tree.bind('<Double-Button-1>',self.show_cell)
        self.tree.bind('<MouseWheel>',lambda e:self.scroll('scroll',-3 if e.delta>0 else 3,'units'))
        self.tree.bind('<Button-4>',lambda e:self.scroll('scroll',-3,'units'))
        self.tree.bind('<Button-5>',lambda e:self.scroll('scroll',3,'units'))
        self.status=ttk.Label(self,text=tr('Loading workbook…'),width=1);self.status.pack(fill='x')
        ToolTip(self.status,lambda:self.status.cget('text'))
        self.bind('<Destroy>',self.destroyed,add='+')
        self.serial=self.jobs.submit({'mode':'workbook','paths':[str(p) for p in self.paths]});self._job=self.after(40,self.poll)

    def poll(self):
        self._job=None
        try:serial,result=self.jobs.results.get_nowait()
        except queue.Empty:self._job=self.after(40,self.poll);return
        if serial!=self.serial:return
        if 'error' in result:
            self.status.configure(text=result['error']);self.show_empty(tr('Workbook could not be read')+'\n'+result['error']);return
        self.books=result['books'];names=[]
        for book in self.books:
            for sheet in book['sheets']:
                if sheet['name'] not in names:names.append(sheet['name'])
        self.sheets.configure(values=names)
        if names:self.sheet.set(names[0]);self.load_sheet()
        else:
            self.status.configure(text=tr('Workbook has no worksheets'));self.show_empty(tr('Workbook has no worksheets'))

    def load_sheet(self):
        if not self.books:return
        self.selected=[next((s for s in b['sheets'] if s['name']==self.sheet.get()),None) for b in self.books]
        self.filter(rebuild=True)

    def equal(self,a,b):
        return cell_values_equal(a,b,self.cell_mode.get())

    def filter(self,rebuild=False):
        if not self.books:return
        self._generation+=1;serial=self._generation
        needle=self.search_var.get().casefold();only=self.only.get();mode=self.cell_mode.get()
        self._filter_needle=needle
        selected=list(self.selected);keys=self.keys;header=self.header_row
        self.rows=[];self.filtered=[];self.tree.delete(*self.tree.get_children())
        self.show_empty(tr('Comparing worksheet…'))
        self.status.configure(text=tr('Comparing worksheet…'))
        def work():
            try:
                rows=workbook_rows(*selected,keys,header);filtered=[];differences=0
                for n,(ar,br,a,b) in enumerate(rows):
                    if serial!=self._generation:return
                    different=not cell_values_equal(a,b,mode);differences+=different
                    if (not only or different) and (not needle or needle in (ar+' '+br+' '+str(a)+' '+str(b)).casefold()):filtered.append(n)
                self._row_results.put((serial,rows,filtered,None,differences))
            except Exception as exc:self._row_results.put((serial,[],[],str(exc),0))
        threading.Thread(target=work,daemon=True).start()
        if self._rows_job is None:self._rows_job=self.after(40,self.poll_rows)

    def poll_rows(self):
        self._rows_job=None
        try:serial,rows,filtered,error,differences=self._row_results.get_nowait()
        except queue.Empty:self._rows_job=self.after(40,self.poll_rows);return
        if serial!=self._generation:self._rows_job=self.after(40,self.poll_rows);return
        self.rows=rows;self.filtered=filtered;self.difference_count=differences;self.top=0;self.render()
        if error:self.status.configure(text=error);self.show_empty(error)
        elif self._pending_find is not None:
            direction=self._pending_find;self._pending_find=None;self._move_result(direction)

    @staticmethod
    def value(cell):
        if cell is None:return '—',''
        typ,value,formula=cell
        return (('[cached result unavailable]' if formula else '[blank]') if value is None else str(value)),formula

    def render(self):
        self.tree.delete(*self.tree.get_children())
        end=min(len(self.filtered),self.top+self.PAGE)
        for n in self.filtered[self.top:end]:
            ar,br,a,b=self.rows[n];av,af=self.value(a);bv,bf=self.value(b)
            status='Same' if self.equal(a,b) else ('Right only' if a is None else 'Left only' if b is None else 'Changed')
            self.tree.insert('', 'end',iid=str(n),values=(tr(status),ar,av[:2000],af[:2000],br,bv[:2000],bf[:2000]),tags=(status,))
        self.scrollbar.set(self.top/max(1,len(self.filtered)),end/max(1,len(self.filtered)))
        meta=' · '.join(('L' if n==0 else 'R')+': '+(s['state']+f', {len(s["merged"])} merged ranges' if s else 'sheet missing') for n,s in enumerate(self.selected)) if self.books else ''
        dates=' · '+tr('Different Excel date systems') if self.books and self.books[0]['date1904']!=self.books[1]['date1904'] else ''
        summary=tr('{cells} cells compared · {diffs} differences · {sheets} worksheets',
                   cells=len(self.rows),diffs=self.difference_count,sheets=len(self.sheets.cget('values')))
        self.status.configure(text=summary+f' · {self.top+1 if end else 0}–{end}/{len(self.filtered)} · '+tr('Read-only · formulas are not recalculated · double-click for full cell')+' · '+meta+dates)
        if not self.filtered:
            reason=(tr('No cells match the current filter') if self._filter_needle else
                    tr('No value/formula differences in this worksheet') if self.rows else
                    tr('This worksheet contains no stored cell values or formulas'))
            self.show_empty(reason+'\n'+summary+'\n'+tr('Other worksheets may differ. Formatting, pictures and charts are not compared.'),bool(self.rows))
        else:self.empty.place_forget()

    def show_empty(self,text,show_all=False):
        self.empty_text.configure(text=text)
        self.show_all_button.pack(pady=(8,0)) if show_all else self.show_all_button.pack_forget()
        self.empty.place(relx=.5,rely=.5,anchor='center')

    def show_all(self):
        self.only.set(False);self.search_var.set('');self.filter()

    def scroll(self,*args):
        self.top=int(float(args[1])*len(self.filtered)) if args[0]=='moveto' else self.top+int(args[1])*(self.PAGE if args[2]=='pages' else 1)
        self.top=max(0,min(max(0,len(self.filtered)-1),self.top));self.render();return 'break'

    def _move_result(self,direction,differences=False):
        if self._rows_job is not None:return
        rows=[n for n in self.filtered if not differences or not self.equal(*self.rows[n][2:])]
        if not rows:return
        selection=self.tree.selection();current=int(selection[0]) if selection else None
        index=rows.index(current) if current in rows else (-1 if direction>0 else 0)
        target=rows[(index+direction)%len(rows)]
        self.top=(self.filtered.index(target)//self.PAGE)*self.PAGE;self.render()
        self.tree.selection_set(str(target));self.tree.focus(str(target));self.tree.see(str(target))

    def find_next(self):return self._find(1)
    def find_previous(self):return self._find(-1)
    def _find(self,direction):
        if not self.search_var.get():return self.focus_search()
        if self._filter_needle!=self.search_var.get().casefold():
            self._pending_find=direction;self.filter()
        else:self._move_result(direction)
        return 'break'

    def next(self):self._move_result(1,True)
    def previous(self):self._move_result(-1,True)
    def focus_search(self):self.search.focus_set();return 'break'
    def set_read_only(self,*args,**kwargs):pass
    def apply_scale(self,scale):
        face=tkfont.nametofont('TkDefaultFont')
        ttk.Style(self).configure('Workbook.Treeview',font=face,rowheight=face.metrics('linespace')+8)
        self.only_button.configure(style=readable_check_style(self,face,
            getattr(self,'_dark',False),'Workbook'))
    def apply_language(self,old):pass
    def apply_color_scheme(self,palette):
        colors=comparison_colors(palette)
        self._dark=colors['base']!='#ffffff';self.apply_scale(1)
        for tag,color in [('Changed','line'),('Left only','orphan'),('Right only','orphan')]:
            self.tree.tag_configure(tag,background=colors[color],foreground=colors['text'])

    def set_keys(self):
        value=simpledialog.askstring(tr('Row key columns'),tr('Column letters separated by commas (e.g. A,C). Empty = cell coordinates.'),parent=self)
        if value is None:return
        try:keys=tuple(cell_position(v.strip().upper()+'1')[1] for v in value.split(',') if v.strip())
        except ValueError as exc:messagebox.showerror(tr('Rules'),str(exc),parent=self);return
        header=simpledialog.askinteger(tr('Header row'),tr('Rows at/before this number are headers; 0 = none'),parent=self,minvalue=0,maxvalue=1048576,initialvalue=self.header_row) if keys else 1
        if header is None:return
        self.keys=keys;self.header_row=header;self.load_sheet()

    def show_cell(self,event=None):
        selected=self.tree.selection()
        if not selected:return
        ar,br,a,b=self.rows[int(selected[0])]
        dialog=tk.Toplevel(self);dialog.title(f'{ar} ↔ {br}');dialog.geometry('900x500')
        dialog.bind('<KeyPress>',lambda e:'break')
        scroll=ttk.Scrollbar(dialog);scroll.pack(side='right',fill='y')
        text=tk.Text(dialog,wrap='word',font='TkFixedFont',yscrollcommand=scroll.set);text.pack(fill='both',expand=True)
        scroll.configure(command=text.yview)
        text.insert('1.0',f'LEFT · {ar}\n{self.value(a)[0]}\nFormula: {self.value(a)[1]}\n\nRIGHT · {br}\n{self.value(b)[0]}\nFormula: {self.value(b)[1]}');text.configure(state='disabled')

    def export_report(self):
        if not self.books:return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.html')
        if not path:return
        include=messagebox.askyesno(tr('Export report'),tr('Include cell values/formulas? No exports addresses/status only.'),default='no',parent=self)
        lines=[self.sheet.get()+' · '+self.cell_mode.get()+' · no recalculation']
        for n in self.filtered:
            ar,br,a,b=self.rows[n];lines.append(f'{ar} ↔ {br}: '+('same' if self.equal(a,b) else 'different'))
            if include:lines.append(str(a)+'\n'+str(b))
        data='<!doctype html><meta charset="utf-8"><title>PFC workbook comparison</title><pre>'+html.escape('\n'.join(lines))+'</pre>'
        try:safe_review_write(Path(path),data.encode(),self.paths)
        except OSError as exc:messagebox.showerror(tr('Export report'),str(exc),parent=self)

    def cancel(self):
        self._generation+=1
        if self._rows_job is not None:self.after_cancel(self._rows_job);self._rows_job=None
        self.jobs.cancel()
        if self._job is not None:self.after_cancel(self._job);self._job=None
        self.status.configure(text=tr('Cancelled'))

    def destroyed(self,event):
        if event.widget is self:
            self._generation+=1
            if self._rows_job is not None:self.after_cancel(self._rows_job);self._rows_job=None
            self.jobs.cancel()
            if self._job is not None:self.after_cancel(self._job);self._job=None
            self.sheet=self.only=self.search_var=self.cell_mode=None
