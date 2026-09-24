# Markdown preview expansion: risk and scope plan

Originally a proposal requested 2026-09-19. The user subsequently authorized a
two-hour implementation window. The plan itself is not deployment authority.
This refines the local-link proposal in `ui-ux-review-2026-09-19.md`.

## v0.17.19 implementation status

The read-only tasks/callouts, outline/folding, exact local links/Back and bounded
worker described here are implemented. See [the current guide](markdown-preview-guide.md)
for actual limits and restrictions; the remaining sections retain the original
planning baseline and proposed acceptance gates for traceability.

Important deliberate restriction: **all Windows reparse targets are refused**,
including resident OneDrive files. A provider-specific no-recall path remains
unimplemented, not silently assumed safe. No full Obsidian compatibility or
hostile-filesystem OS sandbox is claimed. The reader never indexes or searches
for a missing link. Explicit manual F3/F5 reads may hydrate cloud documents.

Validation includes Linux source/portable GUI checks and Windows ARM64 portable
checks with both python.exe and pythonw.exe: 100/150/300% fonts, three themes,
fold/search/copy, Unicode link offsets, exact-path navigation/Back, missing and
out-of-bound targets, cancellation/timeout/stale results, archive anchor-only
behavior and source fallback. Native Windows ordinary-file, junction and offline
attribute fixtures pass. **Real cloud-provider transitions and adversarial OS
filesystem races have not been established by these tests.**

## Verified planning baseline (v0.17.18, before this implementation)

`preview.py` renders Markdown links as styled text plus a destination string;
it has no link activation/resolution handler or link-driven filesystem index.
Text input is bounded to 8 MiB, with a truncation notice. Reading, parsing and
Text insertion still run on the Tk/UI thread. A two-second preview timer checks
file signatures; directory previews enumerate their immediate entries. These
are NOT recursive link indexing, but can still block on slow storage or expensive
documents. Input-size and grid-expansion limits alone do not bound CPU time or
peak memory. Existing behavior is not claimed to satisfy the new requirements.

## Recommended first link release: resolve explicit paths, never search

No index, recursive scan, background link validation, hover prefetch, Windows
Search query, project discovery or persistent link database. Parse only the
document the user explicitly opened. Resolve one target only when clicked.

Two separate concepts:

- Relative-path base: the directory of the document containing the link.
- Allowed boundary: the original preview document's directory, fixed for the
  navigation session, including explicitly addressed descendants. Following a
  link never expands or moves this boundary upward. Opening another document
  manually starts a new scope. A path prefix/Home icon, Git root or INI setting
  supplied by a document is not authority to enlarge the boundary.

Supported initially:

| Link | Resolution |
| --- | --- |
| `#Heading` / `[[#Heading]]` | Current loaded document only; zero filesystem lookup |
| `[Spec](spec.md)` | Exact file beside the containing document |
| `[Spec](docs/spec.md#Heading)` | Exact addressed descendant, then its heading |
| `../spec.md` | Only if normalization still stays inside the fixed boundary |
| Missing file / denied access / missing heading | Distinct message; no broader fallback |
| `[[Spec]]`, aliases, vault-root wikilinks, block references | Not resolved in the first release; visible unsupported syntax |
| Absolute paths, UNC, mapped network drives, device paths, URI schemes | No activation through this feature |
| Non-Markdown files / executables / scripts / directories | No activation; no shell launch or automatic file listing |

Obsidian vault-relative wikilinks must not silently be reinterpreted as
document-relative paths. Explicitly label this as a subset of Markdown local
links, not full Obsidian compatibility. No fuzzy matching, implicit extension
guessing or opening the first same-name result. A duplicate heading presents
the actual matching headings/positions rather than silently picking one.

Display the normalized destination before activation. Preserve source document,
scroll position and selection until the new preview succeeds; provide Back,
with at most 20 navigation entries held in memory. Failed navigation adds no
history entry. Do not auto-create missing notes or rewrite links after renames.
Revalidate when clicked, not just when rendering the source document.

## Path and I/O security gate

- Parse path and fragment separately; decode escapes once, reject malformed
  encoding, control/NUL characters, alternate data streams and device/drive-relative
  path tricks. Perform path-component containment, never a string-prefix check.
- Lexical normalization is insufficient: symlinks, junctions and mount points
  can redirect outside the allowed root or to a network target. Check components
  without following name-surrogate reparse points; reject them in the first
  release. Validate the opened target identity/path as well, covering changes
  between validation and opening. Do not claim a security boundary based solely
  on a pre-open `resolve()` check.
- Cloud reparse points are not all symlinks. A blanket reparse rejection would
  exclude many ordinary OneDrive documents and reduce value for this workflow.
  Support only explicitly understood locally resident provider cases with a
  tested no-recall read path. Online-only, unknown or unsupported cases show a
  message without opening content. No automatic download or hydration. If the
  platform cannot enforce the gate, decline linked preview instead of guessing.
- Detect remote/mapped paths before content access. Even metadata/path resolution
  can block or contact providers, so these operations also belong outside Tk.
- Inside ZIP/7z previews, initially support same-document anchors only. Do not
  expose or navigate extraction Temp paths, extract another archive or cross
  archive boundaries by following a link. Exiting the archive invalidates links.
