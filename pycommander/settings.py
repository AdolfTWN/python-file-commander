"""Categorized, draft-first preferences. No filesystem scanning or network preview."""
import os
import math
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from functools import lru_cache

from .i18n import tr, LANGUAGES
from .tabs import TAB_STYLES, color_scheme
from .columnsettings import modified_text
from .homeprefix import PREFIX_ICONS, prefix_icon
from .settingsshots import SETTINGS_SHOTS
from .settingspreview import SettingsSamplePreview, SettingsLayoutPreview
from .icons import _distance_to_segment, _hex_rgba, _rgba_png_downsample


SETTINGS_CATEGORIES = (
    ('appearance', 'Appearance'), ('layout', 'Layout & Tabs'),
    ('columns', 'File Columns'), ('navigation', 'Paths & Operations'),
    ('preview', 'Preview'), ('general', 'General'),
)


@lru_cache(maxsize=48)
def settings_check_icon_png(size, selected, disabled, dark):
    """A crisp tick (never the Clam theme's X), independent of installed fonts."""
    supersample=4;extent=size*supersample;unit=extent/20
    pixels=bytearray(extent*extent*4)
    if disabled:
        edge,face,ink=('#657380','#394550','#a3afba') if dark else ('#aeb8c2','#e2e6ea','#657380')
    elif selected:
        edge,face,ink=('#8bc8ff','#8bc8ff','#153449') if dark else ('#176fbc','#176fbc','#ffffff')
    else:
        edge,face,ink=('#a9bbc9','#252d35','#ffffff') if dark else ('#5b6c7b','#ffffff','#153449')
    edge,face,ink=map(_hex_rgba,(edge,face,ink))
    def rounded(x,y,lo,hi,r):
        cx=max(lo+r,min(x,hi-r));cy=max(lo+r,min(y,hi-r))
        return (x-cx)**2+(y-cy)**2<=r*r
    for y in range(extent):
        py=(y+.5)/unit
        for x in range(extent):
            px=(x+.5)/unit
            if not rounded(px,py,1,19,2.3):continue
            color=face if rounded(px,py,2.2,17.8,1.2) else edge
            if selected and min(_distance_to_segment(px,py,5,10,8.5,13.5),
                                _distance_to_segment(px,py,8.5,13.5,15,6.5))<=1.15:
                color=ink
            start=(y*extent+x)*4;pixels[start:start+4]=bytes(color)
    return _rgba_png_downsample(pixels,size,supersample)


def preference_specs(app):
    """key, category, group, label, choices (None = check), apply method."""
    return [
        ('color_scheme', 'appearance', 'Color Scheme', 'Color Scheme',
         [('light', 'Light'), ('light_grey', 'Light Grey'), ('dark', 'Dark')], 'apply_color_scheme'),
        ('auto_font_size', 'appearance', 'Font Size', 'Auto Font Size', None, 'set_auto_font_size'),
        ('font_size', 'appearance', 'Font Size', 'Font Size',
         [(k, f'{round(v*100)}%') for k, v in app._font_scales.items()], 'apply_font_size'),
        ('panel_count', 'layout', 'Panel Counts', 'Panel Counts',
         [(1, '1 Panel')] + [(n, tr('{count} Panels', count=n)) for n in range(2,5)], 'apply_panel_count'),
        ('tab_style', 'layout', 'Tab Style', 'Tab Style', list(TAB_STYLES.items()), 'apply_tab_style'),
        ('show_hidden', 'columns', 'Name · current tab', 'Show Hidden', None, 'set_hidden_visibility'),
        ('show_system', 'columns', 'Name · current tab', 'Show System', None, 'set_system_visibility'),
        ('show_extensions', 'columns', 'Name · current tab', 'Show File Extension', None, 'set_extension_visibility'),
        ('mix_sorting', 'columns', 'Name · all tabs', 'File/Folder Mix Sorting', None, 'set_mix_sorting'),
        ('long_name_scrolling', 'columns', 'Name · all tabs', 'Long Filename Scrolling', None, 'set_long_name_scrolling'),
        ('onedrive_overlay', 'columns', 'Status icons', 'OneDrive Sync Overlay', None, 'apply_column_settings'),
        ('vcs_overlay', 'columns', 'Status icons', 'Git / SVN Overlay', None, 'set_vcs_overlay'),
        ('column_ext', 'columns', 'Ext', 'Show Ext column', None, 'apply_column_settings'),
        ('column_size', 'columns', 'Size', 'Show Size column', None, 'apply_column_settings'),
        ('size_emphasis', 'columns', 'Size', 'Emphasize GB / TB', None, 'apply_column_settings'),
        ('column_modified', 'columns', 'Date Modified', 'Show Date Modified column', None, 'apply_column_settings'),
        ('date_order', 'columns', 'Date Modified', 'Date format', [('ymd','YYYY/MM/DD'), ('mdy','MM/DD/YYYY')], 'apply_column_settings'),
        ('time_style', 'columns', 'Date Modified', 'Time format',
         [('24','24-hour (hh:mm)'), ('12','12-hour (1136a / 0515p)'), ('none','Date only')], 'apply_column_settings'),
        ('right_click_menu', 'navigation', 'Right Click Menu', 'Right Click Menu',
         [('explorer','File Explorer'), ('pfc','PFC')], 'save_config'),
        ('recycle_bin', 'navigation', 'File Operation Settings', 'Send Delete to Recycle Bin', None, 'save_config'),
        ('continue_errors', 'navigation', 'File Operation Settings', 'Continue After File Errors', None, 'save_config'),
        ('extension_effect', 'preview', 'F3 Preview', 'Syntax colors & Markdown (Extension Effect)', None, 'set_extension_effect'),
        ('ui_language', 'general', 'UI Language', 'UI Language', list(LANGUAGES), 'apply_ui_language'),
        ('auto_start', 'general', 'Windows startup', 'Auto Start when boot', None, 'toggle_auto_start'),
    ]


