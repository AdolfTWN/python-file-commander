"""Side-effect-free Settings samples. Never read files or invoke an operation."""
from datetime import datetime
from pathlib import PurePath
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .columnsettings import font_snapshot, modified_text
from .fileops import compact_file_size
from .homeprefix import PREFIX_ICONS, prefix_icon_png
from .i18n import tr, tr_for_language
from .icons import cloud_badge_png, folder_nav_icon_png, vcs_badge_png
from .tabs import color_scheme


def column_sample_rows(values):
    """The same display formatters as the file list, with fixed synthetic data."""
    samples = [('Projects', True, 0, ''), ('Notes.md', False, 1536, ''),
               ('Archive.zip', False, 2*1024**3, ''), ('Backup.zip', False, 3*1024**4, ''),
               ('.draft.md', False, 1024, 'hidden'), ('desktop.ini', False, 256, 'system')]
    stamp = datetime(2026, 9, 22, 17, 15).timestamp()
    rows = []
    for name, folder, size, visibility in samples:
        if visibility and not values['show_' + visibility]:
            continue
        suffix = PurePath(name).suffix
        shown = name if folder or values['show_extensions'] else PurePath(name).stem
        rows.append(dict(name=shown, folder=folder, ext='' if folder else suffix[1:].upper(),
                         size='<DIR>' if folder else compact_file_size(size),
                         modified=modified_text(stamp, values['date_order'], values['time_style']),
                         visibility=visibility))
    rows.sort(key=lambda row: (not row['folder'] if not values['mix_sorting'] else False,
                               row['name'].casefold()))
    return rows


