"""F8 and context menus share one asynchronous, selection-scoped VCS controller."""

import os
import queue
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox

from .i18n import tr
from .tooltip import ToolTip, MenuToolTip
from .vcs import invalidate_vcs_cache
from .vcsactions import VcsContext, vcs_context, vcs_status, vcs_find_client, vcs_dialog_command, VCS_CLIENT_NAMES


class VcsActions:
    def __init__(self, app):
        self.app = app
        self.context = None
        self.key = None
        self.tree_target = False
        self.pending = None
        self.busy = False
        self.stopped = False
        self.results = queue.Queue()
        self.status_cache = {}
        self.clients = {}
        self.debounce = None
        self.poll_job = app.after(80, self._poll)
        self.menus = []
        self.processes = []
        self.tooltip = tr('Not a Git or SVN working copy.')
        button = app.action_button_by_hotkey['F8']
        button._pfc_tooltip = ToolTip(button, lambda: self.tooltip, delay=650)
        tree = app.folder_tree.tree
        tree.bind('<FocusIn>', lambda _e: self.request(tree=True), add='+')
        tree.bind('<<TreeviewSelect>>', lambda _e: self.request(), add='+')
        app.bind('<FocusIn>', self._focus, add='+')
        app.bind('<Destroy>', self._destroy, add='+')
        self.request()

    def _focus(self, event):
        if any(event.widget is pane.tree for pane in self.app.all_panes()):
            self.request(tree=False)
        elif event.widget is self.app.folder_tree.tree:
            self.request(tree=True)

    def _destroy(self, event):
        if event.widget is self.app:
            self.stopped = True
            for job in (self.debounce, self.poll_job):
                if job:
                    try: self.app.after_cancel(job)
                    except tk.TclError: pass

    def snapshot(self, pane=None, clicked=None, tree_path=None):
        pane = pane or self.app.active
        if tree_path is not None:
            return ((tree_path,), tree_path, False)
        if self.tree_target and self.app._single_layout and clicked is None:
            tree = self.app.folder_tree
            selection = tree.tree.selection()
            iid = tree.tree.focus()
            if iid not in selection:
                iid = selection[0] if selection else ''
            path = tree.paths.get(iid)
            if path is None:
                return ((), Path(os.path.abspath(os.sep)), True)
            return ((path,), path, False)
        paths = tuple(pane.selected_paths())
        iid = pane.tree.focus()
        tags = pane.tree.item(iid, 'tags') if iid and pane.tree.exists(iid) else ()
        focus = clicked or (Path(tags[0]) if tags and Path(tags[0]) in paths else None)
        focus = focus or (paths[0] if paths else pane.path)
        return (paths or (focus,), focus, pane.archive_session is not None)

    def request(self, tree=None):
        if self.stopped:
            return
        if tree is not None:
            self.tree_target = tree
        snapshot = self.snapshot()
        if snapshot != self.key:
            self.key = snapshot
            self.context = None
            self.tooltip = tr('Checking working copy…')
            self._button(None)
        if self.debounce:
            self.app.after_cancel(self.debounce)
        self.debounce = self.app.after(200, lambda: self._discover(snapshot))

    def _discover(self, snapshot):
        self.debounce = None
        if snapshot != self.key or self.context is not None:
            return
        self._queue(('context', snapshot))

    def _queue(self, task):
        # One worker and one latest request: rapid navigation cannot create a thread storm.
        if self.busy:
            if task[0] == 'context' or self.pending is None or self.pending[0] != 'context':
                self.pending = task
            return
        self.busy = True
        def work():
            try:
                value = vcs_context(*task[1]) if task[0] == 'context' else vcs_status(task[1])
                clients = {}
                if task[0] == 'context' and value.location:
                    kind = value.location.kind
                    clients[kind] = vcs_find_client(kind, self.app_vcs_paths.get(kind, ''))
                self.results.put((task, value, clients))
            except Exception:
                # Never leave the controller permanently busy after filesystem races.
                self.results.put((task, None, {}))
        # Copy Tk/config state on the GUI thread; workers never call Tk.
        self.app_vcs_paths = {kind: self.app.config_data.get('vcs', kind + '_client', fallback='')
                              for kind in ('git', 'svn')}
        threading.Thread(target=work, daemon=True, name='PFC-VCS-actions').start()

    def _poll(self):
        self.poll_job = None
        if self.stopped:
            return
        try:
            task, value, clients = self.results.get_nowait()
            self.busy = False
            self.clients.update(clients)
            if task[0] == 'context' and task[1] == self.key:
                self.context = value
                self.tooltip = (tr(value.reason) if value and not value.location else
                                tr('Version Control') + (' — ' + str(value.focus) if value else ''))
                self._button(value)
                for menu, snapshot, context in list(self.menus):
                    if snapshot == self.key and context is None:
                        self._populate(menu, snapshot, value)
            elif task[0] == 'status' and value is not None:
                self.status_cache[task[1]] = (time.monotonic(), value)
                if len(self.status_cache) > 64:
                    self.status_cache.pop(next(iter(self.status_cache)))
                for menu, snapshot, context in list(self.menus):
                    if context == task[1]:
                        self._summary(menu, context, value)
            pending, self.pending = self.pending, None
            if pending:
                self._queue(pending)
        except queue.Empty:
            pass
        finished = [p for p in self.processes if p.poll() is not None]
        if finished:
            self.processes = [p for p in self.processes if p not in finished]
            self.invalidate()
        self.menus = [(m, s, c) for m, s, c in self.menus if m.winfo_exists()]
        self.poll_job = self.app.after(80, self._poll)

    def _button(self, context):
        button = self.app.action_button_by_hotkey['F8']
        kind = context.location.kind if context and context.location else None
        label = {'git': 'Git', 'svn': 'SVN'}.get(kind, 'VCS')
        self.app.action_bar.set_label('F8', 'F8 ' + label, 'F8 ' + label)
        button.state(['!disabled'] if kind else ['disabled'])

    def invalidate(self):
        self.status_cache.clear()
        invalidate_vcs_cache()
        self.context = None
        self.request()
        # Refresh only existing VCS badges, never rebuild rows or move selection.
        for pane in self.app.all_panes():
            pane._vcs_generation += 1
            pane._vcs_loading = False
            pane._vcs_requested_at = 0
            pane._request_vcs_statuses()

    def _clip(self, text):
        limit = min(650, max(240, self.app.winfo_screenwidth() - 120))
        font = tkfont.nametofont('TkMenuFont')
        text = str(text).replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        if font.measure(text) <= limit:
            return text
        left, right = len(text) // 2, len(text) // 2
        while left > 1 and font.measure(text[:left] + '…' + text[-right:]) > limit:
            left -= 1; right = max(1, right - 1)
        return text[:left] + '…' + text[-right:]

    def build_menu(self, parent, pane=None, clicked=None, tree_path=None):
        snapshot = self.snapshot(pane, clicked, tree_path)
        context = self.context if snapshot == self.key else None
        menu = tk.Menu(parent, tearoff=False, font='TkMenuFont')
        self.menus.append((menu, snapshot, context))
        self._populate(menu, snapshot, context)
        if context is None:
            self.key = snapshot
            self.context = None
            self._queue(('context', snapshot))
        return menu

    def _populate(self, menu, snapshot, context):
        if not menu.winfo_exists():
            return
        self.menus = [(m, s, context if m is menu else c) for m, s, c in self.menus]
        menu.delete(0, 'end')
        menu._vcs_headers = {}
        if not context or not context.location:
            menu.add_command(label=tr(context.reason if context else 'Checking working copy…'), state='disabled')
            self._redraw(menu)
            return
        kind = context.location.kind
        for key in ('location', 'scope', 'changes', 'remote'):
            menu._vcs_headers[key] = menu.index('end') + 1 if menu.index('end') is not None else 0
            menu.add_command(label=tr('Checking status…'), state='disabled')
        menu.add_separator()
        for action, label in [('commit', 'Commit selected…'), ('commit_all', 'Commit entire working copy…'),
                              ('push', 'Push current branch…'), ('log', 'Show History'),
                              ('revisiongraph', 'Show Graph')]:
            if action == 'push' and kind == 'svn':
                continue
            if kind == 'svn' and action in {'log', 'revisiongraph'}:
                label = label + ' (may use network)'
            state = 'disabled' if context.mixed and action in {'commit', 'commit_all', 'push'} else 'normal'
            menu.add_command(label=tr(label), state=state,
                             command=lambda a=action, c=context: self.launch(c, a))
        menu.add_separator()
        menu.add_command(label=tr('Refresh status'), command=lambda: self.refresh_menu(menu, snapshot, context))
        menu.add_command(label=tr('Choose Tortoise client…'), command=lambda: self.choose_client(kind))
        menu._pfc_tooltip = MenuToolTip(menu, {})
        cached = self.status_cache.get(context)
        self._summary(menu, context, cached[1] if cached else None)
        if not cached or time.monotonic() - cached[0] > 3:
            self._queue(('status', context))

    def _summary(self, menu, context, summary):
        if not menu.winfo_exists() or not getattr(menu, '_vcs_headers', None):
            return
        kind = 'Git' if context.location.kind == 'git' else 'SVN'
        branch = summary.branch if summary else ''
        if branch == '(detached)':
            branch = 'detached HEAD'
        location = kind + ' · ' + (branch or (summary.url if summary else '') or context.location.root.name)
        scope = tr('Selected: {count} · {path}', count=len(context.paths), path=context.focus)
        changes = tr('Checking status…')
        if summary:
            changes = (tr(summary.error) if summary.error else
                       tr('Changes {changed} · Untracked {untracked} · Conflicts {conflicts}',
                          changed=summary.changed, untracked=summary.untracked, conflicts=summary.conflicts))
        if context.location.kind == 'svn':
            remote = tr('Commit sends changes to the SVN server; no Push.')
        elif summary and summary.upstream and summary.ahead is not None:
            remote = tr('Push {ahead} · Behind {behind} · {upstream} (cached)', ahead=summary.ahead,
                        behind=summary.behind, upstream=summary.upstream)
        else:
            remote = tr('Push: unknown — no upstream information (no Fetch).')
        if context.mixed:
            changes = tr('Selection spans working copies. Select items from one working copy.')
        for key, full in zip(('location', 'scope', 'changes', 'remote'), (location, scope, changes, remote)):
            label = self._clip(full)
            menu.entryconfigure(menu._vcs_headers[key], label=label)
            menu._pfc_tooltip.descriptions[label] = full
            self.app.header_popup.descriptions[label] = full
        self._redraw(menu)

    def _redraw(self, menu):
        for popup in list(self.app.header_popup.popups):
            if popup.menu is menu:
                popup.refresh()
                if getattr(menu, '_vcs_above_button', False):
                    button = self.app.action_button_by_hotkey['F8']
                    popup.show(button.winfo_rootx(), button.winfo_rooty() - popup.height - 4)

    def refresh_menu(self, menu, snapshot, context):
        self.status_cache.pop(context, None)
        self._queue(('status', context))
        # Menu commands close the popup first; reopen the same scoped menu.
        self.app.after_idle(lambda: self._show(menu))

    def _show(self, menu):
        if not menu.winfo_exists():
            return
        button = self.app.action_button_by_hotkey['F8']
        menu._vcs_above_button = True
        self.app.header_popup.show_at(button.winfo_rootx(), button.winfo_rooty(), menu)
        popup = self.app.header_popup.popups[0]
        popup.show(button.winfo_rootx(), button.winfo_rooty() - popup.height - 4)

    def show(self):
        # Compare/preview/search own their keys. Never act on the hidden main selection.
        focused = self.app.focus_get()
        if self.app._settings_are_open() or self.app.grab_current() or (
                focused is not None and focused.winfo_toplevel() is not self.app):
            return 'break'
        old = getattr(self, 'quick_menu', None)
        self.app.header_popup.close_all()
        if old is not None:
            old.destroy()
        self.quick_menu = self.build_menu(self.app)
        self._show(self.quick_menu)
        return 'break'

    def choose_client(self, kind):
        if os.name != 'nt':
            messagebox.showinfo(tr('Version Control'), tr('Tortoise integration requires Windows.'), parent=self.app)
            return None
        filename = filedialog.askopenfilename(parent=self.app, title=tr('Choose Tortoise client…'),
                    filetypes=[(VCS_CLIENT_NAMES[kind], VCS_CLIENT_NAMES[kind])])
        if not filename:
            return None
        executable = vcs_find_client(kind, filename)
        if not executable or os.path.normcase(executable) != os.path.normcase(filename):
            messagebox.showerror(tr('Version Control'), tr('Select the matching Tortoise executable.'), parent=self.app)
            return None
        if not self.app.config_data.has_section('vcs'):
            self.app.config_data.add_section('vcs')
        self.app.config_data.set('vcs', kind + '_client', executable)
        self.app.save_config()
        self.clients[kind] = executable
        return executable

    def launch(self, context, action):
        if os.name != 'nt':
            messagebox.showinfo(tr('Version Control'), tr('Tortoise integration requires Windows.'), parent=self.app)
            return
        kind = context.location.kind
        executable = self.clients.get(kind)
        if not executable:
            messagebox.showinfo(tr('Version Control'),
                tr('Tortoise client not found. Choose an installed client; nothing will be installed.'), parent=self.app)
            executable = self.choose_client(kind)
        if not executable:
            return
        try:
            command = vcs_dialog_command(executable, context, action)
            self.processes.append(subprocess.Popen(command, cwd=context.location.root,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)))
        except (OSError, ValueError) as exc:
            messagebox.showerror(tr('Version Control'), tr(str(exc)), parent=self.app)
