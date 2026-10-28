from __future__ import annotations

import re
import os
import uuid
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
from .i18n import retranslate_widgets, tr
from .tabs import color_scheme
from .tooltip import ToolTip
from .settings import readable_check_style
from .flowlayout import FlowToolbar


INVALID_NAME_CHARS = set('<>:"/\\|?*')


def render_rename(path: Path, mask: str, find: str = "", replace: str = "",
                  counter: int = 1, digits: int = 2, case_sensitive: bool = False,
                  keep_extension: bool = True) -> str:
    is_folder = path.is_dir()
    stem = path.name if is_folder else path.stem
    extension = "" if is_folder else path.suffix[1:]
    name = mask.replace("[N]", stem).replace("[E]", extension).replace(
        "[C]", str(counter).zfill(max(1, digits)))
    if find:
        if case_sensitive:
            name = name.replace(find, replace)
        else:
            name = re.sub(re.escape(find), lambda _match: replace, name, flags=re.IGNORECASE)
    if keep_extension and not is_folder and "[E]" not in mask:
        name += path.suffix
    return name


def validate_rename_plan(paths: list[Path], names: list[str]):
    if len(paths) != len(names):
        raise ValueError("Each selected item requires exactly one new name.")
    def invalid(name):
        reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{n}" for p in ("COM", "LPT") for n in "123456789¹²³"}
        return (not name or name in {".", ".."} or
                any(c in INVALID_NAME_CHARS or ord(c) < 32 for c in name) or
                name.split(".")[0].upper() in reserved)
    selected = {str(path).casefold() for path in paths}
    duplicate_counts = {}
    for path, name in zip(paths, names):
        if invalid(name):
            continue
        key = str(path.with_name(name)).casefold()
        duplicate_counts[key] = duplicate_counts.get(key, 0) + 1
    result = []
    for path, name in zip(paths, names):
        target = path if invalid(name) else path.with_name(name)
        error = ""
        if not name:
            error = "Empty name"
        elif invalid(name):
            error = "Invalid name"
        elif name.endswith((" ", ".")):
            error = "Trailing space/dot"
        elif duplicate_counts.get(str(target).casefold(), 0) > 1:
            error = "Duplicate target"
        elif os.path.lexists(target) and str(target).casefold() not in selected and target != path:
            error = "Target exists"
        elif target == path:
            error = "Unchanged"
        result.append((path, target, error))
    return result


def execute_rename_pairs(pairs: list[tuple[Path, Path]]) -> list[tuple[Path, Path]]:
    """Rename as one batch via temporary names; restore originals if any step fails."""
    if any(source.parent != target.parent for source, target in pairs):
        raise OSError("Batch rename cannot change the parent folder.")
    plan = validate_rename_plan([source for source, _ in pairs], [target.name for _, target in pairs])
    errors = [error for _, _, error in plan if error and error != "Unchanged"]
    if errors:
        raise OSError(errors[0])
    records = []
    try:
        for source, target in pairs:
            temporary = source.with_name(f".{source.name}.pfc-rename-{uuid.uuid4().hex}")
            source.rename(temporary)
            records.append({"source": source, "target": target, "current": temporary})
        for record in records:
            if os.path.lexists(record["target"]):
                raise OSError("A rename target appeared after the preview.")
            record["current"].rename(record["target"])
            record["current"] = record["target"]
    except OSError:
        rollback = []
        for record in records:
            current = record["current"]
            if os.path.lexists(current):
                temporary = current.with_name(f".{current.name}.pfc-rollback-{uuid.uuid4().hex}")
                try:
                    current.rename(temporary); rollback.append((temporary, record["source"]))
                except OSError:
                    pass
        for temporary, original in rollback:
            try:
                if os.path.lexists(original):
                    continue  # Preserve an externally created file and the recovery copy.
                temporary.rename(original)
            except OSError:
                pass
        raise
    return [(target, source) for source, target in pairs]


