from __future__ import annotations

import io
import json
import keyword
import os
import re
import time
import tokenize
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk
from urllib.parse import quote
from .tooltip import install_button_tooltips, ToolTip
from .i18n import retranslate_widgets, tr, get_language
from .tabs import color_scheme
from .markdownblocks import markdown_blocks, property_rows, render_grid
from .mdlinks import markdown_destination, read_linked_markdown
from .mdjobs import MarkdownJobs, limit_markdown_worker_memory
from .mdworkspace import wiki_destination, scan_markdown_workspace
from .mdworkspaceui import MarkdownWorkspaceDialog
from .workflowdata import WorkflowRecords, reading_anchor, resolve_reading_anchor
from .workflows import WorkflowPicker


TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".tsv", ".log", ".py", ".ini", ".json", ".xml",
    ".yaml", ".yml", ".html", ".htm", ".css", ".js", ".ps1", ".bat", ".cmd",
    ".sql", ".srt", ".cfg", ".conf",
}
TEXT_LIMIT = 8 * 1024 * 1024
HEX_LIMIT = 1024 * 1024
SYNTAX_BATCH_SIZE = 600

CODE_EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".php": "PHP",
    ".sql": "SQL", ".ps1": "PowerShell", ".sh": "Shell",
    ".bat": "Batch", ".cmd": "Batch", ".json": "JSON",
    ".xml": "XML", ".html": "HTML", ".htm": "HTML", ".xhtml": "HTML",
    ".svg": "SVG", ".css": "CSS", ".scss": "SCSS",
    ".yaml": "YAML", ".yml": "YAML", ".ini": "INI",
    ".cfg": "Config", ".conf": "Config", ".md": "Markdown",
}

COMMON_KEYWORDS = set("""
abstract as async await break case catch class const continue def default delete do
else enum except export extends false finally for from function if import in
interface lambda let match namespace new nil none null package pass private
protected public raise return self static struct super switch this throw true try
type typeof using var void while with yield select range where
""".split())


def _line_offsets(text: str) -> list[int]:
    offsets, total = [0], 0
    for line in text.splitlines(keepends=True):
        total += len(line); offsets.append(total)
    return offsets


def syntax_spans(text: str, suffix: str) -> list[tuple[int, int, str]]:
    """Return lightweight syntax spans without requiring third-party packages."""
    suffix = suffix.casefold()
    if suffix == ".py":
        offsets = _line_offsets(text)
        spans = []
        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                if token.type not in (tokenize.COMMENT, tokenize.STRING, tokenize.NUMBER,
                                      tokenize.NAME, tokenize.OP):
                    continue
                tag = {
                    tokenize.COMMENT: "syntax_comment", tokenize.STRING: "syntax_string",
                    tokenize.NUMBER: "syntax_number", tokenize.OP: "syntax_operator",
                }.get(token.type)
                if token.type == tokenize.NAME and keyword.iskeyword(token.string):
                    tag = "syntax_keyword"
                if tag and token.start[0] <= len(offsets) and token.end[0] <= len(offsets):
                    start = offsets[token.start[0] - 1] + token.start[1]
                    end = offsets[token.end[0] - 1] + token.end[1]
                    spans.append((start, end, tag))
        except (tokenize.TokenError, IndentationError):
            pass
        return spans

    spans = []
    comment_pattern = (r"(?m)(?://|;|--).*?$|/\*[\s\S]*?\*/|<!--[\s\S]*?-->"
                       if suffix == ".md" else
                       r"(?m)(?://|#|;|--).*?$|/\*[\s\S]*?\*/|<!--[\s\S]*?-->")
    patterns = [
        ("syntax_comment", comment_pattern),
        ("syntax_string", r"""(?s:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')"""),
        ("syntax_number", r"\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b"),
    ]
    if suffix in {".xml", ".html", ".htm", ".xhtml", ".svg"}:
        patterns.append(("syntax_keyword", r"</?[\w:-]+|/?>"))
    elif suffix == ".md":
        patterns.extend([
            ("syntax_heading", r"(?m)^#{1,6}\s+.*$"),
            ("syntax_keyword", r"(?m)^(?:\s*[-*+]\s+|\s*\d+\.\s+|>\s+)|`{1,3}"),
            ("syntax_link", r"\[[^\]]+\]\([^)]+\)"),
        ])
    else:
        words = COMMON_KEYWORDS
        patterns.append(("syntax_keyword", r"\b(?:" + "|".join(sorted(map(re.escape, words))) + r")\b"))
    occupied = [False] * len(text)
    for tag, pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start, end = match.span()
            if start < end and not any(occupied[start:end]):
                spans.append((start, end, tag))
                occupied[start:end] = [True] * (end - start)
    return spans


