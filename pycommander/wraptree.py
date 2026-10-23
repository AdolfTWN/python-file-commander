"""Structured preview: native resizable headings, variable-height canvas rows.

The native tree owns hierarchy/selection; only its fixed-height body is replaced.
Text layout is bounded and batched, and only viewport rows are painted.
"""
from bisect import bisect_right
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


class WrappedTreeview(ttk.Treeview):
    def __init__(self,master,**kw):
        super().__init__(master,**kw)
        self._display={};self._layouts={};self._entries=[];self._ends=[]
        self._layout_job=None;self._paint_job=None;self._revision=0
        self._yscroll=None;self._xscroll=None;self._offset=0;self._left=0
        self._total=1;self._extent=1;self._pending_see=None;self._match={}
        self._indent=18
        self._layout_epoch=0;self._defer_layout=False;self._layout_finished=None;self._viewport_width=None
        self._body=tk.Canvas(self,highlightthickness=0,takefocus=False)
        self._body.place(x=1,y=25,relwidth=1,width=-2,relheight=1,height=-26)
        self.bind('<Configure>',self._geometry_changed,add='+')
        self.bind('<ButtonRelease-1>',lambda e:self._columns_changed(),add='+')
        self.bind('<B1-Motion>',lambda e:self._columns_changed(),add='+')
        self.bind('<<TreeviewOpen>>',lambda e:self._invalidate(),add='+')
        self.bind('<<TreeviewClose>>',lambda e:self._invalidate(),add='+')
        self.bind('<<TreeviewSelect>>',lambda e:self._schedule_paint(),add='+')
        self._body.bind('<Button-1>',self._click)
        self._body.bind('<ButtonRelease-1>',lambda e:self._forward(e,'<ButtonRelease-1>'))
        self._body.bind('<Double-1>',lambda e:self._forward(e,'<Double-1>'))
        self._body.bind('<Button-3>',lambda e:self._forward(e,'<Button-3>'))
        self._body.bind('<MouseWheel>',self._wheel)
        self._body.bind('<Button-4>',lambda e:self.yview_scroll(-3,'units'))
        self._body.bind('<Button-5>',lambda e:self.yview_scroll(3,'units'))
        for key in ('Up','Down','Left','Right','Home','End','Prior','Next'):
            self.bind('<'+key+'>',lambda e,k=key:self._key(k))
        self.bind('<Destroy>',self._destroy,add='+')

    def _destroy(self,event):
        if event.widget is self:
            for job in (self._layout_job,self._paint_job):
                if job is not None:
                    try:self.after_cancel(job)
                    except tk.TclError:pass

    def cancel_layout(self):
        self._revision+=1;self._layout_epoch+=1
        if self._layout_job is not None:self.after_cancel(self._layout_job);self._layout_job=None
        self._pending_see=None

    def begin_batch(self):
        self.cancel_layout();self._defer_layout=True

    def end_batch(self,commit=True):
        self._defer_layout=False
        if commit:self._invalidate()
        else:self.cancel_layout()

    def _geometry_changed(self,event):
        # Row wrapping depends on width, not viewport height. Busy controls or
        # status text changing height must not start another layout operation.
        if event.width!=self._viewport_width:
            self._viewport_width=event.width;self._invalidate()
        else:self._clamp();self._schedule_paint()

    def _columns_changed(self):
        widths=tuple(self.column(c,'width') for c in ('#0','value','type'))
        if widths!=getattr(self,'_layout_widths',None):self._invalidate()

    def configure(self,cnf=None,**kw):
        if 'yscrollcommand' in kw:self._yscroll=kw.pop('yscrollcommand')
        if 'xscrollcommand' in kw:self._xscroll=kw.pop('xscrollcommand')
        return super().configure(cnf,**kw)
    config=configure

    def column(self,column,option=None,**kw):
        result=super().column(column,option,**kw)
        if kw and hasattr(self,'_revision'):self._invalidate()
        return result

    def insert(self,parent,index,iid=None,**kw):
        text=kw.get('text','');values=tuple(kw.get('values',()))
        native=dict(kw,text=text[:500],values=tuple(str(v)[:500] for v in values))
        iid=super().insert(parent,index,iid,**native)
        self._display[iid]=(text,values);self._invalidate();return iid

    def item(self,item,option=None,**kw):
        if kw:
            text,values=self._display.get(item,('',()))
            self._display[item]=(kw.get('text',text),tuple(kw.get('values',values)))
            native=dict(kw)
            if 'text' in native:native['text']=str(native['text'])[:500]
            if 'values' in native:native['values']=tuple(str(v)[:500] for v in native['values'])
            result=super().item(item,option,**native);self._invalidate();return result
        result=super().item(item,option)
        text,values=self._display.get(item,('',()))
        if option=='text':return text
        if option=='values':return values
        if option is None:result.update(text=text,values=values)
        return result

    def delete(self,*items):
        pending=list(items)
        while pending:
            iid=pending.pop();pending.extend(self.get_children(iid))
            self._display.pop(iid,None);self._layouts.pop(iid,None);self._match.pop(iid,None)
        super().delete(*items);self._invalidate()

    def selection_set(self,*items):
        super().selection_set(*items);self._schedule_paint()
    def selection_remove(self,*items):
        super().selection_remove(*items);self._schedule_paint()

    def _invalidate(self):
        self._revision+=1
        if not self._defer_layout and self._layout_job is None:self._layout_job=self.after_idle(self._layout)

    @staticmethod
    def _line_chunks(text,width,font):
        for paragraph in text.replace('\r\n','\n').replace('\r','\n').split('\n'):
            start=0
            while start<len(paragraph):
                # Never repeatedly measure an entire pathological long scalar.
                remaining=len(paragraph)-start
                low,high=1,min(remaining,max(64,width*2))
                while low<high:
                    mid=(low+high+1)//2
                    if font.measure(paragraph[start:start+mid])<=width:low=mid
                    else:high=mid-1
                if low==remaining:break
                cut=max(1,low);space=paragraph.rfind(' ',start,start+cut)-start
                if space>cut//2:cut=space+1
                yield paragraph[start:start+cut];start+=cut
            yield paragraph[start:]

    @staticmethod
    def _lines(text,width,font):return list(WrappedTreeview._line_chunks(text,width,font))

    def _layout(self):
        self._layout_job=None;revision=self._revision;epoch=self._layout_epoch
        font=tkfont.nametofont('TkDefaultFont');line=font.metrics('linespace')
        self._indent=max(18,round(line*.9))
        widths=[self.column(c,'width') for c in ('#0','value','type')]
        self._layout_widths=tuple(widths)
        # Header height follows the actual themed heading font, not a fixed row.
        heading=ttk.Style(self).lookup('Treeview.Heading','font') or 'TkDefaultFont'
        top=tkfont.Font(self,font=heading).metrics('linespace')+10
        top=next((y for y in range(1,top+20) if self.identify_region(10,y) in ('tree','cell')),top)
        self._body.place_configure(y=top,height=-top-1)
        anchor=None
        if self._entries:
            index=min(bisect_right(self._ends,self._offset),len(self._entries)-1)
            old=self._entries[index];anchor=(old[0],self._offset-old[2])
        rows=[];stack=[(iid,0) for iid in reversed(self.get_children())]
        while stack:
            iid,depth=stack.pop();rows.append((iid,depth))
            if super().item(iid,'open'):stack.extend((child,depth+1) for child in reversed(self.get_children(iid)))
        entries=[];ends=[];y=0;cache={}
        signature=(tuple(widths),font.actual('family'),font.actual('size'),font.actual('weight'))
        def layout_rows():
            for iid,depth in rows:
                text,values=self._display[iid];raw=(text,)+values
                key=(signature,depth,raw);saved=self._layouts.get(iid)
                if saved and saved[0]==key:wrapped=saved[1]
                else:
                    wrapped=[]
                    for col,(value,width) in enumerate(zip(raw,widths)):
                        width=max(20,width-12-min((depth+1)*self._indent,max(0,width-36)) if col==0 else width-12)
                        lines=[]
                        for chunk in self._line_chunks(str(value),width,font):
                            lines.append(chunk);yield None
                        wrapped.append(lines)
                yield iid,depth,key,wrapped
        iterator=layout_rows()
        def batch():
            nonlocal y
            if epoch!=self._layout_epoch:return
            self._layout_job=None
            if revision!=self._revision:
                self._layout_job=self.after_idle(self._layout);return
            start=time.monotonic();count=0
            while count<100 and time.monotonic()-start<.008:
                try:row=next(iterator)
                except StopIteration:break
                count+=1
                if row is None:continue
                iid,depth,key,wrapped=row
                cache[iid]=(key,wrapped)
                height=max(line+8,max(map(len,wrapped),default=1)*line+8)
                entries.append((iid,depth,y,height,wrapped));y+=height;ends.append(y)
            else:
                self._layout_job=self.after(1,batch);return
            if epoch!=self._layout_epoch:return
            self._entries=entries;self._ends=ends;self._layouts=cache;self._total=max(1,y);self._extent=sum(widths)
            if anchor:
                found=next((r for r in entries if r[0]==anchor[0]),None)
                if found:self._offset=found[2]+anchor[1]
            self._clamp();self._paint()
            if self._pending_see:
                iid=self._pending_see;self._pending_see=None;self.see(iid)
            if self._layout_finished:
                callback=self._layout_finished;self._layout_finished=None;callback()
        batch()

    def _clamp(self):
        self._offset=max(0,min(self._offset,max(0,self._total-self._body.winfo_height())))
        self._left=max(0,min(self._left,max(0,self._extent-self._body.winfo_width())))

    def _schedule_paint(self):
        if self._paint_job is None:self._paint_job=self.after_idle(self._paint)

    def _paint(self):
        self._paint_job=None;body=self._body;body.delete('all')
        style=ttk.Style(self);bg=style.lookup('Treeview','background') or '#ffffff'
        fg=style.lookup('Treeview','foreground') or '#202020'
        selected_bg=style.lookup('Treeview','background',('selected',)) or '#0078d7'
        selected_fg=style.lookup('Treeview','foreground',('selected',)) or '#ffffff'
        body.configure(background=bg);font=tkfont.nametofont('TkDefaultFont');line=font.metrics('linespace')
        selected=set(self.selection());widths=[self.column(c,'width') for c in ('#0','value','type')]
        self._left=super().xview()[0]*max(1,sum(widths))
        start=bisect_right(self._ends,self._offset)
        for iid,depth,y,height,wrapped in self._entries[start:]:
            if y-self._offset>body.winfo_height():break
            if not self.exists(iid):continue
            top=y-self._offset;color=selected_fg if iid in selected else fg
            if iid in selected:body.create_rectangle(0,top,max(body.winfo_width(),self._extent),top+height,fill=selected_bg,outline='')
            x=-self._left
            for column,(width,lines) in enumerate(zip(widths,wrapped)):
                indent=min((depth+1)*self._indent,max(0,width-36)) if column==0 else 0
                first=max(0,int((-top-4)//line));last=min(len(lines),int((body.winfo_height()-top)//line)+1)
                if last>first:body.create_text(x+6+indent,top+4+first*line,text='\n'.join(lines[first:last]),anchor='nw',font=font,fill=color)
                x+=width
            if self.get_children(iid):
                x=min(depth*self._indent+8,max(8,widths[0]-28))-self._left;cy=top+4+line/2
                radius=max(3,round(line*.15))
                points=(x-radius,cy-radius,x+radius,cy-radius,x,cy+radius) if super().item(iid,'open') else (x-radius,cy-radius,x-radius,cy+radius,x+radius,cy)
                body.create_polygon(*points,fill=color)
        if self._yscroll:self._yscroll(self._offset/self._total,min(1,(self._offset+body.winfo_height())/self._total))
        if self._xscroll:self._xscroll(self._left/self._extent,min(1,(self._left+body.winfo_width())/self._extent))

    def identify_row(self,y):
        value=y-self._body.winfo_y()+self._offset;index=bisect_right(self._ends,value)
        return self._entries[index][0] if value>=0 and index<len(self._entries) else ''

    def _click(self,event):
        self.focus_set();iid=self.identify_row(event.y+self._body.winfo_y())
        if not iid:return 'break'
        entry=next(r for r in self._entries if r[0]==iid)
        arrow=min(entry[1]*self._indent+8,max(8,self.column('#0','width')-28))
        if self.get_children(iid) and abs(event.x+self._left-arrow)<max(9,self._indent/2):self.item(iid,open=not super().item(iid,'open'))
        self.selection_set(iid);self.focus(iid);return 'break'

    def _forward(self,event,sequence):
        if sequence=='<Double-1>':
            iid=self.identify_row(event.y+self._body.winfo_y())
            if iid and self.get_children(iid):self.item(iid,open=not super().item(iid,'open'));return 'break'
            self.event_generate('<Return>');return 'break'
        self.event_generate(sequence,x=event.x,y=event.y+self._body.winfo_y());return 'break'

    def _key(self,key):
        if key in ('Prior','Next'):
            self.yview_scroll(-1 if key=='Prior' else 1,'pages');return 'break'
        ids=[r[0] for r in self._entries]
        if not ids:return 'break'
        current=self.focus();index=ids.index(current) if current in ids else 0
        if key in ('Left','Right'):
            if key=='Right':self.item(ids[index],open=True)
            elif self.item(ids[index],'open'):self.item(ids[index],open=False)
            elif self.parent(ids[index]):self.selection_set(self.parent(ids[index]));self.focus(self.parent(ids[index]));self.see(self.parent(ids[index]))
        else:
            delta={'Up':-1,'Down':1,'Home':-len(ids),'End':len(ids)}[key]
            index=max(0,min(len(ids)-1,index+delta));self.selection_set(ids[index]);self.focus(ids[index]);self.see(ids[index])
        return 'break'

    def _wheel(self,event):
        self.yview_scroll(-int(event.delta/120) if abs(event.delta)>=120 else (-1 if event.delta>0 else 1),'units');return 'break'

    def yview(self,*args):
        if not args:return self._offset/self._total,min(1,(self._offset+self._body.winfo_height())/self._total)
        if args[0]=='moveto':self._offset=float(args[1])*self._total
        else:self._offset+=int(args[1])*(self._body.winfo_height()*.9 if args[2]=='pages' else tkfont.nametofont('TkDefaultFont').metrics('linespace')+8)
        self._clamp();self._schedule_paint()
    def yview_moveto(self,fraction):self.yview('moveto',fraction)
    def yview_scroll(self,number,what):self.yview('scroll',number,what)

    def xview(self,*args):
        if not args:return self._left/self._extent,min(1,(self._left+self._body.winfo_width())/self._extent)
        super().xview(*args)
        self._left=super().xview()[0]*self._extent;self._clamp();self._schedule_paint()
    def xview_moveto(self,fraction):self.xview('moveto',fraction)
    def xview_scroll(self,number,what):self.xview('scroll',number,what)

    def see(self,iid):
        if self._layout_job is not None:self._pending_see=iid;return
        entry=next((r for r in self._entries if r[0]==iid),None)
        if entry:
            top=entry[2];bottom=top+entry[3];height=self._body.winfo_height()
            match=self._match.get(iid)
            if match and match[0] in ('label','value'):
                column=0 if match[0]=='label' else 1
                raw=self._display[iid][0] if column==0 else self._display[iid][1][0]
                position=0;line=0;raw=raw.replace('\r\n','\n').replace('\r','\n')
                for part in entry[4][column]:
                    if position+len(part)>match[1]:break
                    position+=len(part)
                    if raw[position:position+1]=='\n':position+=1
                    line+=1
                font=tkfont.nametofont('TkDefaultFont')
                top+=line*font.metrics('linespace');bottom=top+font.metrics('linespace')+8
            if top<self._offset:self._offset=top
            elif bottom>self._offset+height:self._offset=top if bottom-top>height else bottom-height
            self._clamp();self._schedule_paint()

    def bbox(self,iid,column=None):
        entry=next((r for r in self._entries if r[0]==iid),None)
        if not entry:return ''
        y=entry[2]-self._offset+self._body.winfo_y();widths=[self.column(c,'width') for c in ('#0','value','type')]
        if column is None:return (-self._left,y,sum(widths),entry[3])
        index=('#0','value','type').index(column)
        return (sum(widths[:index])-self._left,y,widths[index],entry[3])
