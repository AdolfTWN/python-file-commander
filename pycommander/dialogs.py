"""PFC message dialogs that inherit interface fonts and preserve modal ownership."""
import tkinter as tk
import math
from tkinter import ttk, messagebox, simpledialog, font as tkfont
from .flowlayout import FlowToolbar, guard_dialog_keys
from .i18n import tr
from .windowplacement import popup_work_area, position_popup_in_work_area

_NativeMessage = messagebox.Message
_NATIVE_INPUTS={kind:getattr(getattr(simpledialog,'ask'+kind),'_pfc_native_input',
                           getattr(simpledialog,'ask'+kind)) for kind in ('string','integer','float')}


class ScaledMessageDialog(tk.Toplevel):
    CHOICES = {'ok': ('ok',), 'okcancel': ('ok', 'cancel'),
               'yesno': ('yes', 'no'), 'yesnocancel': ('yes', 'no', 'cancel'),
               'retrycancel': ('retry', 'cancel'), 'abortretryignore': ('abort', 'retry', 'ignore')}

    def __init__(self, parent, options):
        super().__init__(parent); self.withdraw(); self.transient(parent.winfo_toplevel())
        self._pfc_message_dialog = True; self.result = None
        self.title(options.get('title') or 'PFC')
        palette = getattr(parent._root(), 'palette', {})
        background, foreground = palette.get('window', '#eeeeee'), palette.get('text', '#101010')
        self.configure(background=background)
        font = tkfont.nametofont('TkDefaultFont', root=self)
        line = font.metrics('linespace'); ratio = max(1, line/20)
        pad = max(10, round(line*.5))
        area = popup_work_area(parent)
        width = min(area[2]-area[0]-48, round(620*ratio))
        footer = FlowToolbar(self, padding=pad); footer.pack(side='bottom', fill='x')
        body = ttk.Frame(self, padding=pad); body.pack(fill='both', expand=True)
        scroll = ttk.Scrollbar(body); scroll.pack(side='right', fill='y')
        self.text = tk.Text(body, font='TkDefaultFont', wrap='word', borderwidth=0,
                            highlightthickness=0, background=background, foreground=foreground,
                            yscrollcommand=scroll.set, cursor='arrow', takefocus=True)
        self.text.pack(fill='both', expand=True); scroll.configure(command=self.text.yview)
        message = str(options.get('message') or '')
        if options.get('detail'): message += '\n\n'+str(options['detail'])
        # Fit short confirmations instead of enlarging a mostly empty window.
        # Long details remain scrollable within the screen-height budget.
        available = max(80, width-2*pad-30)
        rows = sum(max(1, math.ceil(font.measure(part)/available)) for part in message.split('\n'))
        height = min(area[3]-area[1]-80, (max(2, min(12, rows))+2)*line+4*pad)
        self.text.insert('1.0', message); self.text.configure(state='disabled')
        kind = str(options.get('type') or 'ok')
        choices = self.CHOICES.get(kind, ('ok',))
        default = str(options.get('default') or choices[0])
        self.buttons = {}
        for index, choice in enumerate(choices):
            button = ttk.Button(footer, text=tr(choice.title()), width=0, command=lambda c=choice: self.choose(c))
            footer.add(button)
            self.buttons[choice] = button
        self.cancel_value = 'cancel' if 'cancel' in choices else 'no' if 'no' in choices else choices[0]
        guard_dialog_keys(self)
        self.bind('<Escape>', lambda _e: self.choose(self.cancel_value))
        def accept(_event=None):
            focused=self.focus_get()
            if focused in self.buttons.values():focused.invoke()
            else:self.choose(default if default in choices else choices[0])
            return 'break'
        self.bind('<Return>',accept)
        self.protocol('WM_DELETE_WINDOW', lambda: self.choose(self.cancel_value))
        self.geometry(f'{width}x{height}')
        self.update_idletasks()
        minimum=max(240,sum(button.winfo_reqwidth() for button in self.buttons.values())+
                    footer.gap*(len(self.buttons)-1)+2*pad)
        self.minsize(min(width,minimum), min(height, 5*line))
        self.deiconify(); position_popup_in_work_area(self, parent, area); self.lift()
        self.buttons.get(default, self.buttons[choices[0]]).focus_force()

    def choose(self, value):
        self.result = value; self.destroy()


class _ScaledMessage(_NativeMessage):
    _pfc_scaled_message = True

    def show(self, **options):
        values = dict(self.options, **options)
        parent = values.get('parent') or self.master or tk._default_root
        if parent is None or not getattr(parent._root(), '_pfc_scaled_messages', False):
            return super().show(**options)
        previous = parent.grab_current(); focus = parent.focus_get()
        dialog = ScaledMessageDialog(parent, values)
        try:
            dialog.grab_set(); parent.wait_window(dialog)
            return dialog.result
        finally:
            if dialog.winfo_exists(): dialog.destroy()
            if previous is not None and previous.winfo_exists(): previous.grab_set()
            if focus is not None and focus.winfo_exists(): focus.focus_set()


