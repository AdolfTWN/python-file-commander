# v0.17.19 Markdown validation

## Automated checks

- Unit suite: 179 tests, 8 platform-specific skips on Linux.
- Full existing headless suite: menus, columns, preview, overlays, drag/refresh,
  archives, paths, fonts, prefixes/icons, scrolling, size/date cells and VCS.
- `markdown_preview_check.py`: existing tables/properties, source roundtrip,
  search, themes and pixel-sized headings, updated to await asynchronous work.
- `markdown_reading_check.py`, source and portable: 100/150/300% fonts; all three
  themes; 1100px and 640px reading-row accessibility; task counts, expanded
  callouts, folding/search/copy, source/rendered switching and Extension Effect
  off; Unicode link ranges; exact navigation and Back/scroll position; missing
  and out-of-bound targets; stale jobs, cancel/timeout/retry; ZIP anchor-only
  behavior; explicit source fallback; original files unchanged; worker cleanup.
- `test_markdown_jobs.py`: one reusable worker, rejection of concurrent requests,
  cancellation of a blocked worker without waiting for its work, stale-result
  rejection and successful replacement after exit.
- `test_markdown_reading.py`: 1,000 links parsed without target stat/enumeration;
  destination traversal/device/network/execution refusals; exact bounded reads;
  POSIX symlink and FIFO rejection; metadata caps; unknown callouts and encoded
  Unicode/space/percent heading anchors.

## Native Windows ARM64, offline

The portable candidate was exercised under both `python.exe` and `pythonw.exe`.
The final candidate's table/property and reading checks passed; a native 150%
visual check confirmed readable hierarchy, task counters and callout styling.

`markdown_windows_check.py` passed:

- Normal file content and metadata-only reads.
- Junction redirect refusal.
- Offline-attribute refusal before content stream creation.
- A separate worker applying its Windows Job Object memory limit refused a
  600 MiB allocation. This verifies enforcement, not merely a successful API call.

Portable file checked in the Windows VM:

`fc2d76b70e3071072c9633b120412aaadde702d3d31116a27fca05b2cca6577d`

VM networking remained disabled; the lease was released after validation for
immediate disk hibernation under the shared-pool policy.

## Issues found during development and corrected

- Tk folded-text Unicode search could segfault; search now uses bounded Python
  text matching rather than Tk's problematic elided-text search path.
- Confusing Tcl UTF-16 length with Text character offsets shifted link hit areas;
  offsets now use Text's Unicode-character modifiers, checked natively.
- Metadata probing swallowed link clicks; explicit navigation now takes priority.
- Large fonts crowded Cancel off the toolbar; the reading row now flexes/wraps.
- Same-document wiki anchors needed percent encoding for spaces, `%` and CJK.
- Source highlighting must respect Extension Effect off; verified separately.

## Limits of this evidence

No live OneDrive provider was authorized or tested. All reparse-linked targets
remain refused, including resident OneDrive cases. Synthetic offline attributes
do not prove provider no-hydration behavior. No hostile-administrator filesystem
race, arbitrary storage driver, third-party renderer or full Obsidian syntax
compatibility is claimed. The main application is not an OS sandbox; worker
memory/time limits and exact-path navigation are defense-in-depth controls.