def markdown_document(text: str):
    """Render a bounded, read-only document model; no filesystem/link lookups."""
    output, spans, length = [], [], 0
    headings, links, tasks = [], [], [0,0]
    callout = None

    def append(value: str, tag: str | None = None) -> None:
        nonlocal length
        start = length; output.append(value); length += len(value)
        if tag and value: spans.append((start, start + len(value), tag))
        if length>2*1024*1024 or len(spans)>20000:
            raise ValueError('Markdown rendering limit reached')

    def inline(value: str) -> None:
        pattern = re.compile(r"(\*\*.+?\*\*|__.+?__|`[^`]+`|\[\[[^\]\n]+\]\]|\[[^\]\n]+\]\([^\n)]+\)|(?<!\*)\*[^*]+\*)")
        cursor = 0
        for match in pattern.finditer(value):
            append(value[cursor:match.start()])
            token = match.group()
            if token.startswith(("**", "__")):
                append(token[2:-2], "markdown_bold")
            elif token.startswith("`"):
                append(token[1:-1], "markdown_code")
            elif token.startswith("["):
                if token.startswith('[['):
                    try: wiki=wiki_destination(token[2:-2])
                    except ValueError:
                        append(token);cursor=match.end();continue
                    label=wiki['label'];url=wiki['href']
                else:
                    label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()
                start=length
                append(label, "markdown_link")
                # Images remain literal text, never embeds or clickable includes.
                if not (match.start()>0 and value[match.start()-1]=='!'):
                    if len(links)>=2000: raise ValueError('Markdown rendering limit reached')
                    links.append({'start':start,'end':length,'href':url,'label':label})
                    if token.startswith('[[') and wiki['name']:
                        links[-1]['wiki']=token[2:-2]
                append(f" ({url})", "markdown_url")
            else:
                append(token[1:-1], "markdown_italic")
            cursor = match.end()
        append(value[cursor:])

    for kind, raw in markdown_blocks(text):
        if length>2*1024*1024 or len(spans)>20000:
            raise ValueError('Markdown rendering limit reached')
        if kind == 'properties':
            start=length
            append(tr('Properties (read-only)')+'\n', 'markdown_h3')
            body=length
            append(render_grid([[tr('Property'),tr('Value')]]+property_rows(raw)), 'markdown_table')
            headings.append({'title':tr('Properties (read-only)'),'level':0,'start':start,'body':body,'end':length})
            continue
        if kind == 'table':
            rows, aligns = raw
            # Flatten inline presentation inside a grid, preserving all words,
            # URLs and line breaks. Keep a uniform fixed font for alignment.
            plain_rows=[]
            for row in rows:
                plain=[]
                for value in row:
                    start, old_length, old_spans, old_links = len(output), length, len(spans),len(links)
                    inline(re.sub(r'<br\s*/?>', '\n', value, flags=re.I))
                    plain.append(''.join(output[start:]))
                    del output[start:]; del spans[old_spans:];del links[old_links:]; length=old_length
                plain_rows.append(plain)
            append(render_grid(plain_rows, aligns), 'markdown_table')
            continue
        if kind == 'code':
            callout=None
            append(raw + "\n", "markdown_code")
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", raw)
        if heading:
            callout=None
            start = length; inline(heading.group(2)); append("\n")
            spans.append((start, length - 1,
                          f"markdown_h{min(3, len(heading.group(1)))}"))
            if len(headings)>=2000: raise ValueError('Markdown rendering limit reached')
            headings.append({'title':heading.group(2),'level':len(heading.group(1)),
                             'start':start,'body':length})
        elif re.match(r'^\s*[-*+]\s+\[([ xX])\]\s+',raw):
            callout=None
            match=re.match(r'^(\s*)[-*+]\s+\[([ xX])\]\s+(.*)',raw)
            done=match.group(2).lower()=='x';tasks[0]+=int(done);tasks[1]+=1
            start=length;append(match.group(1)+('☑ ' if done else '☐ '));inline(match.group(3));append('\n')
            spans.append((start,length,'markdown_task_done' if done else 'markdown_task'))
        elif re.match(r"^\s*[-*+]\s+", raw):
            callout=None
            append("• ", "markdown_bullet"); inline(re.sub(r"^\s*[-*+]\s+", "", raw)); append("\n")
        elif raw.startswith(">"):
            value=raw[1:].lstrip();match=re.match(r'^\[!([\w-]+)\][+-]?(?:\s+(.*))?$',value)
            start=length
            if match:
                name=match.group(1).lower();title=match.group(2) or name.title()
                callout='warning' if name in ('warning','danger','error','failure','bug') else 'tip' if name in ('tip','success','done') else 'note'
                append({'warning':'⚠ ','tip':'✓ ','note':'ℹ '}[callout]+name.upper()+' — ')
                inline(title);append('\n')
            else:
                append('│ ');inline(value);append('\n')
            spans.append((start,length,'markdown_callout_'+callout if callout else 'markdown_quote'))
        elif re.match(r"^\s*(?:---+|\*\*\*+)\s*$", raw):
            append("────────────────────────\n", "markdown_rule")
        else:
            callout=None
            inline(raw); append("\n")
    for index,item in enumerate(headings):
        if 'end' not in item:
            item['end']=next((h['start'] for h in headings[index+1:] if h['level']<=item['level']),length)
    if length>2*1024*1024 or len(spans)>20000: raise ValueError('Markdown rendering limit reached')
    return {'content':''.join(output),'spans':spans,'headings':headings,'links':links,'tasks':tasks}


def render_markdown(text: str) -> tuple[str, list[tuple[int, int, str]]]:
    model=markdown_document(text)
    return model['content'],model['spans']


def markdown_worker_main():
    """Private JSON protocol; invoked in a dedicated, non-GUI subprocess."""
    import sys
    from_locale=globals().get('set_language')
    if from_locale is None:
        from .i18n import set_language as from_locale
    memory_limited=limit_markdown_worker_memory()
    for raw in sys.stdin.buffer:
        request={}
        try:
            request=json.loads(raw);path=Path(request['path'])
            from_locale(request.get('language','en'))
            if request.get('action')=='workspace':
                if not memory_limited: raise ValueError('Memory protection unavailable')
                result=scan_markdown_workspace(request,markdown_document,decode_text)
            elif request.get('action')=='stat':
                if request.get('boundary'):
                    _,signature=read_linked_markdown(path,request['boundary'],-1)
                else:
                    info=path.stat();signature=[info.st_mtime_ns,info.st_size]
                result={'signature':signature}
            else:
                if request.get('boundary'):
                    data,signature=read_linked_markdown(path,request['boundary'],TEXT_LIMIT)
                else:
                    with path.open('rb') as stream:
                        info=os.fstat(stream.fileno())
                        if not __import__('stat').S_ISREG(info.st_mode): raise ValueError('Target is not a regular file')
                        signature=(info.st_mtime_ns,info.st_size);data=stream.read(TEXT_LIMIT+1)
                truncated=len(data)>TEXT_LIMIT
                source,encoding=decode_text(data[:TEXT_LIMIT]);notice=''
                rendered=bool(request.get('rendered'))
                if rendered:
                    try:
                        if not memory_limited: raise ValueError('Memory protection unavailable')
                        if len(source)>512*1024: raise ValueError('Markdown rendering limit reached')
                        result=markdown_document(source)
                    except (ValueError,RecursionError,MemoryError):
                        result={'content':source[:512*1024],'spans':[]};rendered=False
                        truncated=truncated or len(source)>512*1024
                        notice='Rendering limit reached; showing source text' if memory_limited else 'Memory protection unavailable; showing source text'
                else:
                    result={'content':source,'spans':syntax_spans(source,'.md')
                            if request.get('highlight') and memory_limited and len(source)<=512*1024 else []}
                result.update(signature=signature,encoding=encoding,truncated=truncated,
                              rendered=rendered,notice=notice,size=signature[1])
            result['id']=request['id']
        except Exception as exc:
            result={'id':request.get('id'),'error':str(exc),'error_type':type(exc).__name__}
        sys.stdout.buffer.write((json.dumps(result,ensure_ascii=True)+'\n').encode('utf-8'))
        sys.stdout.buffer.flush()


def looks_text(path: Path, sample: bytes) -> bool:
    if path.suffix.casefold() in TEXT_EXTENSIONS:
        return True
    if not sample:
        return True
    if sample.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
        return True
    return b"\x00" not in sample and sum(byte < 9 or 13 < byte < 32 for byte in sample) / len(sample) < 0.05


def decode_text(data: bytes) -> tuple[str, str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace"), "UTF-16"
    try:
        return data.decode("utf-8-sig"), "UTF-8"
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), "Windows-1252"


def render_hex(data: bytes) -> str:
    lines = []
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]
        hexadecimal = " ".join(f"{byte:02X}" for byte in chunk)
        printable = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:08X}  {hexadecimal:<47}  |{printable}|\n")
    return "".join(lines)


