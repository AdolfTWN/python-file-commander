from __future__ import annotations

import re
import uuid
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
from .i18n import tr


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
    selected = {str(path).casefold() for path in paths}
    duplicate_counts = {}
    for path, name in zip(paths, names):
        key = str(path.with_name(name)).casefold()
        duplicate_counts[key] = duplicate_counts.get(key, 0) + 1
    result = []
    for path, name in zip(paths, names):
        target = path.with_name(name) if name else path
        error = ""
        if not name:
            error = "Empty name"
        elif name in {".", ".."} or any(char in INVALID_NAME_CHARS for char in name):
            error = "Invalid name"
        elif name.endswith((" ", ".")):
            error = "Trailing space/dot"
        elif duplicate_counts.get(str(target).casefold(), 0) > 1:
            error = "Duplicate target"
        elif target.exists() and str(target).casefold() not in selected and target != path:
            error = "Target exists"
        elif target == path:
            error = "Unchanged"
        result.append((path, target, error))
    return result


def execute_rename_pairs(pairs: list[tuple[Path, Path]]) -> list[tuple[Path, Path]]:
    """Rename as one batch via temporary names; restore originals if any step fails."""
    records = []
    try:
        for source, target in pairs:
            temporary = source.with_name(f".{source.name}.pfc-rename-{uuid.uuid4().hex}")
            source.rename(temporary)
            records.append({"source": source, "target": target, "current": temporary})
        for record in records:
            record["current"].rename(record["target"])
            record["current"] = record["target"]
    except OSError:
        rollback = []
        for record in records:
            current = record["current"]
            if current.exists():
                temporary = current.with_name(f".{current.name}.pfc-rollback-{uuid.uuid4().hex}")
                try:
                    current.rename(temporary); rollback.append((temporary, record["source"]))
                except OSError:
                    pass
        for temporary, original in rollback:
            try:
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
        ttk.Label(controls, text=tr("Name mask:")).grid(row=0, column=0, sticky="w")
        self.mask_entry = ttk.Entry(controls, textvariable=self.mask_var)
        self.mask_entry.grid(row=0, column=1, columnspan=5, sticky="ew", padx=(4, 8))
        ttk.Label(controls, text=tr("[N] original   [C] counter   [E] extension")).grid(
            row=0, column=6, columnspan=3, sticky="w")
        ttk.Label(controls, text=tr("Find:")).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(controls, textvariable=self.find_var).grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(6, 0))
        ttk.Label(controls, text=tr("Replace:")).grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(controls, textvariable=self.replace_var).grid(row=1, column=3, sticky="ew", padx=(4, 8), pady=(6, 0))
        ttk.Checkbutton(controls, text=tr("Case sensitive"), variable=self.case_var,
                        command=self.update_preview).grid(row=1, column=4, sticky="w", pady=(6, 0))
        ttk.Checkbutton(controls, text=tr("Keep extension"), variable=self.extension_var,
                        command=self.update_preview).grid(row=1, column=5, sticky="w", pady=(6, 0))
        ttk.Label(controls, text=tr("Start:")).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(controls, from_=0, to=999999, textvariable=self.start_var, width=7,
                    command=self.update_preview).grid(row=2, column=1, sticky="w", padx=(4, 8), pady=(6, 0))
        ttk.Label(controls, text=tr("Digits:")).grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Spinbox(controls, from_=1, to=12, textvariable=self.digits_var, width=5,
                    command=self.update_preview).grid(row=2, column=3, sticky="w", padx=(4, 8), pady=(6, 0))
        controls.columnconfigure(1, weight=1); controls.columnconfigure(3, weight=1)
        self.tree = ttk.Treeview(self, columns=("old", "new", "status"), show="headings")
        for column, width in (("old", 360), ("new", 360), ("status", 150)):
            self.tree.heading(column, text=tr(column.title())); self.tree.column(column, width=width)
        self.tree.tag_configure("error", foreground="#a00000")
        self.tree.tag_configure("ok", foreground="#006c3b")
        self.tree.pack(fill="both", expand=True, padx=8)
        bottom = ttk.Frame(self, padding=8); bottom.pack(fill="x")
        self.status = ttk.Label(bottom, anchor="w"); self.status.pack(side="left", fill="x", expand=True)
        self.undo_button = ttk.Button(bottom, text=tr("Ctrl+Z Undo"), command=self.undo)
        self.undo_button.pack(side="right")
        ttk.Button(bottom, text=tr("Close"), command=self.destroy).pack(side="right", padx=4)
        self.apply_button = ttk.Button(bottom, text=tr("Ctrl+Enter Rename"), command=self.apply)
        self.apply_button.pack(side="right")
        for variable in (self.mask_var, self.find_var, self.replace_var, self.start_var, self.digits_var):
            variable.trace_add("write", lambda *_args: self.after_idle(self.update_preview))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Control-Return>", lambda _event: self.apply())
        self.bind("<Control-z>", lambda _event: self.undo())
        self.update_preview(); self.after_idle(self._activate)

    def _activate(self):
        self.deiconify(); self.lift(); self.focus_force(); self.mask_entry.focus_set(); self.mask_entry.selection_range(0, "end")

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
                             tags=("error" if problem and problem != "Unchanged" else "ok",))
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
