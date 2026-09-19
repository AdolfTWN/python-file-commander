# Markdown reading in PFC v0.17.19

Select an `.md` file, press **F3**, and choose **Rendered**. Extension Effect must
be on for rich rendering. This is a read-only reader, not an Obsidian vault or
editor. It never updates task checkboxes, YAML properties, links or source files.

## Reading controls

- **Sections**: current document's headings and properties, with hierarchy and
  numbered positions so duplicate titles can be distinguished. Code fences do
  not create headings. An ambiguous anchor asks you to choose a section.
- **Fold**: collapse/expand the selected section. **Reading → Expand all** restores
  everything. Folds are session-only and reset on a new content snapshot.
- **Ctrl+F / Enter / Shift+Enter**: search loaded text, including collapsed
  sections; jumping to a hidden match expands its containing sections.
- **Ctrl+A / Ctrl+C**: Select All/Copy includes folded text. Ordinary selections
  include the full logical text between their endpoints, including folded text.
- **Tasks**: `[ ]`, `[x]` and `[X]` show empty/completed boxes and a completed/total
  counter. Unknown markers remain literal. Fenced code does not count as tasks.
- **Callouts**: `> [!note]`, `> [!tip]`, `> [!warning]` and familiar aliases receive
  text labels and color. Every callout starts expanded, even with Obsidian's `-`
  marker. Unknown types retain their label; nested content remains visible.
- **F5 / Cancel**: refresh manually or cancel reading. Timeout/error does not
  cause repeated automatic retries. Previous content stays until a read succeeds;
  canceling during chunked insertion clears the incomplete new display.
- **Reading → Markdown Source / Rendered** also switches presentation when the
  top mode selector is crowded at large font sizes. The reading row can shrink
  its section selector or wrap into two rows to keep Cancel accessible.

Tables/properties preserve literal data and horizontal scrolling. Table cells
flatten inline formatting and display link destinations as text, but their links
are not clickable. The renderer supports a practical Markdown subset, not all
CommonMark/Obsidian syntax. Use Source view for the exact original notation.

## Links: explicit paths, no search

Hover shows the lexically normalized destination without touching its target.
**Ctrl+click** on a label, or use its entry in **Reading**, to follow it.

- `[Spec](spec.md)` or `[Spec](docs/spec.md#Details)` addresses one exact `.md` file.
- `#Details` / `[[#Details]]` jumps within the current document, with no file read.
- The allowed boundary is the **original preview document's containing folder**,
  including explicitly addressed descendants. It stays fixed as you navigate.
- Relative paths start at the current document. `..` works only when the result
  remains inside that original boundary. No implicit extensions or name matching.
- The Reading tooltip/menu shows the boundary. **← / Alt+Left** returns through
  at most 20 in-memory entries and restores scroll position. A failed link leaves
  the current document/selection intact and adds no history.
- Manually choosing a file, or using File <</>>, starts a new boundary/history.
- Missing files, missing headings and unsupported destinations report a reason.
  They never trigger a folder enumeration, Windows Search, parent search, wider
  drive scan, index, automatic creation or link repair.

Not followed: basename/vault wikilinks (`[[Spec]]`), aliases, block references,
absolute/device/UNC/URI paths, mapped/network drives, scripts, executables,
non-Markdown files and symlink/junction/reparse redirects. No browser or shell is
launched. No external images, HTML/JavaScript, CSS, plugins, Mermaid, Dataview or
embedded includes execute. ZIP/7z workspaces allow same-document anchors only.

**Windows cloud restriction:** the first release rejects every reparse-linked
target, including many fully resident OneDrive documents. This conservative gate
avoids guessing whether a provider would download content. Explicitly selecting
a document and using F3/F5 remains possible, but that normal open **may hydrate a
cloud file**. It is distinct from guarded link navigation. Live-provider support
has not been validated; an offline VM test is not evidence of provider behavior.

## Resources, refresh and privacy

- One isolated worker per preview; no work is created per link. Reading, probing
  and parsing happen outside Tk. Canceled/superseded results cannot overwrite the
  new document. No new worker replaces a retiring one until exit is confirmed.
- Five-second worker deadline, explicit Cancel and a **512 MiB** OS memory limit
  (address space on POSIX, process committed memory via a Windows Job Object).
  If the OS cannot apply that limit, rich rendering uses bounded source instead.
  The limit does not cover the main PFC process; this is not an OS security sandbox.
- Input: first 8 MiB; rich rendering/source highlighting: at most 512 Ki Unicode
  characters. Rendering output: 2 Mi characters, 20,000 spans, 2,000 headings or
  active links. Reaching a renderer limit switches to explicitly labeled source
  (at most 512 Ki characters), rather than silently dropping rows or links.
- Source mode can show the full loaded 8 MiB, without syntax highlighting above
  the highlighting threshold. Tk insertion is chunked. Search highlights at most
  5,000 matches. Reading menu lists the first 100 links; other supported labels
  remain Ctrl+clickable in the text.
- Truncated previews say **Loaded portion only**; the task count receives `*`.
  Counts, sections and search cover loaded content only, not the entire disk file.
- Background metadata probes run no more often than every five seconds while
  the preview is focused, idle and without a text selection. Both the probe and
  any subsequent reload use the guarded local-file path. Unsupported locations
  suspend automatic refresh; F5 remains an explicit user action. Refresh restores
  vertical position but resets folds for the changed snapshot.
- No persistent link/content database, telemetry, cloud transfer or folder-root
  discovery. History, section and link metadata live in memory only. Existing
  preview geometry/wrapping preferences still use INI.

Local-link checks are conservative application navigation controls, not a defense
against an administrator maliciously changing the filesystem/provider underneath
the process. Windows validates reparse/offline/recall attributes, final handle
path and file identity before reading; POSIX walks directory handles without
following symlinks and refuses device/mount changes. Unknown cases fail closed.

Try [the example](markdown-preview-example.md). Basename discovery, backlinks,
graphs, plugins and scoped indexing remain separate, unimplemented features.