class PreviewPage(tk.Frame):
    def __init__(self, master, config, save_config, files, selected,
                 extension_effect: bool = True, *, host, lazy=False) -> None:
        super().__init__(master)
        self.host = host
        self._loaded = not lazy
        self.config_data, self.save_config = config, save_config
        self.files = list(files)
        self.index = self.files.index(selected) if selected in self.files else 0
        self.mode_values = {tr("Auto"): "Auto", tr("Text"): "Text", tr("Hex"): "Hex"}
        self.mode_var = tk.StringVar(value=tr("Auto"))
        self.wrap_var = tk.BooleanVar(value=config.getboolean("preview", "wrap", fallback=False))
        self.case_var = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar()
        self.extension_effect = bool(extension_effect)
        self.markdown_values = {tr("Markdown Source"): "source", tr("Rendered"): "rendered"}
        self.markdown_var = tk.StringVar(value=tr("Rendered"))
        self.matches = []
        self.match_index = -1
        self._signature = None
        self._refresh_job = None
        self._span_job = None
        self._pending_spans = []
        self._md_jobs=MarkdownJobs(Path(__file__).absolute(),bool(__package__))
        self._md_request=None;self._md_queued=None;self._md_insert=None
        self._md_model={};self._md_history=[];self._linked_path=None
        self._md_boundary=Path(os.path.abspath(selected)).parent
        self._md_folded=set();self._md_poll_job=None;self._md_last_probe=0
        self._md_display_path=None;self._md_signature=None
        self._md_auto_suspended=False
        self.bind('<Destroy>',lambda e:self._md_jobs.close() if e.widget is self else None,add='+')
        self.title(tr("PFC Preview"))

        toolbar = ttk.Frame(self, padding=(6, 5)); toolbar.pack(fill="x")
        file_row = ttk.Frame(toolbar); file_row.pack(fill="x")
        ttk.Button(file_row, text=tr("File <<"), command=self.previous_file).pack(side="left")
        ttk.Button(file_row, text=tr("File >>"), command=self.next_file).pack(side="left", padx=(3, 10))
        ttk.Label(file_row, text=tr("View:")).pack(side="left", padx=(4, 3))
        self.mode_combo = ttk.Combobox(file_row, width=7, state="readonly", textvariable=self.mode_var,
                                       values=tuple(self.mode_values))
        self.mode_combo.pack(side="left")
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self.load())
        ttk.Checkbutton(file_row, text=tr("Wrap"), variable=self.wrap_var,
                        command=self.set_wrap).pack(side="left", padx=10)
        self.markdown_frame = ttk.Frame(file_row)
        ttk.Label(self.markdown_frame, text="Markdown:").pack(side="left", padx=(2, 3))
        self.markdown_combo = ttk.Combobox(self.markdown_frame, width=10, state="readonly",
                                           textvariable=self.markdown_var,
                                           values=tuple(self.markdown_values))
        self.markdown_combo.pack(side="left")
        self.markdown_combo.bind("<<ComboboxSelected>>", lambda _event: self.load())
        find_row = ttk.Frame(toolbar); find_row.pack(fill="x", pady=(4, 0))
        ttk.Label(find_row, text=tr("Find:")).pack(side="left", padx=(0, 3))
        self.search = ttk.Entry(find_row, textvariable=self.search_var, width=24)
        self.search.pack(side="left", fill="x", expand=True)
        self.search.bind("<Return>", lambda _event: self.find_next())
        self.search.bind("<Shift-Return>", lambda _event: self.find_previous())
        find_actions = ttk.Frame(toolbar); find_actions.pack(fill="x", pady=(3, 0))
        ttk.Button(find_actions, text=tr("Find Prev"), command=self.find_previous).pack(side="left")
        ttk.Button(find_actions, text=tr("Find Next"), command=self.find_next).pack(side="left", padx=(3, 0))
        ttk.Checkbutton(find_actions, text=tr("Case sensitive"), variable=self.case_var,
                        command=self.find_all).pack(side="left", padx=(8, 0))
        self.md_tools=ttk.Frame(toolbar)
        self.md_back=ttk.Button(self.md_tools,text='←',width=2,command=self.markdown_back)
        self.md_outline=ttk.Combobox(self.md_tools,width=1,state='readonly')
        self.md_outline.bind('<<ComboboxSelected>>',lambda e:self.markdown_heading())
        self.md_fold=ttk.Button(self.md_tools,text=tr('Fold'),width=5,command=self.markdown_fold)
        self.md_more=ttk.Menubutton(self.md_tools,text=tr('Reading'),width=7)
        self.md_menu=tk.Menu(self.md_more,tearoff=False,font='TkMenuFont')
        self.md_more.configure(menu=self.md_menu)
        self.md_task_label=ttk.Label(self.md_tools)
        self.md_cancel=ttk.Button(self.md_tools,text=tr('Cancel'),width=7,command=self.cancel_markdown)
        self._md_tools_narrow=None
        self.md_tools.columnconfigure(1,weight=1)
        self.md_tools.bind('<Configure>',lambda e:self._layout_markdown_tools())
        self._layout_markdown_tools()
        ToolTip(self.md_back,lambda:tr('Back to the previous Markdown document (Alt+Left)'),delay=700)
        ToolTip(self.md_outline,lambda:tr('Sections in this document only; no folder scan'),delay=700)
        ToolTip(self.md_fold,lambda:tr('Fold or expand the selected section; search and copy include its text'),delay=700)
        ToolTip(self.md_task_label,lambda:tr('Completed / total tasks; read-only'),delay=700)
        ToolTip(self.md_more,self._markdown_boundary_label,delay=700)

        frame = ttk.Frame(self); frame.pack(fill="both", expand=True)
        self.text = tk.Text(frame, wrap="word" if self.wrap_var.get() else "none", undo=False,
                            font=tkfont.nametofont("TkFixedFont"), padx=8, pady=6)
        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        horizontal.pack(side="bottom", fill="x")
        self.text.pack(side="left", fill="both", expand=True); vertical.pack(side="right", fill="y")
        self.text.tag_configure("match", background="#fff0a6")
        self.text.tag_configure("current_match", background="#ffb347")
        self.text.bind('<Control-a>',self._copy_select_all)
        self.text.bind('<<Copy>>',self._copy_preview)
        self.text.bind('<Control-c>',self._copy_preview)
        self.bind('<F5>',lambda e:self.load())
        self._configure_effect_fonts()
        self.status = ttk.Label(self, anchor="w", padding=(7, 4)); self.status.pack(fill="x")
        self.apply_color_scheme(getattr(host.master, "palette", color_scheme("light")))
        install_button_tooltips(self)
        if not lazy: self.load()
        self._schedule_refresh()
        self._md_poll_job=self.after(40,self._poll_markdown)

    def title(self, value):
        self.page_title = value
        if self.host.active_page is self:
            self.host.title(value)
            self.host.path_label.configure(text=str(self.path))

    def _markdown_mode(self):
        return self.path.suffix.casefold()=='.md' and self.mode_values.get(self.mode_var.get(),self.mode_var.get())!='Hex'

    def _layout_markdown_tools(self):
        fixed=(self.md_back,self.md_fold,self.md_more,self.md_task_label,self.md_cancel)
        narrow=self.md_tools.winfo_width()<sum(w.winfo_reqwidth()+6 for w in fixed)+100
        if narrow==self._md_tools_narrow:return
        self._md_tools_narrow=narrow
        self.md_back.grid(row=0,column=0,sticky='w')
        self.md_outline.grid(row=0,column=1,sticky='ew',padx=3)
        self.md_fold.grid(row=0,column=2,sticky='e')
        self.md_more.grid(row=1 if narrow else 0,column=0 if narrow else 3,
                          columnspan=2 if narrow else 1,sticky='w',padx=3)
        self.md_task_label.grid(row=1 if narrow else 0,column=2 if narrow else 4,sticky='w',padx=4)
        self.md_cancel.grid(row=1 if narrow else 0,column=3 if narrow else 5,sticky='e')

    def _archive_markdown(self):
        # Use the archive session already owned by Commander. No target lookup.
        for session in getattr(self.host.master,'_archive_sessions',[]):
            root=getattr(session,'root',None)
            if root is not None:
                try: Path(os.path.abspath(self.path)).relative_to(Path(os.path.abspath(root)));return True
                except ValueError: pass
        return any(part.startswith('pfc-archive-') for part in self.path.parts)

    def _markdown_boundary_label(self):
        if self._archive_markdown():return tr('Archive preview: same-document anchors only')
        return tr('Link boundary: ')+str(self._md_boundary)

    def _queue_markdown(self,path=None,*,navigation=False,fragment='',restore=None,probe=False,guarded=False):
        if self._md_jobs.pending:
            self._md_jobs.cancel()
        self._md_insert=None
        if self._span_job is not None:
            self.after_cancel(self._span_job);self._span_job=None
        path=Path(path or self.path)
        request={'path':str(path),'action':'stat' if probe else 'load','language':get_language(),
                 'highlight':self.extension_effect,
                 'rendered':self.extension_effect and self.markdown_values.get(self.markdown_var.get())=='rendered'}
        if navigation or probe or guarded or self._linked_path is not None:
            request['boundary']=str(self._md_boundary)
        context={'request':request,'navigation':navigation,'fragment':fragment,'restore':restore,
                 'probe':probe,'view':self.text.yview()[0]}
        self._md_request=None;self._md_queued=context
        self._md_auto_suspended=False
        self.md_tools.pack(fill='x',pady=(3,0))
        self.markdown_frame.pack(side='left',padx=(4,0))
        self.md_cancel.state(['!disabled'])
        if not probe: self.status.configure(text=tr('Loading Markdown…'))

    def cancel_markdown(self):
        if self._md_insert:
            self._md_model={};self._md_display_path=None
            self.text.configure(state='normal');self.text.delete('1.0','end');self.text.configure(state='disabled')
            self.md_outline.configure(values=[]);self.md_task_label.configure(text='')
        self._md_jobs.cancel();self._md_request=None;self._md_queued=None;self._md_insert=None
        self.md_cancel.state(['disabled'])
        self.text.configure(state='disabled')
        self.status.configure(text=tr('Preview canceled; press F5 to retry'))
        self._md_last_probe=time.monotonic()
        self._md_auto_suspended=True

    def _poll_markdown(self):
        self._md_poll_job=None
        try:
            self._md_jobs.reap()
            if self._md_queued and not self._md_jobs.pending and not self._md_jobs.retiring:
                context=self._md_queued
                if self._md_jobs.submit(context['request']):
                    self._md_request=context;self._md_queued=None
            result=self._md_jobs.poll()
            if result is not None and self._md_request is not None:
                context=self._md_request;self._md_request=None
                self.md_cancel.state(['disabled'])
                if 'error' in result:
                    self.status.configure(text=(tr('Automatic refresh paused; use F5') if context['probe']
                        else tr('Cannot preview file'))+': '+tr(result['error']))
                    self._md_last_probe=time.monotonic()
                    self._md_auto_suspended=True
                elif context['probe']:
                    if result['signature']!=self._md_signature:
                        self._queue_markdown(restore=self.text.yview()[0],guarded=True)
                else:
                    self._begin_markdown_result(result,context)
            if self._md_jobs.pending and time.monotonic()-self._md_jobs.started>5:
                self.cancel_markdown()
                self.status.configure(text=tr('Preview timed out; press F5 to retry'))
            if self._md_insert: self._insert_markdown_chunk()
        except (OSError,ValueError) as exc:
            self.cancel_markdown();self.status.configure(text=str(exc))
        if self.winfo_exists(): self._md_poll_job=self.after(40,self._poll_markdown)

    def _begin_markdown_result(self,result,context):
        # Do not replace the old document until the worker has succeeded.
        self._remember_markdown_position()
        if context['navigation']:
            self._md_history.append((str(self.path),context['view'],bool(self._linked_path),str(self._md_boundary)))
            self._md_history=self._md_history[-20:]
            self._linked_path=Path(context['request']['path'])
        elif context.get('back'):
            self._linked_path=Path(context['request']['path']) if context['back'][2] else None
            self._md_history.pop()
        if context.get('bookmark_boundary'):
            self._md_boundary=Path(context['bookmark_boundary'])
        elif context.get('back') and len(context['back']) > 3:
            self._md_boundary=Path(context['back'][3])
        self._md_display_path=Path(context['request']['path'])
        self._md_signature=result['signature'];self._md_model=result;self._md_folded.clear()
        self.text.configure(state='normal');self.text.delete('1.0','end')
        for tag in self.text.tag_names():
            if tag.startswith(('md_link_','md_fold_')): self.text.tag_delete(tag)
        self.text.configure(state='disabled')
        self._md_insert={'result':result,'context':context,'offset':0}
        self.md_cancel.state(['!disabled'])
        self.title(tr('PFC Preview')+' — '+self._md_display_path.name)
        self.status.configure(text=tr('Rendering Markdown…'))

    def _insert_markdown_chunk(self):
        job=self._md_insert;result=job['result'];content=result['content'];offset=job['offset']
        self.text.configure(state='normal')
        self.text.insert('end',content[offset:offset+65536])
        self.text.configure(state='disabled');job['offset']+=65536
        if job['offset']<len(content): return
        self._md_insert=None
        self.md_cancel.state(['disabled'])
        # Text's '+Nc' modifier counts Unicode characters, unlike Tcl string
        # length / Text.count, which can count UTF-16 units. Keep Python offsets.
        self._apply_spans(result['spans'])
        for number,item in enumerate(result.get('links',[])):
            tag=f'md_link_{number}'
            self.text.tag_add(tag,f"1.0+{item['start']}c",f"1.0+{item['end']}c")
            self.text.tag_bind(tag,'<Control-ButtonRelease-1>',lambda e,n=number:self.follow_markdown_link(n))
            self.text.tag_bind(tag,'<Enter>',lambda e,v=item:self._describe_markdown_link(v))
        headings=result.get('headings',[])
        self.md_outline.configure(values=[('  '*max(0,h['level']-1))+h['title']+f'  [{i+1}]' for i,h in enumerate(headings)])
        self.md_outline.set(tr('Sections')+(' *' if result.get('truncated') else ''))
        self.md_outline.state(['!disabled'] if headings else ['disabled'])
        self.md_fold.state(['!disabled'] if headings else ['disabled'])
        self.md_back.state(['!disabled'] if self._md_history else ['disabled'])
        self.md_menu.delete(0,'end')
        self.md_menu.add_command(label=tr('Expand all'),command=self.markdown_expand_all)
        self.md_menu.add_command(label=tr('Markdown Source') if result.get('rendered') else tr('Rendered'),
                                 command=self.toggle_markdown_source,state='normal' if self.extension_effect else 'disabled')
        self.md_menu.add_command(label=tr('Refresh')+'  F5',command=self.load)
        self.md_menu.add_command(label=tr('Bookmarks')+'…', command=self.markdown_bookmarks,
                                 state='normal' if result.get('rendered') and not self._archive_markdown() else 'disabled')
        self.md_menu.add_command(label=tr('Forget reading position'), command=self.forget_reading_position)
        workspace_state='normal' if result.get('rendered') and not self._archive_markdown() else 'disabled'
        self.md_menu.add_command(label=tr('Find Markdown files')+'…',command=self.markdown_workspace,state=workspace_state)
        self.md_menu.add_command(label=tr('Backlinks to this document')+'…',command=lambda:self.markdown_workspace('backlinks'),state=workspace_state)
        self.md_menu.add_command(label=self._markdown_boundary_label(),state='disabled')
        self.md_menu.add_separator()
        for number,item in enumerate(result.get('links',[])[:100]):
            self.md_menu.add_command(label=item['label'][:50]+' → '+item['href'][:70],
                                     command=lambda n=number:self.follow_markdown_link(n))
        if len(result.get('links',[]))>100:
            self.md_menu.add_command(label=tr('More links: use Ctrl+click in text'),state='disabled')
        done,total=result.get('tasks',(0,0))
        self.md_task_label.configure(text=f'☑ {done}/{total}'+(' *' if result.get('truncated') else '') if total else '')
        mode=tr('Markdown rendered') if result.get('rendered') else tr('Markdown Source')
        detail=f"{mode}   {result['size']:,} bytes   {result['encoding']}"
        if result.get('truncated'): detail+='   '+tr('Loaded portion only')
        if result.get('notice'): detail+='   '+tr(result['notice'])
        self.status.configure(text=detail)
        self.find_all()
        context=job['context']
        if context['restore'] is not None: self.text.yview_moveto(context['restore'])
        else: self.text.yview_moveto(0)
        if context['fragment']: self._jump_markdown_fragment(context['fragment'])
        elif context.get('bookmark'):
            self._restore_reading_position(context['bookmark'])
        elif context['restore'] is None and result.get('rendered'):
            saved = next((item['data'] for item in WorkflowRecords(self.config_data, 'reading_positions').read()
                          if item['data'].get('path') == str(self._md_display_path)), None)
            if saved: self._restore_reading_position(saved)

    def _capture_markdown_position(self):
        if (not self._md_model.get('rendered') or self._md_insert or self._archive_markdown()
                or self._md_display_path != self.path):
            raise ValueError(tr('Bookmarks are available for rendered local Markdown documents only.'))
        offset = len(self.text.get('1.0', self.text.index('@0,0')))
        data = reading_anchor(self._md_model, offset, self.text.yview()[0], self._md_signature)
        data.update(path=str(self._md_display_path), boundary=str(self._md_boundary))
        return data

    def _remember_markdown_position(self):
        if not self._md_display_path: return
        try: data = self._capture_markdown_position()
        except ValueError: return
        records = WorkflowRecords(self.config_data, 'reading_positions')
        entries = [r for r in records.read() if r['data'].get('path') != data['path']]
        records.write([{'name': self._md_display_path.name[:80], 'data': data}] + entries)

    def _restore_reading_position(self, data):
        try: kind, value, changed = resolve_reading_anchor(self._md_model, data, self._md_signature)
        except (TypeError, ValueError): return
        if kind == 'offset':
            self._expand_markdown_at(value); self.text.yview(f'1.0+{value}c')
        else: self.text.yview_moveto(value)
        if changed:
            self.status.configure(text=tr('Document changed: restored its section, or the top if the section is missing/ambiguous.'))

    def markdown_bookmarks(self):
        WorkflowPicker(self, 'Bookmarks', WorkflowRecords(self.config_data, 'markdown_bookmarks'),
                        self.save_config, self._capture_markdown_position, self.open_markdown_bookmark,
                        lambda d: str(d.get('path', ''))+'\n'+str(d.get('heading', '')))

    def open_markdown_bookmark(self, data):
        target = Path(data['path']); boundary = Path(data['boundary'])
        if target.suffix.casefold() != '.md': raise ValueError('Only Markdown bookmarks are supported.')
        if target == self._md_display_path and self._md_model.get('rendered'):
            self._restore_reading_position(data); return True
        # Exact explicit target, checked in the bounded worker. No basename
        # search, no synchronous exists/resolve call, no cloud hydration fallback.
        target.relative_to(boundary)
        self._queue_markdown(target, navigation=True, guarded=True)
        self._md_queued['request']['boundary'] = str(boundary)
        self._md_queued['bookmark_boundary'] = str(boundary)
        self._md_queued['bookmark'] = data
        return True

    def forget_reading_position(self):
        records = WorkflowRecords(self.config_data, 'reading_positions')
        records.write([r for r in records.read() if r['data'].get('path') != str(self._md_display_path)])
        self.text.yview_moveto(0); self.save_config()
        self.status.configure(text=tr('Reading position reset to the top'))

    def markdown_heading(self):
        index=self.md_outline.current();headings=self._md_model.get('headings',[])
        if 0<=index<len(headings):
            self._expand_markdown_at(headings[index]['start'])
            self.text.see(f"1.0+{headings[index]['start']}c")

    def toggle_markdown_source(self):
        target='source' if self._md_model.get('rendered') else 'rendered'
        self.markdown_var.set(next(label for label,value in self.markdown_values.items() if value==target))
        self.load()

    def markdown_fold(self):
        index=self.md_outline.current();headings=self._md_model.get('headings',[])
        if not 0<=index<len(headings):
            self.status.configure(text=tr('Choose a section first'));return
        item=headings[index]
        if index in self._md_folded: self._md_folded.remove(index)
        else: self._md_folded.add(index)
        self._update_markdown_folds()
        self.text.see(f"1.0+{item['start']}c")

    def markdown_expand_all(self):
        self._md_folded.clear()
        self._update_markdown_folds()

    def _update_markdown_folds(self):
        self.text.tag_remove('md_fold_hidden','1.0','end')
        for index in self._md_folded:
            item=self._md_model['headings'][index]
            self.text.tag_add('md_fold_hidden',f"1.0+{item['body']}c",f"1.0+{item['end']}c")
        self.text.tag_configure('md_fold_hidden',elide=True)
        self.md_fold.configure(text=tr('Expand') if self.md_outline.current() in self._md_folded else tr('Fold'))

    def _expand_markdown_at(self,offset):
        for index in list(self._md_folded):
            item=self._md_model['headings'][index]
            if item['body']<=offset<item['end']:
                self._md_folded.remove(index)
        self._update_markdown_folds()

    def _jump_markdown_fragment(self,fragment):
        def slug(value): return re.sub(r'[^\w\s-]','',value.casefold()).strip().replace(' ','-')
        matches=[i for i,h in enumerate(self._md_model.get('headings',[]))
                 if h['title']==fragment or slug(h['title'])==fragment.casefold()]
        if len(matches)==1:
            self.md_outline.current(matches[0]);self.markdown_heading()
        elif matches:
            self.status.configure(text=tr('Multiple matching headings; choose a section'))
            self.md_outline.focus_set()
        else: self.status.configure(text=tr('Heading not found in loaded content'))

    def markdown_workspace(self,mode='files',query='',fragment=''):
        if self._archive_markdown() or not self._md_model.get('rendered'):
            return 'break'
        existing=getattr(self,'_workspace_dialog',None)
        if existing is not None and existing.winfo_exists():existing.lift();return 'break'
        if self._md_insert or (self._md_request and not self._md_request.get('probe')):
            return 'break'
        self._workspace_dialog=MarkdownWorkspaceDialog(self,Path(__file__).absolute(),bool(__package__),mode,query,fragment)
        return 'break'

    def follow_markdown_link(self,number):
        loading=(self._md_request and not self._md_request['probe']) or (self._md_queued and not self._md_queued['probe'])
        if (loading or self._md_insert
                or self._md_display_path!=self.path): return 'break'
        item=self._md_model.get('links',[])[number]
        if item.get('wiki'):
            if self._archive_markdown():
                self.status.configure(text=tr('Cross-document links are disabled inside archives'));return 'break'
            wiki=wiki_destination(item['wiki'])
            return self.markdown_workspace('wiki',wiki['name'],wiki['fragment'])
        try: target,fragment=markdown_destination(self.path,self._md_boundary,item['href'])
        except (ValueError,UnicodeError) as exc:
            self.status.configure(text=tr(str(exc)));return 'break'
        if target==self.path:
            if fragment: self._jump_markdown_fragment(fragment)
            else: self.text.yview_moveto(0)
            return 'break'
        if self._archive_markdown():
            self.status.configure(text=tr('Cross-document links are disabled inside archives'));return 'break'
        self._queue_markdown(target,navigation=True,fragment=fragment)
        return 'break'

    def _describe_markdown_link(self,item):
        if item.get('wiki'):
            self.status.configure(text=tr('Ctrl+click: confirm a project folder to resolve this wiki link.'))
            return
        try:
            target,fragment=markdown_destination(self.path,self._md_boundary,item['href'])
            if self._archive_markdown():
                if target!=self.path:
                    self.status.configure(text=tr('Cross-document links are disabled inside archives'));return
                label=target.name
            else:label=str(target)
            label+=('#'+fragment if fragment else '')
            self.status.configure(text=tr('Ctrl+click: ')+label)
        except (ValueError,UnicodeError) as exc:
            self.status.configure(text=tr(str(exc))+': '+item['href'])

    def markdown_back(self):
        if not self._md_history: return 'break'
        entry=self._md_history[-1]
        self._queue_markdown(Path(entry[0]),restore=entry[1])
        self._md_queued['back']=entry
        if len(entry) > 3: self._md_queued['request']['boundary'] = entry[3]
        return 'break'

    def _copy_select_all(self,event=None):
        self.text.tag_add('sel','1.0','end-1c');return 'break'

    def _copy_preview(self,event=None):
        try: value=self.text.get('sel.first','sel.last')
        except tk.TclError: return 'break'
        self.clipboard_clear();self.clipboard_append(value);return 'break'

    def apply_language(self, old_language: str, *, reload=True) -> None:
        mode = self.mode_values.get(self.mode_var.get(), self.mode_var.get())
        retranslate_widgets(self, old_language)
        self.mode_values = {tr("Auto"): "Auto", tr("Text"): "Text", tr("Hex"): "Hex"}
        self.mode_combo.configure(values=tuple(self.mode_values))
        self.mode_var.set(next(label for label, value in self.mode_values.items() if value == mode))
        markdown_mode = self.markdown_values.get(self.markdown_var.get(), "rendered")
        self.markdown_values = {tr("Markdown Source"): "source", tr("Rendered"): "rendered"}
        self.markdown_combo.configure(values=tuple(self.markdown_values))
        self.markdown_var.set(next(label for label, value in self.markdown_values.items()
                                   if value == markdown_mode))
        if reload: self.load()

    def _configure_effect_fonts(self) -> None:
        base = tkfont.nametofont("TkFixedFont")
        family, size = base.cget("family"), base.cget("size")
        def heading_size(factor, extra):
            scaled = max(abs(size)+extra, round(abs(size)*factor))
            return -scaled if size < 0 else scaled
        self.effect_fonts = {
            "bold": tkfont.Font(self, family=family, size=size, weight="bold"),
            "italic": tkfont.Font(self, family=family, size=size, slant="italic"),
            "h1": tkfont.Font(self, family=family, size=heading_size(1.55,6), weight="bold"),
            "h2": tkfont.Font(self, family=family, size=heading_size(1.35,4), weight="bold"),
            "h3": tkfont.Font(self, family=family, size=heading_size(1.18,2), weight="bold"),
        }

    def apply_scale(self, _scale: float) -> None:
        self._configure_effect_fonts()
        self.apply_color_scheme(self.palette)
        self.after_idle(self._layout_markdown_tools)

    def apply_color_scheme(self, palette) -> None:
        self.palette = palette
        self.configure(background=palette["window"])
        self.text.configure(background=palette["content"], foreground=palette["text"],
                            insertbackground=palette["text"], selectbackground=palette["selection"],
                            selectforeground="#ffffff")
        self.text.tag_configure("match", background=palette["match"], foreground=palette["text"])
        self.text.tag_configure("current_match", background=palette["current_diff"], foreground="#ffffff")
        dark = sum(int(palette["content"][i:i + 2], 16) for i in (1, 3, 5)) < 330
        colors = {
            "syntax_keyword": "#6cb6ff" if dark else "#005cc5",
            "syntax_string": "#a5d6a7" if dark else "#116329",
            "syntax_comment": "#9aa7b0" if dark else "#66737d",
            "syntax_number": "#f2a65a" if dark else "#b35900",
            "syntax_operator": "#d2a8ff" if dark else "#7a3e9d",
            "syntax_heading": "#79c0ff" if dark else "#174f86",
            "syntax_link": "#58a6ff" if dark else "#0969da",
        }
        for tag, foreground in colors.items():
            self.text.tag_configure(tag, foreground=foreground)
        self.text.tag_configure("markdown_bold", font=self.effect_fonts["bold"])
        self.text.tag_configure("markdown_italic", font=self.effect_fonts["italic"])
        self.text.tag_configure("markdown_code", background=palette["surface_alt"],
                                foreground=colors["syntax_string"])
        self.text.tag_configure("markdown_link", foreground=colors["syntax_link"], underline=True)
        self.text.tag_configure("markdown_url", foreground=palette["muted"])
        self.text.tag_configure("markdown_quote", foreground=palette["muted"])
        self.text.tag_configure("markdown_bullet", foreground=colors["syntax_keyword"])
        self.text.tag_configure("markdown_rule", foreground=palette["border"])
        self.text.tag_configure('markdown_task',foreground=palette['text'])
        self.text.tag_configure('markdown_task_done',foreground=palette['muted'])
        for kind,light,dark_color in (('note','#e6f1fc','#243d54'),('tip','#e5f4e8','#213e30'),('warning','#fff0d5','#544025')):
            self.text.tag_configure('markdown_callout_'+kind,background=dark_color if dark else light,
                                    foreground=palette['text'],lmargin1=8,lmargin2=8,spacing1=3,spacing3=3)
        self.text.tag_configure('markdown_table', font=tkfont.nametofont('TkFixedFont'),
                                background=palette['surface_alt'], wrap='none', spacing1=0, spacing3=0)
        for level in (1, 2, 3):
            self.text.tag_configure(f"markdown_h{level}", font=self.effect_fonts[f"h{level}"],
                                    foreground=colors["syntax_heading"], spacing1=8, spacing3=4)

    @property
    def path(self) -> Path:
        return self._linked_path if self._linked_path is not None else self.files[self.index]

    def set_extension_effect(self, enabled: bool) -> None:
        self.extension_effect = bool(enabled)
        self.load()

    def _apply_spans(self, spans: list[tuple[int, int, str]]) -> None:
        self._pending_spans = list(spans)
        self._apply_span_batch()

    def _apply_span_batch(self) -> None:
        self._span_job = None
        batch, self._pending_spans = (
            self._pending_spans[:SYNTAX_BATCH_SIZE],
            self._pending_spans[SYNTAX_BATCH_SIZE:])
        grouped: dict[str, list[str]] = {}
        for start, end, tag in batch:
            grouped.setdefault(tag, []).extend((f"1.0+{start}c", f"1.0+{end}c"))
        for tag, ranges in grouped.items():
            self.text.tag_add(tag, *ranges)
        if self._pending_spans and self.winfo_exists():
            self._span_job = self.after(8, self._apply_span_batch)

    def activate(self) -> None:
        self.host.activate(); self.text.focus_set()

    def _path_signature(self):
        try:
            path = self.path
            if path.is_dir():
                return tuple(sorted((item.name, item.stat().st_mtime_ns, item.stat().st_size)
                                    for item in path.iterdir()))
            stat = path.stat(); return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def _schedule_refresh(self) -> None:
        self._refresh_job = self.after(2000, self._auto_refresh)

    def _auto_refresh(self) -> None:
        self._refresh_job = None
        if self.host.active_page is not self:
            self._schedule_refresh(); return
        if self._markdown_mode():
            if (not self._md_auto_suspended and not self._md_jobs.pending and not self._md_queued
                    and not self._md_insert and self._md_display_path==self.path
                    and time.monotonic()-self._md_last_probe>5 and self.focus_displayof() is not None
                    and self.focus_displayof().winfo_toplevel() is self.host
                    and not self.text.tag_ranges('sel')):
                self._md_last_probe=time.monotonic();self._queue_markdown(probe=True)
            if self.winfo_exists(): self._schedule_refresh()
            return
        signature = self._path_signature()
        if signature != self._signature:
            self.load()
        if self.winfo_exists(): self._schedule_refresh()

    def load(self) -> None:
        path = self.path
        if self._markdown_mode():
            self._queue_markdown();return
        self._remember_markdown_position()
        if self._md_jobs.pending or self._md_queued: self.cancel_markdown()
        self._md_model={};self._md_insert=None;self.md_tools.pack_forget()
        for tag in self.text.tag_names():
            if tag.startswith(('md_fold_','md_link_')): self.text.tag_delete(tag)
        if self._span_job is not None:
            self.after_cancel(self._span_job); self._span_job = None
        self._pending_spans = []
        self.title(f"{tr('PFC Preview')} — {path.name}")
        self.text.configure(state="normal"); self.text.delete("1.0", "end")
        mode = self.mode_values.get(self.mode_var.get(), self.mode_var.get())
        encoding, truncated, spans = "", False, []
        try:
            if path.is_dir():
                entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
                content = f"{tr('Folder')}: {path}\n\n" + "\n".join(
                    ("[DIR]  " if item.is_dir() else "       ") + item.name for item in entries)
                shown_mode = tr("Folder view")
            else:
                size = path.stat().st_size
                with path.open("rb") as stream:
                    sample = stream.read(4096); stream.seek(0)
                    chosen = "Text" if mode == "Text" or (mode == "Auto" and looks_text(path, sample)) else "Hex"
                    limit = TEXT_LIMIT if chosen == "Text" else HEX_LIMIT
                    data = stream.read(limit + 1)
                truncated = len(data) > limit; data = data[:limit]
                if chosen == "Text":
                    content, encoding = decode_text(data); shown_mode = tr("Text")
                    suffix = path.suffix.casefold()
                    markdown_mode = self.markdown_values.get(self.markdown_var.get(), "rendered")
                    if self.extension_effect and suffix == ".md" and markdown_mode == "rendered":
                        content, spans = render_markdown(content)
                        shown_mode = tr("Markdown rendered")
                    elif self.extension_effect and suffix in CODE_EXTENSIONS:
                        spans = syntax_spans(content, suffix)
                        shown_mode = tr("{language} syntax", language=CODE_EXTENSIONS[suffix])
                else:
                    content = render_hex(data); shown_mode = tr("Hex")
                size = path.stat().st_size
            self.text.insert("1.0", content)
            self._apply_spans(spans)
            show_markdown = (path.is_file() and path.suffix.casefold() == ".md"
                             and chosen == "Text" and self.extension_effect)
            if show_markdown:
                self.markdown_frame.pack(side="left", padx=(4, 0))
            else:
                self.markdown_frame.pack_forget()
            size = path.stat().st_size if path.is_file() else 0
            detail = f"{shown_mode}   {size:,} bytes"
            if encoding: detail += f"   {encoding}"
            if truncated: detail += "   Preview truncated"
            self.status.configure(text=f"{detail}   {path}")
        except OSError as exc:
            self.text.insert("1.0", f"{tr('Cannot preview file')}:\n{exc}")
            self.status.configure(text=str(path))
        self.text.configure(state="disabled")
        self.text.tag_raise("match"); self.text.tag_raise("current_match")
        self._signature = self._path_signature()
        self.find_all()

    def set_wrap(self) -> None:
        self.text.configure(wrap="word" if self.wrap_var.get() else "none")

    def focus_search(self) -> str:
        self.search.focus_set(); self.search.selection_range(0, "end"); return "break"

    def find_all(self) -> None:
        self.text.tag_remove("match", "1.0", "end"); self.text.tag_remove("current_match", "1.0", "end")
        self.matches, self.match_index = [], -1
        needle = self.search_var.get()
        if not needle: return
        # Tk 8.6 Text.search can crash on folded text containing astral Unicode.
        # Search the complete visible document model (including folded content)
        # in Python, then use Text's Unicode-character index modifiers.
        content=self.text.get('1.0','end-1c')
        from bisect import bisect_right
        lines=_line_offsets(content)
        def text_index(offset):
            line=bisect_right(lines,offset)-1
            return self.text.index(f'{line+1}.0+{offset-lines[line]}c')
        flags=0 if self.case_var.get() else re.IGNORECASE
        for match in re.finditer(re.escape(needle),content,flags):
            a,b=match.span()
            found,end=text_index(a),text_index(b)
            self.matches.append((found,end));self.text.tag_add('match',found,end)
            if len(self.matches)>=5000:
                self.status.configure(text=tr('Showing the first 5,000 search matches'));break

    def _find(self, direction: int) -> str:
        previous_index = self.match_index
        self.find_all()
        if not self.matches:
            detail=f"{tr('No matches')}   {self.path}"
            if self._md_model.get('truncated'):detail+='   '+tr('Loaded portion only')
            self.status.configure(text=detail); return "break"
        self.match_index = (previous_index + direction) % len(self.matches)
        start, end = self.matches[self.match_index]
        offset=len(self.text.get('1.0',start))
        self._expand_markdown_at(offset)
        self.text.tag_remove("current_match", "1.0", "end")
        self.text.tag_add("current_match", start, end); self.text.see(start)
        self.status.configure(text=f"{tr('Match {current} of {total}', current=self.match_index + 1, total=len(self.matches))}   {self.path}")
        if len(self.matches)>=5000 or self._md_model.get('truncated'):
            notices=[]
            if len(self.matches)>=5000:notices.append(tr('Showing the first 5,000 search matches'))
            if self._md_model.get('truncated'):notices.append(tr('Loaded portion only'))
            self.status.configure(text=self.status.cget('text')+'   '+'; '.join(notices))
        return "break"

    def find_next(self) -> str: return self._find(1)
    def find_previous(self) -> str: return self._find(-1)

    def previous_file(self) -> None:
        if self.files:
            self.host.show(self.files, self.files[(self.index-1) % len(self.files)])

    def next_file(self) -> None:
        if self.files:
            self.host.show(self.files, self.files[(self.index+1) % len(self.files)])

    def close(self) -> None:
        self._remember_markdown_position()
        self._md_jobs.close()
        if self._md_poll_job is not None:
            self.after_cancel(self._md_poll_job);self._md_poll_job=None
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job); self._refresh_job = None
        if self._span_job is not None:
            self.after_cancel(self._span_job); self._span_job = None
        self.destroy()


