"""Categorized, draft-first preferences. No filesystem scanning or network preview."""
import os
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

from .i18n import tr, LANGUAGES
from .tabs import TAB_STYLES, color_scheme
from .columnsettings import modified_text
from .homeprefix import PREFIX_ICONS, prefix_icon
from .settingsshots import SETTINGS_SHOTS


SETTINGS_CATEGORIES = (
    ('appearance', 'Appearance'), ('layout', 'Layout & Tabs'),
    ('columns', 'File Columns'), ('navigation', 'Paths & Operations'),
    ('preview', 'Preview'), ('general', 'General'),
)


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
        ('extension_effect', 'preview', 'F3 Preview', 'Extension Effect', None, 'set_extension_effect'),
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
                                size=-min(22, max(14, abs(int(base.cget('size'))))))
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
        self._build()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        width, height = min(1080, sw-48), min(820, sh-80)
        self.geometry(f'{width}x{height}+{max(0,min(app.winfo_rootx()+30,sw-width-24))}+{max(0,min(app.winfo_rooty()+30,sh-height-40))}')
        self.minsize(min(720,width), min(440,height))
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
        style.configure('Prefs.TCheckbutton',indicatorsize=18,indicatormargin=(0,0,7,0))
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
        self.nav = tk.Listbox(body, font=self.font, width=20, exportselection=False,
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

    def _resize(self, event):
        self.canvas.itemconfigure(self.page_id,width=event.width)
        self.intro.configure(wraplength=max(100,event.width-12))
        for label in getattr(self,'wrap_labels',[]):
            label.configure(wraplength=max(140,event.width-36))
        self._update_shots()

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
        self.controls={};self.images=[];self.wrap_labels=[];self.preview_labels=[];self.date_example=None
        self.title_label.configure(text=tr(dict(SETTINGS_CATEGORIES)[category]))
        self.canvas.yview_moveto(0)
        group=None
        for key,cat,title,label,choices,_method in self.specs:
            if cat!=category:continue
            if title!=group:
                if group is not None:ttk.Separator(self.page).pack(fill='x',pady=8)
                self._label(self.page,title,True); group=title
            if choices is None:
                control=ttk.Checkbutton(self.page,text=tr(label),variable=self.vars[key],style='Prefs.TCheckbutton')
                control.pack(anchor='w',pady=5)
            else:
                if label!=title:self._label(self.page,label)
                control=ttk.Combobox(self.page,state='readonly',style='Prefs.TCombobox',font=self.font,
                                      values=[tr('{count} Panels',count=value) if key=='panel_count' and value>1
                                              else tr(str(label)) for value,label in choices])
                control.current([v for v,_ in choices].index(self.vars[key].get()))
                control.pack(fill='x',pady=(0,6))
                popdown=self.tk.call('ttk::combobox::PopdownWindow',str(control))
                self.tk.call(str(popdown)+'.f.l','configure','-font',str(self.font))
                control.bind('<<ComboboxSelected>>',lambda _e,k=key,c=control,opts=choices:self.vars[k].set(opts[c.current()][0]))
            self.controls[key]=control
            if key=='auto_start' and os.name!='nt':
                control.state(['disabled']); self._label(self.page,'Windows only. No system change is made on this platform.')
        notes={
            'appearance':'Auto adjusts to window and panel widths. Turn it off to choose a fixed scale. The settings dialog keeps a stable reading size.',
            'layout':'1 Panel combines a folder tree and file list with shared tabs. Tab colors and lock modes remain in each tab’s right-click menu.',
            'columns':'Name visibility applies to the tab where Settings was opened. Other column preferences apply to all tabs. Hidden columns can be restored here.',
            'navigation':'File Explorer uses the Windows native file menu. Blank-area and column menus remain PFC shortcuts. Disabling Recycle Bin makes Delete permanent; Shift+Delete always bypasses it.',
            'preview':'Extension Effect enables syntax colors and Markdown rendering in F3 Preview. Reading tools (outline, properties, links and tables) remain in Preview. Link resolution stays within the selected document workspace; this setting does not scan drives.',
            'general':'Auto Start writes a Windows sign-in entry only when applied. Follow your organization’s software policy. Updates remain a manual action in Help.',
        }
        self._label(self.page,notes[category])
        if category=='appearance':
            self._label(self.page,'Text at selected scale',True)
            self.font_example=tk.Label(self.page,text='PFC · Notes.md',anchor='w',
                                       bg=self.app.palette['surface'],fg=self.app.palette['text'])
            self.font_example.pack(fill='x',pady=6)
        if category in ('appearance','layout'): self._previews()
        if category=='columns':
            self.date_example=self._label(self.page,'')
            self._label(self.page,'Blue cloud: online only. Outlined green check: local copy. Filled green check: kept offline. Missing status is unknown, not proof of sync.')
        if category=='navigation':self._prefix_rows()
        for label in self.wrap_labels:
            label.configure(wraplength=max(140,self.canvas.winfo_width()-36))
        self._changed()

    def _previews(self):
        self._label(self.page,'Style comparison',True)
        self._label(self.page,'Sample screenshots from PFC with demo files (100%). No personal folders are captured.')
        cards=ttk.Frame(self.page);cards.pack(fill='x')
        cards.columnconfigure((0,1),weight=1,uniform='preview')
        for i,(title,values) in enumerate((('Current style',self.original),('After Apply',None))):
            card=ttk.Frame(cards);card.grid(row=0,column=i,sticky='nsew',padx=(0,8))
            self._label(card,title,True)
            label=tk.Label(card,bd=1,relief='solid',anchor='center',bg=self.app.palette['surface'])
            label.pack(fill='x',pady=(0,8))
            ttk.Button(card,text=tr('Enlarge preview'),style='Prefs.TButton',
                       command=lambda v=values:self._enlarge(v)).pack(anchor='w')
            self.preview_labels.append((label,values))
        if self.category=='layout':
            self.layout_example=tk.Canvas(self.page,height=94,highlightthickness=0)
            self.layout_example.pack(fill='x',pady=8)
            self.layout_example.bind('<Configure>',lambda _e:self._layout_preview())
            self._label(self.page,'Layout diagram · relative widths only')

    def _enlarge(self,values):
        values=values or {key:var.get() for key,var in self.vars.items()}
        popup=tk.Toplevel(self);popup.transient(self);popup.title(tr('Style comparison'))
        shot=tk.PhotoImage(master=popup,data=SETTINGS_SHOTS[values['color_scheme']+'/'+values['tab_style']],format='png')
        label=ttk.Label(popup,image=shot);label.image=shot;label.pack(padx=12,pady=12)
        def close():
            popup.grab_release();popup.destroy();self.grab_set();self.nav.focus_set()
        button=ttk.Button(popup,text=tr('Close'),command=close,style='Prefs.TButton')
        button.pack(pady=(0,12))
        popup.protocol('WM_DELETE_WINDOW',close);popup.bind('<Escape>',lambda _e:close())
        popup.bind('<KeyPress>',self._key_event,add='+')
        popup.grab_set()
        popup.update_idletasks();button.focus_force()

    def _update_shots(self):
        width=max(160,(self.canvas.winfo_width()-40)//2)
        factor=max(1,(540+width-1)//width)
        for label,values in getattr(self,'preview_labels',[]):
            values=values or {key:var.get() for key,var in self.vars.items()}
            key=values['color_scheme']+'/'+values['tab_style']
            if getattr(label,'shot_key',None)!=(key,factor):
                photo=tk.PhotoImage(master=self,data=SETTINGS_SHOTS[key],format='png')
                label.image=photo.subsample(factor)
                label.configure(image=label.image);label.shot_key=(key,factor)

    def _layout_preview(self):
        c=self.layout_example;c.delete('all');p=color_scheme(self.vars['color_scheme'].get())
        c.configure(bg=p['window']);w=max(240,c.winfo_width()-8);n=self.vars['panel_count'].get()
        for i in range(2 if n==1 else n):
            left=(0 if i==0 else w/3) if n==1 else w*i/n
            right=(w/3 if i==0 else w) if n==1 else w*(i+1)/n
            c.create_rectangle(left+2,20,right-2,88,fill=p['surface'],outline=p['border'])
            c.create_text((left+right)/2,54,text=tr('Folders') if n==1 and i==0 else tr('Files'),fill=p['text'],font=self.font)
        c.create_text(4,8,anchor='w',text=tr('Shared tabs') if n==1 else tr('Tabs per panel'),font=self.font,fill=p['text'])

    def _prefix_rows(self):
        self._label(self.page,'Custom folder prefixes',True)
        self._label(self.page,'Choose up to three prefixes. Empty paths disable a slot.')
        self.prefix_rows=[]
        for index,item in enumerate(self.prefix_draft):
            row=ttk.Frame(self.page);row.pack(fill='x',pady=5)
            keys=list(PREFIX_ICONS)
            icon=ttk.Combobox(row,values=[tr(PREFIX_ICONS[k]) for k in keys],state='readonly',font=self.font,width=12)
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
        if self.category=='appearance' and hasattr(self,'font_example') and self.font_example.winfo_exists():
            scale=self.app._font_scales[self.vars['font_size'].get()]
            self.sample_font=tkfont.Font(self,family=self.font.actual('family'),size=-round(14*scale))
            self.font_example.configure(font=self.sample_font)
        if self.category=='layout' and hasattr(self,'layout_example') and self.layout_example.winfo_exists():self._layout_preview()
        if self.category=='columns' and self.date_example is not None:
            stamp=datetime(2026,9,22,17,15).timestamp()
            self.date_example.configure(text=tr('Example')+': '+modified_text(stamp,self.vars['date_order'].get(),self.vars['time_style'].get()))

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
        if isinstance(event.widget,(ttk.Combobox,tk.Listbox)):return 'break'
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
