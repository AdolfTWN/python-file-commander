"""PFC message dialogs that inherit interface fonts and preserve modal ownership."""
import tkinter as tk
import math
from tkinter import ttk, messagebox, font as tkfont
from .i18n import tr
from .windowplacement import popup_work_area, position_popup_in_work_area

_NativeMessage = messagebox.Message


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
        footer = ttk.Frame(self, padding=pad); footer.pack(side='bottom', fill='x')
        body = ttk.Frame(self, padding=pad); body.pack(fill='both', expand=True)
        scroll = ttk.Scrollbar(body); scroll.pack(side='right', fill='y')
        self.text = tk.Text(body, font='TkDefaultFont', wrap='word', borderwidth=0,
                            highlightthickness=0, background=background, foreground=foreground,
                            yscrollcommand=scroll.set, cursor='arrow', takefocus=False)
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
            button = ttk.Button(footer, text=tr(choice.title()), command=lambda c=choice: self.choose(c))
            button.grid(row=0, column=index, padx=(0, pad//2), sticky='e')
            self.buttons[choice] = button
        footer.columnconfigure(0, weight=1)
        self.cancel_value = 'cancel' if 'cancel' in choices else 'no' if 'no' in choices else choices[0]
        self.bind('<Escape>', lambda _e: self.choose(self.cancel_value))
        self.bind('<Return>', lambda _e: self.choose(default if default in choices else choices[0]))
        self.protocol('WM_DELETE_WINDOW', lambda: self.choose(self.cancel_value))
        self.geometry(f'{width}x{height}')
        self.update_idletasks()
        self.minsize(min(width, footer.winfo_reqwidth()+2*pad), min(height, 5*line))
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
