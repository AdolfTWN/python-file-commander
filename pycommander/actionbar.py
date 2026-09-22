"""Single-line action bar: measured widths, stable zoom, no font shrinking."""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .i18n import tr
from .tooltip import ToolTip


class ActionBarLayout:
    def __init__(self, app, frame):
        self.app, self.frame = app, frame
        self.labels = {}
        self.job = None
        self.mode = 'full'
        frame.pack_propagate(False)
        frame.bind('<Configure>', lambda _e: self.schedule(), add='+')
        frame.bind('<Destroy>', self._destroy, add='+')
        for button, key, label in app.action_buttons:
            button.pack_forget()
            self.labels[key] = (str(button.cget('text')), str(button.cget('text')))
            if key != 'F8':
                button._pfc_tooltip = ToolTip(button, lambda k=key: self.help(k), delay=650)
        self.localize()

    def _destroy(self, event):
        if event.widget is self.frame and self.job:
            self.frame.after_cancel(self.job)
            self.job = None

    def localize(self):
        short = {'F2': 'Rename', 'F3': 'Preview', 'F4': 'Search', 'F5': 'Copy',
                 'F6': 'Move', 'F7': 'Folder', 'F9': 'Compare', 'F11': 'Copy Path', 'F12': 'Path'}
        for button, key, label in self.app.action_buttons:
            if key != 'F8':
                self.set_label(key, f'{key} {tr(label)}', f'{key} {tr(short[key])}')

    def help(self, key):
        descriptions = {'F2': 'Rename the selected item.', 'F3': 'Open the selected item in PFC Preview.',
                        'F4': 'Search for files and folders below the current path.',
                        'F7': 'Create a folder here.', 'F9': 'Compare selected files or folders.',
                        'F11': 'Copy all selected full paths as text.',
                        'F12': 'Focus and select the path bar for direct paste.'}
        full = self.labels[key][0]
        return full + ('\n' + tr(descriptions[key]) if key in descriptions else '')

    def set_label(self, key, full, compact=None):
        value = (full, compact or full)
        if self.labels.get(key) != value:
            self.labels[key] = value
            self.app.action_button_by_hotkey[key].configure(text=full)
            self.schedule()

    def schedule(self):
        if self.job is None:
            self.job = self.frame.after_idle(self.layout)

    def layout(self):
        self.job = None
        if not self.frame.winfo_exists():
            return
        font = tkfont.nametofont('TkDefaultFont')
        padding = max(8, round(font.metrics('linespace') * .35))
        ttk.Style(self.app).configure('Action.TButton', padding=(2, 2))
        keys = [key for _, key, _ in self.app.action_buttons]
        available = max(1, self.frame.winfo_width())
        # Reserve the same F8 space for Git, SVN and VCS to avoid selection jitter.
        def widths(labels):
            return [max(font.measure(text), font.measure('F8 VCS') if key == 'F8' else 0) + padding + 2
                    for key, text in zip(keys, labels)]
        labels = [self.labels[key][0] for key in keys]
        self.mode = 'full'
        if sum(widths(labels)) > available:
            labels = [self.labels[key][1] for key in keys]
            self.mode = 'compact'
        if sum(widths(labels)) > available:
            # Reduce individual long labels first; F5/F6 keep their destination.
            self.mode = 'keys'
            for i in sorted(range(len(keys)), key=lambda i: font.measure(labels[i]), reverse=True):
                if keys[i] not in {'F5', 'F6', 'F8'}:
                    labels[i] = keys[i]
                if sum(widths(labels)) <= available:
                    break
        measured = widths(labels)
        total = sum(measured)
        spare = max(0, available - total)
        height = font.metrics('linespace') + padding + 4
        if self.frame.winfo_reqheight() != height:
            self.frame.configure(height=height)
        x = 0
        for i, (button, key, _) in enumerate(self.app.action_buttons):
            width = measured[i] + spare // len(keys) + (1 if i < spare % len(keys) else 0)
            # All supported main-window sizes fit the key-only baseline.
            if button.cget('text') != labels[i]:
                button.configure(text=labels[i])
            button.configure(style='Action.TButton')
            button.place(x=x, y=0, width=max(1, width - 2), height=height)
            x += width