class PreviewWindow(tk.Toplevel):
    """One window, independent read-only documents; inactive tabs never read files."""
    MAX_TABS = 32

    def __init__(self, master, config, save_config, files, selected, extension_effect=True):
        super().__init__(master)
        self.config_data, self.save_config = config, save_config
        self.extension_effect = extension_effect
        self.pages = {}
        self.active_page = None
        self.geometry(config.get('preview', 'geometry', fallback='1100x720'))
        self.minsize(640, 400)
        self.protocol('WM_DELETE_WINDOW', self.close)
        bar = ttk.Frame(self); bar.pack(fill='x', padx=6, pady=(4,0))
        self.document_menu = ttk.Menubutton(bar, text=tr('Open documents'))
        self.document_menu.pack(side='left')
        self.documents = tk.Menu(self.document_menu, tearoff=False, postcommand=self._document_list)
        self.document_menu.configure(menu=self.documents)
        self.path_label = ttk.Label(bar, anchor='w', width=1)
        self.path_label.pack(side='left', fill='x', expand=True, padx=8)
        ToolTip(self.path_label, lambda: str(self.active_page.path) if self.active_page else '')
        close_button = ttk.Button(bar, text=tr('Close tab'), command=self.close_tab)
        close_button.pack(side='right')
        ToolTip(close_button, lambda: tr('Close tab')+' (Ctrl+W)')
        ToolTip(self.document_menu, lambda: tr('Open documents')+' (Ctrl+Tab / Ctrl+Shift+Tab)')
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True)
        self.notebook.bind('<<NotebookTabChanged>>', self._tab_changed)
        self.notebook.bind('<Button-2>', self._middle_close)
        for sequence, action in (
                ('<Escape>', self.close), ('<Control-w>', self.close_tab),
                ('<Control-f>', lambda: self.active_page.focus_search()),
                ('<F5>', lambda: self.active_page.load()),
                ('<Alt-Left>', lambda: self.active_page.markdown_back() if self.active_page._md_history else self.active_page.previous_file()),
                ('<Alt-Right>', lambda: self.active_page.next_file()),
                ('<Control-Tab>', lambda: self.cycle(1)),
                ('<Control-Shift-Tab>', lambda: self.cycle(-1)),
                ('<Control-ISO_Left_Tab>', lambda: self.cycle(-1))):
            self.bind(sequence, lambda e, fn=action: (fn(), 'break')[1])
        self.show(files, selected)

    def __getattr__(self, name):
        # Preserve Preview's active-document interface for callers and tools.
        page = self.__dict__.get('active_page')
        if page is not None and hasattr(page, name): return getattr(page, name)
        raise AttributeError(name)

    def _document_list(self):
        self.documents.delete(0, 'end')
        for page in self.pages.values():
            self.documents.add_command(label=str(page.path), command=lambda p=page:self.notebook.select(p))

    def show(self, files, selected):
        self.open_paths(files, [selected], selected)

    def open_paths(self, files, selected_paths, selected=None):
        from tkinter import messagebox
        selected_paths = list(selected_paths)
        if not selected_paths: return
        selected = selected or selected_paths[0]
        chosen = None
        for path in selected_paths:
            path = Path(path)
            key = os.path.normcase(os.path.abspath(path))
            page = self.pages.get(key)
            if page is None:
                if len(self.pages) >= self.MAX_TABS:
                    messagebox.showinfo(tr('PFC Preview'), tr('Close a preview tab before opening more (limit: 32).'), parent=self)
                    break
                navigation = list(files)
                if path not in navigation: navigation.append(path)
                page = PreviewPage(self.notebook, self.config_data, self.save_config,
                                   navigation, path, self.extension_effect, host=self, lazy=True)
                self.pages[key] = page
                label = path.name or str(path)
                if len(label)>38: label=label[:24]+'…'+label[-10:]
                self.notebook.add(page, text=label)
            else:
                page.files = list(files)
                if path not in page.files: page.files.append(path)
                page.index = page.files.index(path)
            if path == selected: chosen = page
        if chosen is not None: self.notebook.select(chosen)
        self._tab_changed()
        self.activate()

    def _tab_changed(self, _event=None):
        tab = self.notebook.select()
        if not tab: return
        page = self.nametowidget(tab)
        if self.active_page is not page:
            previous = self.active_page
            if previous is not None:
                previous._remember_markdown_position()
                if previous._md_jobs.pending or previous._md_queued or previous._md_insert:
                    previous.cancel_markdown(); previous._loaded = False
                previous._md_jobs.close()
            self.active_page = page
        if not page._loaded:
            page._loaded = True; page.load()
        self.title(getattr(page, 'page_title', tr('PFC Preview')))
        self.path_label.configure(text=str(page.path))

    def activate(self):
        self.deiconify(); self.lift(); self.focus_force()
        if self.active_page: self.active_page.text.focus_set()

    def cycle(self, direction):
        tabs = self.notebook.tabs()
        if tabs: self.notebook.select(tabs[(tabs.index(self.notebook.select())+direction) % len(tabs)])

    def _middle_close(self, event):
        try: self.close_tab(self.nametowidget(self.notebook.tabs()[self.notebook.index(f'@{event.x},{event.y}')]))
        except tk.TclError: pass

    def close_tab(self, page=None):
        page = page or self.active_page
        if page is None: return
        if len(self.pages) == 1: self.close(); return
        self.notebook.forget(page)
        self.pages = {key:value for key,value in self.pages.items() if value is not page}
        if self.active_page is page: self.active_page = None
        page.close(); self._tab_changed()

    def apply_scale(self, scale):
        for page in self.pages.values(): page.apply_scale(scale)

    def apply_color_scheme(self, palette):
        self.configure(background=palette['window'])
        for page in self.pages.values(): page.apply_color_scheme(palette)

    def apply_language(self, old_language):
        for page in self.pages.values():
            page.apply_language(old_language, reload=page is self.active_page)
        retranslate_widgets(self, old_language)

    def set_extension_effect(self, enabled):
        self.extension_effect = enabled
        for page in self.pages.values():
            page.extension_effect = enabled
            if page is self.active_page: page.load()
            else: page._loaded = False

    def close(self):
        if not self.config_data.has_section('preview'): self.config_data.add_section('preview')
        self.config_data.set('preview', 'geometry', self.geometry())
        if self.active_page:
            self.config_data.set('preview', 'wrap', str(self.active_page.wrap_var.get()).lower())
        for page in list(self.pages.values()): page.close()
        self.pages.clear(); self.active_page = None
        self.save_config(); self.destroy()