class SettingsSamplePreview(ttk.Frame):
    """Fixed top preview; redraw only when the draft or actual width changes."""
    def __init__(self, parent, category, font):
        super().__init__(parent)
        self.category = category
        self.font = tkfont.Font(self, **font_snapshot(font))
        self.bold = tkfont.Font(self, **font_snapshot(font, weight='bold'))
        self.line = max(23, self.font.metrics('linespace') + 5)
        self.title = ttk.Label(self, text=tr('Preview · After Apply'), style='PrefsTitle.TLabel')
        self.title.pack(anchor='w')
        self.caption = ttk.Label(self, style='Prefs.TLabel', wraplength=480)
        self.caption.pack(fill='x', pady=(2,5))
        self.canvas = tk.Canvas(self, height=8*self.line, highlightthickness=1, takefocus=False)
        self.canvas.pack(fill='x')
        self.values = {}; self.prefixes = []; self.images = {}; self._key = None; self._job = None
        self.canvas.bind('<Configure>', self._schedule)

    def update_sample(self, values, prefixes):
        self.values = dict(values)
        self.prefixes = [dict(item) for item in prefixes]
        self._draw()

    def _schedule(self, _event=None):
        if self._job is None:
            self._job = self.after_idle(self._draw)

    def destroy(self):
        if self._job is not None:
            self.after_cancel(self._job); self._job = None
        super().destroy()
        # Tk image/font finalizers must run on the UI thread, not later when a
        # filesystem worker happens to trigger cyclic garbage collection.
        self.images.clear()
        self.font = self.bold = None

    def _draw(self):
        if self._job is not None:
            self.after_cancel(self._job); self._job = None
        if not self.values:
            return
        width = max(200, self.canvas.winfo_width())
        key = (width, tuple(self.values.items()), tuple(tuple(p.items()) for p in self.prefixes))
        if key == self._key:
            return
        self._key = key
        self.canvas.delete('all')
        self.palette = color_scheme(self.values['color_scheme'])
        self.canvas.configure(bg=self.palette['surface'], highlightbackground=self.palette['border'])
        self.caption.configure(wraplength=max(180,width-4))
        getattr(self, '_draw_' + self.category)(width)

    def _text(self, x, y, text, width, *, bold=False, color=None, anchor='w', tag='sample'):
        font = self.bold if bold else self.font
        shown = str(text)
        if font.measure(shown) > width:
            while shown and font.measure(shown + '…') > width:
                shown = shown[:-1]
            shown += '…'
        return self.canvas.create_text(x, y, text=shown, anchor=anchor, font=font,
                    fill=color or self.palette['text'], tags=(tag,))

    def _image(self, key, data, x, y):
        if key not in self.images:
            self.images[key] = tk.PhotoImage(master=self, data=data, format='png')
        self.canvas.create_image(x,y,image=self.images[key],anchor='w')

    def _draw_columns(self, width):
        v, p, c, line = self.values, self.palette, self.canvas, self.line
        self.caption.configure(text=tr('Demo files only. Column, date and status changes appear here immediately.'))
        self.rows = column_sample_rows(v)
        right = width-8
        columns = []
        date_width=max(self.font.measure(self.rows[0]['modified']),self.bold.measure(tr('Date Modified')))+16
        for key, label, space in (('modified','Date Modified', date_width),
                                  ('size','Size', max(66,self.font.measure(tr('Size'))+16)),
                                  ('ext','Ext',max(43,self.font.measure(tr('Ext'))+16))):
            if v['column_' + key]:
                columns.append((key,label,right-space,right)); right -= space
        columns.append(('name','Name',4,right))
        c.create_rectangle(0,0,width,line,fill=p['surface_alt'],outline='')
        for key,label,x1,x2 in columns:
            c.create_line(x1,0,x1,7*line,fill=p['border'])
            self._text(x1+6,line/2,tr(label),x2-x1-12,bold=True,tag='heading-'+key)
        for i,row in enumerate(self.rows):
            y=(i+1.5)*line
            for key,_label,x1,x2 in columns:
                if key=='name':
                    if row['folder']:
                        self._image('folder',folder_nav_icon_png('folder',18),x1+6,y)
                    else:
                        c.create_rectangle(x1+8,y-8,x1+20,y+8,fill=p['surface_alt'],outline=p['border'])
                    if v['onedrive_overlay'] and row['name'].startswith('Notes'):
                        self._image('online',cloud_badge_png(13,'online'),x1+14,y+4)
                    if v['vcs_overlay'] and row['folder']:
                        self._image('modified',vcs_badge_png(13,'modified'),x1+14,y+4)
                    self._text(x1+32,y,row['name'],x2-x1-38,
                               color=p['muted'] if row['visibility'] else p['text'],tag='filename')
                elif key=='size':
                    amount, _, unit = row['size'].rpartition(' ')
                    strong = v['size_emphasis'] and unit in ('GB','TB')
                    if strong:
                        color = ('#ffb4a9' if v['color_scheme']=='dark' else '#b00020') if unit=='TB' else p['text']
                        self._text(x2-6,y,unit,x2-x1-12,bold=True,color=color,anchor='e',tag='size-unit')
                        self._text(x2-6-self.bold.measure(unit+' '),y,amount,30,anchor='e')
                    else:self._text(x2-6,y,row[key],x2-x1-12,anchor='e')
                else:self._text(x2-6,y,row[key],x2-x1-12,anchor='e',tag=key)
        self._text(8,7.5*line,tr('Long names: scroll on hover') if v['long_name_scrolling'] else tr('Long names: static'),
                   width-16,color=p['muted'],tag='long-names')

    def _draw_navigation(self, width):
        v,p,c,line=self.values,self.palette,self.canvas,self.line
        self.caption.configure(text=tr('Behavior illustration only; no menu, deletion or folder access is executed.'))
        split=max(155,min(210,width*.32))
        c.create_rectangle(6,6,split-8,4*line,fill=p['menu'],outline=p['border'])
        self._text(14,.7*line,tr('File Explorer') if v['right_click_menu']=='explorer' else 'PFC',split-30,bold=True)
        commands=('Open','Copy','Properties') if v['right_click_menu']=='explorer' else ('Preview','Copy','Compare')
        for i,text in enumerate(commands):self._text(14,(i+1.55)*line,tr(text),split-30)
        self._text(split+6,.65*line,'Delete → '+tr('Recycle Bin' if v['recycle_bin'] else 'Permanent delete'),
                   width-split-18,bold=True,color=p['text'] if v['recycle_bin'] else
                   '#ffb4a9' if v['color_scheme']=='dark' else '#b00020',tag='delete-policy')
        self._text(split+6,1.65*line,tr('Shift+Delete: always permanent'),width-split-18)
        self._text(split+6,2.65*line,tr('On error: continue remaining files' if v['continue_errors'] else 'On error: stop'),width-split-18,tag='error-policy')
        self._text(8,4.6*line,tr('Prefix examples · sample child “Docs”'),width-16,bold=True)
        for i,item in enumerate(self.prefixes):
            y=(5.5+i)*line
            kind=item['icon']; path=item['path'].strip().strip('"')
            self._image('prefix-'+kind,prefix_icon_png(kind,20),8,y)
            name=tr(PREFIX_ICONS[kind])
            text=f'{i+1}. {name} — {path}' if path else f'{i+1}. {name} — '+tr('Not set')
            tail=' → Docs' if path else ''
            tail_width=self.bold.measure(tail)+2 if tail else 0
            self._text(36,y,text,width-44-tail_width,tag='prefix-sample')
            if tail:self._text(width-8,y,tail,tail_width,anchor='e',bold=True,tag='prefix-sample')

    def _draw_preview(self, width):
        v,p,c,line=self.values,self.palette,self.canvas,self.line
        enabled=v['extension_effect']
        self.caption.configure(text=tr('Notes.md · formatted Markdown sample' if enabled else 'Notes.md · plain source sample'))
        if not enabled:
            lines=['# Notes', '', '| Task | Status |', '| --- | --- |', '| Review | Done |', '', '**Ready** to share.']
            for i,text in enumerate(lines):self._text(12,(i+.65)*line,text,width-24,tag='markdown-source')
            return
        self._text(12,.8*line,'Notes',width-24,bold=True,tag='markdown-heading')
        c.create_line(12,1.5*line,width-12,1.5*line,fill=p['border'])
        table_right=min(width-12,480);mid=(12+table_right)/2
        c.create_rectangle(12,2*line,table_right,4*line,outline=p['border'])
        c.create_rectangle(13,2*line+1,table_right-1,3*line,fill=p['surface_alt'],outline='')
        c.create_line(mid,2*line,mid,4*line,fill=p['border'])
        c.create_line(12,3*line,table_right,3*line,fill=p['border'])
        for x,y,text,strong in ((20,2.5,'Task',True),(mid+8,2.5,'Status',True),
                                (20,3.5,'Review',False),(mid+8,3.5,'Done',False)):
            self._text(x,y*line,text,mid-28,bold=strong,tag='markdown-table')
        self._text(12,5*line,'Ready',70,bold=True)
        self._text(16+self.bold.measure('Ready'),5*line,'to share.',width-100)
        self._text(12,7*line,tr('Headings, tables and emphasis; original file stays unchanged.'),width-24,color=p['muted'])

    def _draw_general(self, width):
        v,p,c,line=self.values,self.palette,self.canvas,self.line
        language=v['ui_language']
        t=lambda text:tr_for_language(language,text)
        self.caption.configure(text=tr('Sample interface language and sign-in behavior; applies only after Apply.'))
        c.create_rectangle(0,0,width,1.7*line,fill=p['header'],outline='')
        x=12
        for text in ('Files','Go','View','Tools','Help'):
            label=t(text);space=self.font.measure(label)+26
            self._text(x,.85*line,label,space-10,color=p['header_text'],tag='language-menu');x+=space
        self._text(12,2.6*line,t('Name')+'    Notes.md',width-24,bold=True,tag='language-name')
        x=12
        for text in ('Apply','Cancel','OK'):
            label=t(text);space=max(65,self.font.measure(label)+24)
            c.create_rectangle(x,3.4*line,x+space,4.6*line,fill=p['button'],outline=p['border'])
            self._text(x+space/2,4*line,label,space-12,anchor='center',tag='language-button');x+=space+8
        self._text(12,5.6*line,tr('Windows sign-in')+' → '+tr('PFC opens automatically' if v['auto_start'] else 'Open PFC manually'),
                   width-24,bold=True,tag='startup-flow')
        self._text(12,7*line,tr('File names are unchanged; startup is Windows only.'),width-24,color=p['muted'])