def install_scaled_messageboxes(root):
    # Keep the public messagebox API, result values and existing test mocks.
    # Other Tk roots and external file pickers continue using their own dialogs.
    root._pfc_scaled_messages = True
    if not getattr(messagebox.Message, '_pfc_scaled_message', False):
        messagebox.Message = _ScaledMessage
    for kind in _NATIVE_INPUTS:
        current=getattr(simpledialog,'ask'+kind)
        if not getattr(current,'_pfc_scaled_input',False):
            def ask(title,prompt,_kind=kind,**options):
                parent=options.get('parent') or tk._default_root
                if parent is None or not getattr(parent._root(),'_pfc_scaled_messages',False):
                    return _NATIVE_INPUTS[_kind](title,prompt,**options)
                dialog=ScaledInputDialog(parent,title,prompt,_kind,options)
                parent.wait_window(dialog)
                return dialog.result
            ask._pfc_scaled_input=True
            ask._pfc_native_input=_NATIVE_INPUTS[kind]
            setattr(simpledialog,'ask'+kind,ask)


class ScaledInputDialog(tk.Toplevel):
    """PFC-only typed prompts; focused Cancel, nested grabs and font scale work."""
    def __init__(self,parent,title,prompt,kind='string',options=None):
        super().__init__(parent);self.withdraw();options=options or {}
        self.previous_grab=parent.grab_current();self.previous_focus=parent.focus_get()
        self.result=None;self.kind=kind;self.options=options
        self.title(title);self.transient(parent.winfo_toplevel())
        area=popup_work_area(parent);font=tkfont.nametofont('TkDefaultFont')
        line=font.metrics('linespace');width=min(round(620*max(1,line/20)),area[2]-area[0]-48)
        outer=ttk.Frame(self,padding=12);outer.pack(fill='both',expand=True)
        message=ttk.Frame(outer);message.pack(fill='both',expand=True,pady=(0,8))
        scroll=ttk.Scrollbar(message);scroll.pack(side='right',fill='y')
        palette=getattr(parent._root(),'palette',{})
        self.prompt=tk.Text(message,font='TkDefaultFont',wrap='word',height=3,
                            borderwidth=0,highlightthickness=0,takefocus=True,
                            background=palette.get('window','#eeeeee'),foreground=palette.get('text','#101010'),
                            yscrollcommand=scroll.set)
        self.prompt.insert('1.0',prompt);self.prompt.configure(state='disabled')
        self.prompt.pack(fill='both',expand=True);scroll.configure(command=self.prompt.yview)
        self.entry=ttk.Entry(outer,font='TkDefaultFont',show=options.get('show',''),width=12)
        self.entry.pack(fill='x')
        if options.get('initialvalue') is not None:self.entry.insert(0,str(options['initialvalue']))
        self.error=ttk.Label(outer,text='',wraplength=width-32)
        self.actions=FlowToolbar(outer);self.actions.pack(side='bottom',fill='x',pady=(10,0),before=message)
        self.entry.pack(side='bottom',fill='x',before=message)
        self.ok_button=ttk.Button(self.actions,text=tr('OK'),width=0,command=self.accept)
        self.cancel_button=ttk.Button(self.actions,text=tr('Cancel'),width=0,command=self.cancel)
        self.actions.add(self.ok_button);self.actions.add(self.cancel_button)
        guard_dialog_keys(self)
        self.bind('<Escape>',lambda e:self.cancel())
        self.bind('<Return>',self._return)
        self.protocol('WM_DELETE_WINDOW',self.cancel)
        self.bind('<Configure>',lambda e:self._wrap(e.width) if e.widget is self else None)
        self.geometry(f'{width}x{min(area[3]-area[1]-64,max(180,6*line+70))}')
        self.minsize(min(420,width),min(170,area[3]-area[1]-64))
        self.deiconify();position_popup_in_work_area(self,parent,area)
        self.grab_set();self.entry.focus_force();self.entry.selection_range(0,'end')

    def _wrap(self,width):
        self.error.configure(wraplength=max(120,width-32))

    def _return(self,_event=None):
        if self.focus_get() is self.cancel_button:self.cancel()
        else:self.accept()
        return 'break'

    def accept(self):
        try:
            raw=self.entry.get()
            value=raw if self.kind=='string' else self.tk.getint(raw) if self.kind=='integer' else self.tk.getdouble(raw)
            if self.kind!='string':
                if not math.isfinite(value):raise ValueError()
                if self.options.get('minvalue') is not None and value<self.options['minvalue']:raise ValueError()
                if self.options.get('maxvalue') is not None and value>self.options['maxvalue']:raise ValueError()
        except (tk.TclError,ValueError,OverflowError):
            low=self.options.get('minvalue','−∞');high=self.options.get('maxvalue','∞')
            self.error.configure(text=tr('Enter a valid number ({minimum}–{maximum}).',minimum=low,maximum=high))
            self.error.pack(side='bottom',fill='x',before=self.entry,pady=(5,0));self.entry.focus_set()
            return
        self.result=value;self._finish()

    def cancel(self):self._finish()

    def _finish(self):
        self.destroy()
        try:
            if self.previous_grab is not None and self.previous_grab.winfo_exists():self.previous_grab.grab_set()
            if self.previous_focus is not None and self.previous_focus.winfo_exists():self.previous_focus.focus_set()
        except tk.TclError:pass