class SettingsDialog(tk.Toplevel):
    def __init__(self, app, category='appearance'):
        super().__init__(app)
        self.withdraw()
        self.app = app
        self.pane = app.active
        self.title(tr('PFC Settings'))
        self.transient(app)
        # Independent pixel fonts keep Apply from moving controls under the mouse.
        # The content area scrolls; the footer never scrolls out of reach.
        base = tkfont.nametofont('TkDefaultFont')
        self.font = tkfont.Font(self, family=base.actual('family'),
                                size=-max(14, min(18, round(app._base_tk_scaling*11))))
        self.heading_font = tkfont.Font(self, **dict(self.font.actual(), size=self.font.cget('size'), weight='bold'))
        self.small_font = tkfont.Font(self, **dict(self.font.actual(), size=self.font.cget('size')))
        self.specs = preference_specs(app)
        self.vars, self.original = {}, {}
        for key, _cat, _group, _label, choices, _method in self.specs:
            value = self._read(key)
            self.original[key] = value
            cls = tk.BooleanVar if choices is None else tk.IntVar if isinstance(value,int) else tk.StringVar
            self.vars[key] = cls(self, value=value)
            self.vars[key].trace_add('write', self._changed)
        self.prefix_original = [dict(item) for item in app.custom_home_prefixes]
        self.prefix_draft = [dict(item) for item in self.prefix_original]
        self.category = category if category in dict(SETTINGS_CATEGORIES) else 'appearance'
        self.controls = {}
        self.images = []
        self.status_var = tk.StringVar(self)
        self._shot_sources = {}
        self._shot_job = None
        self._build()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        width, height = min(1180, sw-48), min(720, sh-80)
        self.geometry(f'{width}x{height}+{max(0,min(app.winfo_rootx()+30,sw-width-24))}+{max(0,min(app.winfo_rooty()+30,sh-height-40))}')
        self.minsize(min(720,width), min(560,height))
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.bind('<Escape>', lambda _e: self.cancel())
        # Stop application-wide file shortcuts from acting behind the modal dialog.
        self.bind('<KeyPress>', self._key_event, add='+')
        self.bind('<Control-Return>', lambda _e: self.apply(close=True))
        self.bind('<Control-MouseWheel>', lambda _e: 'break')
        self.bind('<Control-Button-4>', lambda _e: 'break')
        self.bind('<Control-Button-5>', lambda _e: 'break')
        self.bind('<MouseWheel>', self._wheel)
        self.bind('<Button-4>', lambda _e: self._scroll(-3))
        self.bind('<Button-5>', lambda _e: self._scroll(3))
        self.bind('<FocusIn>', self._reveal_focus, add='+')
        self.deiconify()
        self.grab_set()
        self.nav.focus_set()

    def _read(self, key):
        if key in ('show_hidden','show_system','show_extensions'):
            return getattr(self.pane, key)
        if key.startswith('column_'):
            return self.app.column_visible_vars[key[7:]].get()
        return getattr(self.app, key+'_var').get()

    def _build(self):
        p = self.app.palette
        self.configure(bg=p['window'])
        style = ttk.Style(self)
        for suffix in ('TButton','TCheckbutton','TLabel','TCombobox','TEntry'):
            style.configure('Prefs.'+suffix, font=self.font)
        self._checkbutton_style(style)
        style.configure('PrefsTitle.TLabel', font=self.heading_font)
        self.footer = ttk.Frame(self, padding=12)
        self.footer.pack(side='bottom', fill='x')
        ttk.Button(self.footer, text=tr('OK'), style='Prefs.TButton', width=9,
                   command=lambda:self.apply(close=True)).pack(side='right')
        ttk.Button(self.footer, text=tr('Cancel'), style='Prefs.TButton', width=9,
                   command=self.cancel).pack(side='right', padx=6)
        self.apply_button = ttk.Button(self.footer, text=tr('Apply'), style='Prefs.TButton', width=9, command=self.apply)
        self.apply_button.pack(side='right')
        self.status_label = ttk.Label(self.footer, textvariable=self.status_var, style='Prefs.TLabel')
        self.status_label.pack(side='left', fill='x', expand=True)
        body = ttk.Frame(self, padding=(12,12,12,0)); body.pack(fill='both', expand=True)
        self.nav = tk.Listbox(body, font=self.font, width=18, exportselection=False,
                              activestyle='none', relief='flat', borderwidth=0,
                              highlightthickness=1, background=p['surface_alt'], foreground=p['text'],
                              selectbackground=p['selection'], selectforeground='#ffffff',
                              selectmode='browse')
        self.nav.pack(side='left', fill='y', padx=(0,14))
        for _key, label in SETTINGS_CATEGORIES: self.nav.insert('end', tr(label))
        self.nav.bind('<<ListboxSelect>>', self._select)
        right = ttk.Frame(body); right.pack(fill='both', expand=True)
        self.title_label = ttk.Label(right, style='PrefsTitle.TLabel'); self.title_label.pack(anchor='w', pady=(0,6))
        self.intro = ttk.Label(right, text=tr('Changes take effect only after Apply or OK.'), style='Prefs.TLabel', wraplength=500)
        self.intro.pack(anchor='w', pady=(0,12))
        # Comparison stays in view while only the preference controls scroll.
        self.comparison = ttk.Frame(right)
        self.comparison.pack(fill='x', pady=(0,8))
        self.comparison.bind('<Configure>', lambda _e:self._schedule_shots())
        content = ttk.Frame(right); content.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(content, highlightthickness=0, bg=p['window'])
        self.scrollbar = ttk.Scrollbar(content, orient='vertical', command=self.canvas.yview)
        self.scrollbar.pack(side='right', fill='y'); self.canvas.pack(fill='both', expand=True)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.page = ttk.Frame(self.canvas, padding=(2,0,12,10))
        self.page_id = self.canvas.create_window(0,0,window=self.page,anchor='nw')
        self.page.bind('<Configure>', lambda _e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', self._resize)
        index = [key for key,_label in SETTINGS_CATEGORIES].index(self.category)
        self.nav.selection_set(index); self.nav.activate(index)
        self.show_page(self.category)

    def _checkbutton_style(self, style):
        # Ttk elements retain image names after the dialog closes. Own these four
        # images on the application, reuse them on Apply/reopen, and keep the
        # native checkbutton's focus, mouse and Space-key behavior intact.
        images=getattr(self.app,'_settings_check_images',None)
        if images is None:
            images={state:tk.PhotoImage(master=self.app) for state in
                    ((False,False),(True,False),(False,True),(True,True))}
            self.app._settings_check_images=images
        size=max(18,min(24,self.font.metrics('linespace')))
        dark=self.app.color_scheme_var.get()=='dark'
        for (selected,disabled),image in images.items():
            image.configure(data=settings_check_icon_png(size,selected,disabled,dark),format='png')
        name='Prefs.Checkbutton.indicator'
        if name not in style.element_names():
            style.element_create(name,'image',images[False,False],
                ('disabled','selected',images[True,True]),
                ('disabled','!selected',images[False,True]),
                ('selected',images[True,False]),width=size+7,sticky='w')
        def replace(layout):
            return [(name if element=='Checkbutton.indicator' else element,
                     {key:replace(value) if key=='children' else value for key,value in options.items()})
                    for element,options in layout]
        style.layout('Prefs.TCheckbutton',replace(style.layout('TCheckbutton')))

    def _resize(self, event):
        self.canvas.itemconfigure(self.page_id,width=event.width)
        self.intro.configure(wraplength=max(100,event.width-12))
        for label in getattr(self,'wrap_labels',[]):
            label.configure(wraplength=max(140,event.width-36))
        self._schedule_shots()

    def _select(self, _event=None):
        selection=self.nav.curselection()
        if selection:self.show_page(SETTINGS_CATEGORIES[selection[0]][0])

    def _label(self, parent, text, heading=False):
        label=ttk.Label(parent,text=tr(text),style='PrefsTitle.TLabel' if heading else 'Prefs.TLabel',wraplength=480)
        label.pack(anchor='w',fill='x',pady=(8 if heading else 2,6))
        self.wrap_labels.append(label)
        return label

    def show_page(self, category):
        self.category=category
        index=[key for key,_label in SETTINGS_CATEGORIES].index(category)
        if self.nav.curselection()!=(index,):
            self.nav.selection_clear(0,'end');self.nav.selection_set(index);self.nav.activate(index)
        for child in self.page.winfo_children():child.destroy()
        for child in self.comparison.winfo_children():child.destroy()
        self.controls={};self.images=[];self.wrap_labels=[];self.preview_labels=[];self.date_example=None
        self.layout_examples=[];self.sample_title=None;self.danger_note=None;self.page_preview=None
        self.title_label.configure(text=tr(dict(SETTINGS_CATEGORIES)[category]))
        self.canvas.yview_moveto(0)
        notes={
            'appearance':'Choose a style below. The comparison shows your current style and the draft; only Apply or OK changes PFC.',
            'layout':'Compare complete layouts and tab styles before applying.',
            'columns':'Name visibility applies to the tab where Settings was opened. Other column preferences apply to all tabs. Hidden columns can be restored here.',
            'navigation':'Configure file menus, delete behavior and path shortcuts. Changes apply only after Apply or OK.',
            'preview':'Controls F3 Preview only. It does not change files, index drives or enable external plugins.',
            'general':'Choose the interface language and Windows sign-in behavior. Updates remain a manual action in Help.',
        }
        self.intro.configure(text=tr(notes[category]))
        self.comparison.pack(before=self.canvas.master,fill='x',pady=(0,8))
        if category in ('appearance','layout'):
            self._previews()
        else:
            self.page_preview=SettingsSamplePreview(self.comparison,category,self.font)
            self.page_preview.pack(fill='x')
        group=None
        for key,cat,title,label,choices,_method in self.specs:
            if cat!=category:continue
            compact=category in ('appearance','layout')
            if title!=group and not compact:
                if group is not None:ttk.Separator(self.page).pack(fill='x',pady=8)
                self._label(self.page,title,True); group=title
            if choices is None:
                control=ttk.Checkbutton(self.page,text=tr(label),variable=self.vars[key],style='Prefs.TCheckbutton')
                control.pack(anchor='w',pady=5)
            else:
                container=self.page
                if compact:
                    container=ttk.Frame(self.page);container.pack(fill='x',pady=(4,6))
                    ttk.Label(container,text=tr(label),style='PrefsTitle.TLabel',width=13).pack(side='left',padx=(0,8))
                elif label!=title:self._label(self.page,label)
                control=ttk.Combobox(container,state='readonly',style='Prefs.TCombobox',font=self.font,
                                      values=[tr('{count} Panels',count=value) if key=='panel_count' and value>1
                                              else tr(str(label)) for value,label in choices])
                control.current([v for v,_ in choices].index(self.vars[key].get()))
                control.pack(fill='x',expand=compact,pady=(0,0 if compact else 6))
                self._prepare_combo(control)
                control.bind('<<ComboboxSelected>>',lambda _e,k=key,c=control,opts=choices:self.vars[k].set(opts[c.current()][0]))
            self.controls[key]=control
            if key=='auto_start' and os.name!='nt':
                control.state(['disabled']); self._label(self.page,'Windows only. No system change is made on this platform.')
            hints={
                'font_size':'Auto fits the main window width. Turn it off for a fixed percentage. Settings keeps a stable reading size.',
                'onedrive_overlay':'Blue cloud: online only. Outlined green check: local copy. Filled green check: kept offline. Missing status is unknown, not proof of sync.',
                'size_emphasis':'GB is bold; TB is bold red. This changes display only, not file sizes.',
                'right_click_menu':'File Explorer uses the Windows native file menu. Blank-area and column menus remain PFC shortcuts.',
                'continue_errors':'Continue with the remaining files after a failure; errors are still reported.',
                'extension_effect':'On: syntax colors and formatted Markdown. Off: plain source text. Outline, properties, links and tables are in F3 Preview.',
                'ui_language':'Changes the interface after Apply, not your file names.',
                'auto_start':'Auto Start writes a Windows sign-in entry only when applied. Follow your organization’s software policy. Updates remain a manual action in Help.',
            }
            if key in hints:self._label(self.page,hints[key])
            if key=='recycle_bin':self.danger_note=self._label(self.page,'')
            if key=='time_style':self.date_example=self._label(self.page,'')
        if category=='navigation':self._prefix_rows()
        for label in self.wrap_labels:
            label.configure(wraplength=max(140,self.canvas.winfo_width()-36))
        self._changed()

    def _previews(self):
        if self.category=='layout':
            return self._layout_previews()
        bar=ttk.Frame(self.comparison);bar.pack(fill='x')
        ttk.Label(bar,text=tr('Style comparison'),style='PrefsTitle.TLabel').pack(side='left')
        ttk.Button(bar,text=tr('Compare at full size…'),style='Prefs.TButton',
                   command=lambda:self._enlarge(None)).pack(side='right')
        caption=ttk.Label(self.comparison,text=tr('Style details from demo screenshots; font size is shown separately.' if self.category=='appearance'
                          else 'Sample tabs and file list; panel layout is shown below.'),
                          style='Prefs.TLabel',wraplength=480)
        caption.pack(fill='x',pady=(2,4));self.comparison_caption=caption
        cards=ttk.Frame(self.comparison);cards.pack(fill='x')
        cards.columnconfigure((0,1),weight=1,uniform='preview')
        for i,(title,values) in enumerate((('Current style',self.original),('After Apply',None))):
            card=ttk.Frame(cards);card.grid(row=0,column=i,sticky='nsew',padx=(0,8))
            ttk.Label(card,text=tr(title),style='PrefsTitle.TLabel').pack(anchor='w',pady=(2,4))
            label=tk.Label(card,bd=1,relief='solid',anchor='center',bg=self.app.palette['surface'],cursor='hand2')
            label.pack(fill='x',pady=(0,8))
            label.bind('<Button-1>',lambda _e:self._enlarge(None))
            self.preview_labels.append((label,values))
        if self.category=='appearance':
            self.sample_title=ttk.Label(self.comparison,style='PrefsTitle.TLabel')
            self.sample_title.pack(anchor='w',pady=(0,3))
            self.sample_font=tkfont.Font(self)
            # Reserve the maximum sample height: choosing 100–300% cannot move
            # the controls under the pointer or push the comparison off-screen.
            self.sample_font.configure(size=-round(self._sample_pixels()*3))
            self.sample_box_height=self.sample_font.metrics('linespace')+4
            holder=ttk.Frame(self.comparison,height=self.sample_box_height)
            holder.pack(fill='x');holder.pack_propagate(False)
            self.font_example=tk.Label(holder,text='Notes.md · Aa 123',anchor='w',
                bg=self.app.palette['surface'],fg=self.app.palette['text'],font=self.sample_font)
            self.font_example.pack(fill='both',expand=True)

    def _layout_previews(self):
        bar=ttk.Frame(self.comparison);bar.pack(fill='x')
        ttk.Label(bar,text=tr('Panel layout comparison'),style='PrefsTitle.TLabel').pack(side='left')
        ttk.Button(bar,text=tr('Enlarge comparison…'),style='Prefs.TButton',
                   command=lambda:self._enlarge(None)).pack(side='right')
        self.comparison_caption=ttk.Label(self.comparison,
            text=tr('Whole-window illustration. The left stays unchanged until Apply; the right follows your choices.'),
            style='Prefs.TLabel',wraplength=480)
        self.comparison_caption.pack(fill='x',pady=(2,4))
        cards=ttk.Frame(self.comparison);cards.pack(fill='x')
        cards.columnconfigure((0,1),weight=1,uniform='layout-preview')
        for i,values in enumerate((self.original,None)):
            sample=SettingsLayoutPreview(cards,self.font,before=i==0)
            sample.grid(row=0,column=i,sticky='nsew',padx=(0,8))
            self.layout_examples.append((sample,values))

    def _enlarge(self,values):
        layout=self.category=='layout'
        popup=tk.Toplevel(self);popup.transient(self);popup.title(tr('Panel layout comparison' if layout else 'Style comparison'))
        sw,sh=self.winfo_screenwidth(),self.winfo_screenheight()
        wide=sw>=1180
        width,height=min(sw-48,1140 if wide else 620),min(sh-80,(410 if wide else 720) if layout else (330 if wide else 600))
        popup.geometry(f'{width}x{height}+{max(0,(sw-width)//2)}+{max(0,(sh-height)//2)}')
        footer=ttk.Frame(popup);footer.pack(side='bottom',fill='x',pady=8)
        canvas=tk.Canvas(popup,highlightthickness=0,bg=self.app.palette['window'])
        vertical=ttk.Scrollbar(popup,command=canvas.yview);vertical.pack(side='right',fill='y')
        horizontal=ttk.Scrollbar(popup,orient='horizontal',command=canvas.xview);horizontal.pack(side='bottom',fill='x')
        canvas.pack(fill='both',expand=True)
        canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        body=ttk.Frame(canvas,padding=10);canvas.create_window(0,0,window=body,anchor='nw')
        for i,(title,state) in enumerate((('Current style',self.original),('After Apply',values or {k:v.get() for k,v in self.vars.items()}))):
            card=ttk.Frame(body);card.grid(row=0 if wide else i,column=i if wide else 0,padx=6,pady=4)
            if layout:
                sample=SettingsLayoutPreview(card,self.font,before=i==0,height=220)
                sample.canvas.configure(width=540)
                sample.pack();sample.update_sample(state)
                continue
            ttk.Label(card,text=tr(title),style='PrefsTitle.TLabel').pack(anchor='w',pady=(0,6))
            shot=tk.PhotoImage(master=popup,data=SETTINGS_SHOTS[state['color_scheme']+'/'+state['tab_style']],format='png')
            label=ttk.Label(card,image=shot);label.image=shot;label.pack()
        body.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
        popup.bind('<MouseWheel>',lambda e:(canvas.yview_scroll(-1 if e.delta>0 else 1,'units'),'break')[-1])
        popup.bind('<Button-4>',lambda _e:(canvas.yview_scroll(-3,'units'),'break')[-1])
        popup.bind('<Button-5>',lambda _e:(canvas.yview_scroll(3,'units'),'break')[-1])
        def close():
            popup.grab_release();popup.destroy();self.grab_set();self.nav.focus_set()
        button=ttk.Button(footer,text=tr('Close'),command=close,style='Prefs.TButton')
        button.pack()
        popup.protocol('WM_DELETE_WINDOW',close);popup.bind('<Escape>',lambda _e:close())
        popup.bind('<KeyPress>',self._key_event,add='+')
        popup.grab_set()
        popup.update_idletasks();button.focus_force()

    def _schedule_shots(self):
        if self._shot_job is None:self._shot_job=self.after_idle(self._update_shots)

    def _update_shots(self):
        if self._shot_job is not None:self.after_cancel(self._shot_job);self._shot_job=None
        width=max(120,(self.comparison.winfo_width()-26)//2)
        # Crop the relevant tab/path/list detail, then resize with smaller steps
        # than integer subsampling. Original full screenshots remain in Compare.
        factor=max(4,math.ceil(360*4/min(360,width)))
        if getattr(self,'comparison_caption',None) is not None and self.comparison_caption.winfo_exists():
            self.comparison_caption.configure(wraplength=max(100,self.comparison.winfo_width()-12))
        if self.sample_title is not None:
            self.sample_title.configure(wraplength=max(100,self.comparison.winfo_width()-12))
        for label,values in getattr(self,'preview_labels',[]):
            values=values or {key:var.get() for key,var in self.vars.items()}
            key=values['color_scheme']+'/'+values['tab_style']
            if getattr(label,'shot_key',None)!=(key,factor):
                if key not in self._shot_sources:
                    photo=tk.PhotoImage(master=self,data=SETTINGS_SHOTS[key],format='png')
                    detail=tk.PhotoImage(master=self)
                    detail.tk.call(str(detail),'copy',str(photo),'-from',0,0,360,150)
                    self._shot_sources[key]=detail
                photo=self._shot_sources[key]
                label.image=photo if factor==4 else photo.zoom(4).subsample(factor)
                label.configure(image=label.image);label.shot_key=(key,factor)

    def _layout_preview(self):
        for sample,values in self.layout_examples:
            values=values or {key:var.get() for key,var in self.vars.items()}
            sample.update_sample(values)

    def _sample_pixels(self):
        base=self.app._base_font_sizes['TkDefaultFont']
        return abs(base)*(1 if base<0 else self.app._base_tk_scaling)

    def _prepare_combo(self, control):
        popdown=self.tk.call('ttk::combobox::PopdownWindow',str(control))
        self.tk.call(str(popdown)+'.f.l','configure','-font',str(self.font))
        # A wheel gesture over a closed combo scrolls without changing a draft.
        control.bind('<MouseWheel>',self._wheel)
        control.bind('<Button-4>',lambda _e:self._scroll(-3))
        control.bind('<Button-5>',lambda _e:self._scroll(3))

    def _prefix_rows(self):
        self._label(self.page,'Custom folder prefixes',True)
        self._label(self.page,'Choose up to three prefixes. Empty paths disable a slot.')
        self.prefix_rows=[]
        for index,item in enumerate(self.prefix_draft):
            row=ttk.Frame(self.page);row.pack(fill='x',pady=5)
            keys=list(PREFIX_ICONS)
            icon=ttk.Combobox(row,values=[tr(PREFIX_ICONS[k]) for k in keys],state='readonly',font=self.font,style='Prefs.TCombobox',width=12)
            self._prepare_combo(icon)
            icon.current(keys.index(item['icon']));icon.pack(side='left')
            img=prefix_icon(self,item['icon'],20);self.images.append(img)
            picture=ttk.Label(row,image=img);picture.pack(side='left',padx=4)
            path=tk.StringVar(self,value=item['path'])
            entry=ttk.Entry(self.page,textvariable=path,font=self.font);entry.pack(fill='x',pady=(0,5))
            def update(_e=None,i=index,c=icon,v=path,p=picture):
                self.prefix_draft[i]={'icon':keys[c.current()],'path':v.get()}
                if getattr(p,'icon_key',None)!=keys[c.current()]:
                    p.image=prefix_icon(self,keys[c.current()],20);p.configure(image=p.image)
                    p.icon_key=keys[c.current()]
                self._changed()
            icon.bind('<<ComboboxSelected>>',update)
            path.trace_add('write',lambda *_args,fn=update:fn())
            def browse(v=path):
                selected=filedialog.askdirectory(parent=self)
                if selected:v.set(selected)
            ttk.Button(row,text=tr('Browse…'),command=browse,style='Prefs.TButton').pack(side='right')
            self.prefix_rows.append((icon,path,entry))

    def _changed(self,*_args):
        if not hasattr(self,'apply_button'):return
        dirty=any(var.get()!=self.original[key] for key,var in self.vars.items()) or self.prefix_draft!=self.prefix_original
        self.apply_button.state(['!disabled'] if dirty else ['disabled'])
        self.status_var.set(tr('Unsaved changes') if dirty else tr('No pending changes'))
        for key,_cat,_group,_label,choices,_method in self.specs:
            if choices is not None and key in self.controls:
                self.controls[key].current([value for value,_label in choices].index(self.vars[key].get()))
        if 'font_size' in self.controls:
            self.controls['font_size'].configure(state='disabled' if self.vars['auto_font_size'].get() else 'readonly')
        self._update_shots()
        if self.page_preview is not None:
            self.page_preview.update_sample({k:v.get() for k,v in self.vars.items()},self.prefix_draft)
        if self.category=='appearance' and hasattr(self,'font_example') and self.font_example.winfo_exists():
            scale=self.app._font_scales[self.vars['font_size'].get()]
            self.sample_font.configure(family=self.font.actual('family'),size=-round(self._sample_pixels()*scale))
            title='File text after Apply · {percent}%' if not self.vars['auto_font_size'].get() else 'Auto font · {percent}% reference; follows window width'
            self.sample_title.configure(text=tr(title,percent=round(scale*100)))
            p=color_scheme(self.vars['color_scheme'].get())
            self.font_example.configure(bg=p['surface'],fg=p['text'])
        if self.category=='layout':self._layout_preview()
        if self.category=='columns' and self.date_example is not None:
            stamp=datetime(2026,9,22,17,15).timestamp()
            shown=self.vars['column_modified'].get()
            self.date_example.configure(text=tr('Example')+': '+modified_text(stamp,self.vars['date_order'].get(),self.vars['time_style'].get()) if shown else tr('Date column hidden; format is remembered.'))
            for key in ('date_order','time_style'):self.controls[key].configure(state='readonly' if shown else 'disabled')
            self.controls['size_emphasis'].state(['!disabled'] if self.vars['column_size'].get() else ['disabled'])
        if self.danger_note is not None:
            self.danger_note.configure(text=tr('Delete moves items to Recycle Bin. Shift+Delete is always permanent.') if self.vars['recycle_bin'].get() else tr('Warning: Delete will permanently remove files after Apply.'))
            self.danger_note.configure(foreground=self.app.palette['text'] if self.vars['recycle_bin'].get() else
                                      '#ffb4a9' if self.app.color_scheme_var.get()=='dark' else '#b00020')

    def apply(self,close=False):
        prefixes=[]
        for item in self.prefix_draft:
            value=item['path'].strip().strip('"')
            if value:
                path=Path(os.path.normpath(os.path.expandvars(value))).expanduser()
                if not path.is_absolute():
                    messagebox.showerror(tr('Custom folder prefixes'),tr('Enter an absolute folder path.'),parent=self)
                    self.nav.selection_clear(0,'end');self.nav.selection_set(3);self.show_page('navigation')
                    return
                value=str(path)
            prefixes.append({'icon':item['icon'],'path':value})
        changed=[s for s in self.specs if self.vars[s[0]].get()!=self.original[s[0]]]
        # Visibility is explicitly scoped to the original tab, before layout switches.
        for key,_cat,_group,_label,_choices,_method in changed:
            value=self.vars[key].get()
            if key.startswith('column_'):self.app.column_visible_vars[key[7:]].set(value)
            else:getattr(self.app,key+'_var').set(value)
        methods=[]
        for key,_cat,_group,_label,_choices,method in changed:
            if key in ('show_hidden','show_system','show_extensions'):
                setattr(self.pane,key,self.vars[key].get())
                if 'pane_refresh' not in methods:methods.append('pane_refresh')
            elif method not in methods:methods.append(method)
        # Language replaces menus; apply it last and rebuild this dialog's labels.
        if 'apply_ui_language' in methods:methods.remove('apply_ui_language');methods.append('apply_ui_language')
        try:
            for method in methods:
                if method=='pane_refresh':self.pane.refresh();self.pane.on_change()
                elif method=='apply_ui_language':self.app._apply_ui_language_now()
                else:getattr(self.app,method)()
            if self.app.auto_font_size_var.get() and any(method in methods for method in
                    ('set_auto_font_size','apply_font_size','apply_panel_count')):
                # Establish the actual auto-selected scale before taking the new
                # baseline, instead of showing a stale disabled percentage.
                if self.app._auto_font_job is not None:
                    self.app.after_cancel(self.app._auto_font_job)
                    self.app._auto_font_job=None
                self.app._apply_automatic_font_size()
            if prefixes!=self.prefix_original:self.app.set_home_prefixes(prefixes)
            self.app.save_config()
        except Exception as exc:
            messagebox.showerror(tr('PFC Settings'),tr('Some settings may already be applied. Review the settings before retrying.')+'\n\n'+str(exc),parent=self)
            return
        for key in self.vars:self.original[key]=self._read(key);self.vars[key].set(self.original[key])
        self.prefix_original=[dict(item) for item in prefixes];self.prefix_draft=[dict(item) for item in prefixes]
        if close:self.cancel();return
        for child in self.winfo_children():child.destroy()
        self.title(tr('PFC Settings'));self._build();self.nav.focus_set()

    def cancel(self):
        if self._shot_job is not None:self.after_cancel(self._shot_job);self._shot_job=None
        self.grab_release();self.destroy()

    def _key_event(self,event):
        if event.keysym in ('Tab','ISO_Left_Tab'):
            previous=event.keysym=='ISO_Left_Tab' or bool(event.state & 1)
            target=event.widget.tk_focusPrev() if previous else event.widget.tk_focusNext()
            if target is not None:target.focus_set()
        return 'break'

    def _scroll(self,units):
        if self.canvas.yview()!=(0.,1.):self.canvas.yview_scroll(units,'units')
        return 'break'

    def _wheel(self,event):
        if isinstance(event.widget,tk.Listbox):return 'break'
        return self._scroll(-1 if event.delta>0 else 1)

    def _reveal_focus(self,event):
        widget=event.widget
        if not str(widget).startswith(str(self.page)+'.'):return
        self.update_idletasks()
        y=widget.winfo_rooty()-self.page.winfo_rooty()
        top=self.canvas.canvasy(0);height=self.canvas.winfo_height()
        if y<top:self.canvas.yview_moveto(y/max(1,self.page.winfo_height()))
        elif y+widget.winfo_height()>top+height:
            self.canvas.yview_moveto((y+widget.winfo_height()-height)/max(1,self.page.winfo_height()))
