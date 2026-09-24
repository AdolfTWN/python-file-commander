# Markdown workspace — v0.18.8

## Entry points and scope

In F3 Rendered Markdown, open **Reading → Find Markdown files** or **Backlinks to
this document**. Ctrl+click a wiki link opens the same compact dialog in exact
filename mode. Confirm the project folder and press **Search**. Opening a document,
hovering a link and opening the dialog perform no workspace scan.

The folder must contain the current document. Drive roots and the user's home
folder are rejected. A successful scan remembers the most recently confirmed root
and depth locally in `pfc.ini`; it is proposed only for documents inside that root.
Other documents propose their own containing folder, still requiring Search.
There is no automatic ascent through parents, inferred repository root or disk scan.

Depth means child-folder edges below the confirmed root: root-level files count
as depth 0. Default 3; choices 1, 3, 5 and 8. A root's sibling is never searched.
If the user needs sibling projects, they must explicitly choose a containing root.

## Links and results

- `[[Spec]]` / `[[Spec.md]]`: exact filename, case-insensitive candidate matching.
- `[[Spec#Overview|Design]]`: alias display plus heading jump after selection.
- `[[docs/Spec]]`: exact path relative to the confirmed project root, not a fuzzy
  basename fallback. It must still be reachable within the selected search depth.
- `[[#Heading]]`: current loaded document only, no search.
- Ordinary `[label](path.md)` remains exact document-relative navigation within
  its approved boundary; it never triggers discovery automatically.
- Opening a workspace result adopts the explicitly confirmed boundary for that
  navigation. Back restores the preceding document and boundary.

Every result uses a relative path. No result is preselected or auto-opened, even
if there is only one match. Duplicate names remain separate. Selection is needed
before Open is enabled; double-click/Enter opens the selected item. The selected
file is revalidated by the existing guarded reader before loading.

Backlinks are a list, not an automatically maintained graph. **Exact path
reference** is a supported explicit link targeting this document. **Possible
filename reference** is a basename wiki link that might refer to another file
with the same name; it is never presented as a confirmed relationship. Opening
the result opens the referring document, not a claim of an exact source offset.
Only links understood by the Markdown inline renderer are included, not code,
properties, table-cell links, block IDs or arbitrary Obsidian/plugin syntax.

## Resource and safety limits

Each scan shares 5,000 total visited entries (including non-MD/excluded items),
three seconds and 50 results across every branch. The dedicated worker has the
existing 512 MiB memory protection. A four-second UI watchdog terminates an
unresponsive worker, including startup/I/O delay; OS teardown is not an absolute
latency promise. A new worker cannot start until its predecessor is reaped.

Filename search never reads document content. Backlinks explicitly read local MD
files only: at most 256 KiB each and 8 MiB total (plus a truncation-detection byte),
under the same time/entry budgets.
Large or unreadable documents yield an incomplete result, not silent certainty.
Code blocks/inline code do not generate backlinks. Search does not run on typing,
hover, document open, tab switch or a refresh timer. No persistent content index.

The default exclusions are `.git`, `.svn`, `node_modules`, `.venv`, `venv` and
`__pycache__`. Depth/exclusions are always part of the completion message.
Other skipped inaccessible/cloud/link paths and budget limits are explicit.
No match within scope is not evidence that the document is absent elsewhere.

Directory enumeration retains no-follow handles on POSIX; Windows locks checked
ancestor components against rename/delete while enumerating. Network drives,
reparse/cloud paths and cross-device POSIX paths remain refused. A filesystem
race/security sandbox against hostile storage drivers is not claimed.
ZIP previews remain same-document-anchor only.

## Validation and remaining integrations

`tests/test_mdworkspace.py` covers lexical scope/links, depth, exclusions, duplicate
names, total entry/result/time budgets, no-content filename search, backlinks,
large-document limits and POSIX symlink rejection. `tools/markdown_workspace_check.py`
exercises actual worker processes, four languages, explicit consent, navigation,
Back, remembered settings, cancellation, stale-result clearing and fixed footers
in package and portable editions and on the offline Windows VM.
The final unit suite has 262 tests with 8 platform skips. Windows visual review
used a Traditional Chinese dialog and synthetic duplicate documents. Native tests
also cover a 700×480 dialog and larger application fonts. Subsequent small changes
to the minimum window size and shrinking read-budget guard were rechecked on Linux;
the native run predates those two adjustments. A final percent-sign path/INI
roundtrip correction (including reading records) passed Linux package/portable
checks with a `Project 100%` fixture; that fixture was not rerun on Windows.
The complete headless runner finished all 78 package/portable GUI invocations
successfully before that last INI adjustment. Markdown workspace, workflow records
and Preview tabs were rechecked separately after it; this is not a claim that the
entire runner was restarted for the final small change.

`tools/markdown_workspace_benchmark.py` creates 5,501 local synthetic entries and
searches for a missing filename. The Linux run visited exactly 5,000, returned an
entry-limit/incomplete result in 0.0203 seconds. This measures warm local storage
only, not a latency guarantee for Windows, OneDrive, HDDs or network providers.

The same Windows inspection found no Git/SVN CLI or Tortoise clients, and one
sampled OneDrive entry had unknown metadata. Real Tortoise dialogs and cloud state
transitions remain unverified. No networking, account change, content hydration
or sync-state mutation was performed for those checks.

Cloud-link work remains gated rather than removing existing protections:
[CfOpenFileWithOplock](https://learn.microsoft.com/en-us/windows/win32/api/cfapi/nf-cfapi-cfopenfilewithoplock)
provides protected handles, while
[range information](https://learn.microsoft.com/en-us/windows/win32/api/cfapi/ne-cfapi-cf_placeholder_range_info_class)
describes resident byte ranges. Neither documentation alone proves that the full
proposed PFC path/read sequence cannot recall content under provider races. That
needs a provider-specific implementation and real transition tests before enabling.