- No network requests, OS-open/ShellExecute, HTML/JavaScript execution, embedded
  includes, custom CSS, plugin commands or externally fetched images.

## Resource and failure behavior

Before enabling linked previews, move file probing/read/parse off the UI thread.
Use one bounded, cancellable job per preview; do not spawn a job for every link.
Use a dedicated worker process for operations that cannot be interrupted safely
in a Python thread. Superseded jobs cannot repaint the newer document. Confirm
worker exit before reusing the slot; never accumulate hung workers.

Proposed initial limits, to validate by benchmarks rather than advertise as
measured guarantees: retain 8 MiB input limit; show activity/cancel after 300 ms;
stop waiting at a 5-second job budget and retire the worker; bounded result size
and chunked Tk insertion. Cancellation should restore controls within 200 ms on
test hardware. OS/provider I/O may outlive an application timeout; keep the slot
unavailable until its worker is confirmed stopped, and do not automatically retry.

For an overly complex document, offer bounded source preview with an explicit
reason, not silently omitted rows. Search, outline and task counts must say
“loaded portion” whenever the preview is truncated. No completeness claims then.
Coalesce preview refreshes, defer during selection/copy, and avoid directory
enumeration or metadata calls on Tk. Preserve reading position after a refresh;
invalidate offsets/folds only when the document snapshot changes.

## Other candidate features: defined first-release behavior

| Feature | Main risk | Initial boundary |
| --- | --- | --- |
| Task lists | Accidental writes; false progress counts | Read-only `[ ]` / `[x]`; keep unfamiliar markers literal; ignore fenced code; no cross-file task collection or recurring-task interpretation |
| Callouts | Hidden warnings, lost nested content, theme contrast | Initially expand all blocks; support note/tip/warning with text labels and icons, not color alone; preserve unknown types and unsupported nesting visibly; no CSS/embeds |
| Heading menu | Wrong targets; code mistaken for headings | Parse current snapshot only; exclude code fences; label duplicate titles with hierarchy/position; compact dropdown, no disk scan |
| Folding | Search/copy misses hidden text; stale offsets | Defer until heading navigation works; search expands matched regions, Select All/Copy includes folded text, default expanded; only session state; reset safely on content changes |
| Tables/properties | YAML execution; resource expansion; apparent completeness | Literal read-only properties, no constructors; bounded render/source fallback; explicit truncation and supported-syntax limits |
| Cross-document links | Unbounded search, boundary escape, missing targets | Exact local Markdown paths within fixed scope only, as defined above |
| History/cache | Private paths persist; stale previews | Bounded in-memory navigation only; no document content or link paths in telemetry/context notes or repository config |

## Optional scoped search: separate future feature, not a fallback

Update 2026-09-25: the user approved a bounded discovery trial. Filename search,
wiki links and an on-demand backlinks list now ship in v0.18.8; see
[the exact implementation limits](markdown-workspace.md). The proposal below is
retained as planning history, not a promise of full Obsidian search semantics.

If basename-only wikilinks are wanted later, ask the user to choose a local
project root explicitly. One-shot filename search only, started by a separate
button displaying the scope; no content scan or automatic index rebuild.

Proposed limits: reject drive roots/home as a broad default; at most 5,000 visited
entries (count ALL entries, not matches), depth 8, 3 seconds and 50 candidates;
stop on the first limit and label results incomplete. Local resident entries
only; do not follow symlinks/junctions, enumerate cloud-only folders, enter
archives, or descend `.git`, `.svn`, `node_modules`, `.venv` by default. Never
enlarge the root or restart in the background. Cancellation/worker isolation
requirements above still apply; the time limit is not a promise that every OS
I/O can be synchronously canceled. Multiple matches require a user choice.
No automatic selection even when a partial search found one candidate.

This loses some discovery convenience deliberately. Its ROI must be reassessed
against real documents that use such links before implementing it.

## Acceptance gates before shipping

1. A document with 1,000 links causes zero link-target I/O when opened or hovered.
2. Clicking a nonexistent exact path causes no directory enumeration, Windows
   Search access, parent walk or request for other drives.
3. Encoded traversal, same-prefix sibling folders, symlink/junction loops,
   target replacement and remote/cloud redirects are refused without content read.
4. Cloud-only/unknown states do not hydrate; offline, permission-denied, removed
   media and slow providers produce a cancellable result, not frozen controls.
5. Huge/nested/malformed documents hit tested limits without silent data loss or
   ever-growing workers. Incomplete preview/search is explicitly labeled.
6. Follow a link, fail another, return, zoom, refresh, search and copy: document
   identity, position and text remain consistent. Source-file hashes unchanged.
7. Markdown, OneDrive-local and ZIP cases are tested separately. No claim of
   provider no-hydration safety until its native test passes with authorization.

## References

- [Obsidian vault boundary](https://obsidian.md/help/vault)
- [Obsidian internal-link semantics](https://obsidian.md/help/links)
- [Windows reparse behavior](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-points)
- [Windows offline/recall attributes](https://learn.microsoft.com/en-us/windows/win32/fileio/file-attribute-constants)