class MultiRenameWindow(tk.Toplevel):
    def __init__(self, master, paths, undo_stack, on_changed):
        super().__init__(master)
        self.paths = list(paths); self.undo_stack = undo_stack; self.on_changed = on_changed
        self.title(tr("PFC Multi-Rename"))
        self.geometry("980x650"); self.minsize(700, 470); self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.mask_var = tk.StringVar(value="[N]")
        self.find_var, self.replace_var = tk.StringVar(), tk.StringVar()
        self.start_var, self.digits_var = tk.IntVar(value=1), tk.IntVar(value=2)
        self.case_var, self.extension_var = tk.BooleanVar(value=False), tk.BooleanVar(value=True)
        controls = ttk.Frame(self, padding=8); controls.pack(fill="x")
        self.naming_tools = FlowToolbar(controls)
        self.naming_tools.pack(fill='x')
        self.replace_tools = FlowToolbar(controls)
        self.replace_tools.pack(fill='x',pady=(3,0))
        def field(bar, label, variable, *, spin=None):
            group=ttk.Frame(bar)
            ttk.Label(group,text=tr(label)).pack(side='left',padx=(0,4))
            entry=(ttk.Spinbox(group,from_=spin[0],to=spin[1],textvariable=variable,
                               width=7 if spin[1]==999999 else 3,command=self.update_preview) if spin else
                   ttk.Entry(group,textvariable=variable,width=10))
            entry.pack(side='left',fill='x',expand=True)
            bar.add(group,expand=spin is None)
            return entry
        self.mask_entry = field(self.naming_tools,'Name mask:',self.mask_var)
        ToolTip(self.mask_entry, lambda: tr('[N] original   [C] counter   [E] extension'))
        extension=ttk.Checkbutton(self.naming_tools,text=tr('Keep extension'),variable=self.extension_var,
                                  command=self.update_preview)
        self.naming_tools.add(extension)
        field(self.naming_tools,'Start:',self.start_var,spin=(0,999999))
        field(self.naming_tools,'Digits:',self.digits_var,spin=(1,12))
        self.find_entry=field(self.replace_tools,'Find:',self.find_var)
        self.replace_entry=field(self.replace_tools,'Replace:',self.replace_var)
        case = ttk.Checkbutton(self.replace_tools, text='Aa', variable=self.case_var, command=self.update_preview)
        self.replace_tools.add(case)
        ToolTip(case, lambda: tr('Case sensitive'))
        self.tree = ttk.Treeview(self, columns=("old", "new", "status"), show="headings")
        for column, width in (("old", 360), ("new", 360), ("status", 150)):
            self.tree.heading(column, text=tr(column.title())); self.tree.column(column, width=width)
        self.tree.tag_configure("error", foreground="#a00000")
        self.tree.tag_configure("ok", foreground="#006c3b")
        self.tree.pack(fill="both", expand=True, padx=8)
        bottom = ttk.Frame(self, padding=8); bottom.pack(side='bottom', fill="x", before=controls)
        self.status = ttk.Label(bottom, anchor="w", width=1); self.status.pack(side="left", fill="x", expand=True)
        ToolTip(self.status, lambda: self.status.cget('text'))
        self.undo_button = ttk.Button(bottom, text=tr("Ctrl+Z Undo"), width=0, command=self.undo)
        self.undo_button.pack(side="right")
        self.close_button = ttk.Button(bottom, text=tr("Close"), width=0, command=self.destroy)
        self.close_button.pack(side="right", padx=4)
        self.apply_button = ttk.Button(bottom, text=tr("Ctrl+Enter Rename"), width=0, command=self.apply)
        self.apply_button.pack(side="right")
        ToolTip(self.apply_button, lambda: tr('Ctrl+Enter Rename'))
        ToolTip(self.undo_button, lambda: tr('Ctrl+Z Undo'))
        bottom.bind('<Configure>', self._layout_actions)
        for variable in (self.mask_var, self.find_var, self.replace_var, self.start_var, self.digits_var):
            variable.trace_add("write", lambda *_args: self.after_idle(self.update_preview))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Control-Return>", lambda _event: self.apply())
        self.bind("<Control-z>", lambda _event: self.undo())
        self.apply_color_scheme(getattr(master, "palette", color_scheme("light")))
        self.update_preview(); self.after_idle(self._activate)

    def apply_color_scheme(self, palette) -> None:
        self.palette = palette
        bg = self.winfo_rgb(palette.get('window', '#eeeeee'))
        style = readable_check_style(self, tkfont.nametofont('TkDefaultFont'),
                                      sum(bg)/3 < 32768, prefix='RenameCheck')
        pending = [self]
        while pending:
            widget = pending.pop(); pending.extend(widget.winfo_children())
            if isinstance(widget, ttk.Checkbutton): widget.configure(style=style)
        self.configure(background=palette["window"])
        dark = palette["window"] == "#20262c"
        self.tree.tag_configure("error", foreground="#ff7770" if dark else "#a00000")
        self.tree.tag_configure("ok", foreground="#73d6a1" if dark else "#006c3b")
        self.tree.tag_configure('unchanged',foreground=palette['text'])

    def _layout_actions(self, event):
        font = tkfont.nametofont('TkDefaultFont')
        needed = sum(font.measure(tr(label)) for label in ('Ctrl+Enter Rename', 'Ctrl+Z Undo', 'Close'))+100
        compact = event.width < needed
        self.apply_button.configure(text=tr('Rename' if compact else 'Ctrl+Enter Rename'))
        self.undo_button.configure(text=tr('Undo' if compact else 'Ctrl+Z Undo'))

    def _activate(self):
        self.deiconify(); self.lift(); self.focus_force(); self.mask_entry.focus_set(); self.mask_entry.selection_range(0, "end")

    def apply_language(self, old_language: str) -> None:
        retranslate_widgets(self, old_language)
        self.title(tr("PFC Multi-Rename"))
        for column in ("old", "new", "status"):
            self.tree.heading(column, text=tr(column.title()))
        self.naming_tools.schedule(); self.replace_tools.schedule()
        self.update_preview()

    def _plan(self):
        try:
            start, digits = self.start_var.get(), self.digits_var.get()
        except tk.TclError:
            start, digits = 1, 2
        names = [render_rename(path, self.mask_var.get(), self.find_var.get(), self.replace_var.get(),
                               start + index, digits, self.case_var.get(), self.extension_var.get())
                 for index, path in enumerate(self.paths)]
        return validate_rename_plan(self.paths, names)

    def update_preview(self):
        if not self.winfo_exists(): return
        plan = self._plan(); self.tree.delete(*self.tree.get_children())
        errors = changed = 0
        for source, target, problem in plan:
            if problem and problem != "Unchanged": errors += 1
            if not problem: changed += 1
            self.tree.insert("", "end", values=(source.name, target.name, tr(problem or "Ready")),
                             tags=('unchanged' if problem=='Unchanged' else 'error' if problem else 'ok',))
        self.status.configure(text=tr("{changed} rename(s), {errors} error(s)", changed=changed, errors=errors))
        self.apply_button.state(["disabled"] if errors or not changed else ["!disabled"])
        self.undo_button.state(["!disabled"] if self.undo_stack else ["disabled"])

    def apply(self):
        plan = self._plan()
        pairs = [(source, target) for source, target, problem in plan if not problem]
        errors = [problem for _source, _target, problem in plan if problem and problem != "Unchanged"]
        if errors or not pairs: return "break"
        preview = "\n".join(f"{source.name}  →  {target.name}" for source, target in pairs[:30])
        if len(pairs) > 30: preview += f"\n… and {len(pairs) - 30} more"
        if not messagebox.askyesno(tr("Multi-Rename"),
                                   tr("Rename {count} item(s)?", count=len(pairs)) + f"\n\n{preview}", parent=self):
            return "break"
        try:
            undo = execute_rename_pairs(pairs)
        except OSError as exc:
            messagebox.showerror(tr("Multi-Rename failed"), str(exc), parent=self); return "break"
        self.undo_stack.append(undo); self.paths = [target for _source, target in pairs]
        self.on_changed(); self.update_preview()
        messagebox.showinfo(tr("Multi-Rename"), tr("Renamed {count} item(s).", count=len(pairs)), parent=self)
        return "break"

    def undo(self):
        if not self.undo_stack: return "break"
        pairs = self.undo_stack[-1]
        problems = validate_rename_plan([source for source, _target in pairs],
                                        [target.name for _source, target in pairs])
        if any(problem and problem != "Unchanged" for _source, _target, problem in problems):
            messagebox.showerror(tr("Undo Multi-Rename"), tr("Undo target is no longer available."), parent=self)
            return "break"
        try:
            execute_rename_pairs(pairs)
        except OSError as exc:
            messagebox.showerror(tr("Undo Multi-Rename"), str(exc), parent=self); return "break"
        self.undo_stack.pop(); self.paths = [target for _source, target in pairs]
        self.on_changed(); self.update_preview()
        messagebox.showinfo(tr("Undo Multi-Rename"), tr("Restored {count} item(s).", count=len(pairs)), parent=self)
        return "break"
