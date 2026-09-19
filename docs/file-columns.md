# File columns and status badges

Right-click **a column heading**, not a file, for quick settings. File-row
right-click retains the selected Explorer/PFC context-menu behavior.

`View > File Columns` has the same four groups:

| Column | Options |
| --- | --- |
| Name | Hidden (including Windows HIDDEN), System, filename extensions, mixed file/folder sorting, long-name scrolling, OneDrive overlay, Git / SVN overlay |
| Ext | Show this column |
| Size | Show this column; emphasize GB / TB (bold GB, bold red TB) |
| Date Modified | Show this column; YYYY/MM/DD or MM/DD/YYYY; 24-hour hh:mm, 12-hour 1136a/0515p, or date only |

Click a heading to change sorting; duplicated sorting commands have been removed
from the menus. Name is always present. Hidden
columns have no clickable header; restore them in the main menu. Name receives
freed column space. Display preferences persist in `[view]` of the portable INI;
Hidden/System/filename-extension choices retain their existing per-panel scope.
Timestamp display changes do not rewrite files or discard underlying timestamps.
Midnight is `1200a`; noon is `1200p`. Sorting uses original metadata, not the
formatted date text in ordinary directory listings.

## Fonts

Selected font zoom uses negative Tk pixel sizes, calculated from the original
font and startup DPI. Derived breadcrumb and rich-size fonts preserve that pixel
size instead of converting through `Font.actual()` point sizes. Breadcrumb
redraw restores intended named-font sizes after resume. Rich GB/TB cells retain
their canvases and text items through coalesced redraws instead of unmapping and
recreating them on every request.

## OneDrive: bounded, metadata-only and best effort

Automatic OneDrive roots come from local environment/registered account folders;
assigning a custom cloud-shaped folder-prefix icon does **not** establish that a
folder is synchronized. A single daemon worker queries at most 128 visible items
per batch, at a two-second interval. It never calls Tk, opens file content, runs
OneDrive, requests hydration, or signs in. Dragged rows are excluded from updates.

Square top-left badges distinguish cloud status from round bottom-right Git/SVN
badges (both remain visible when enabled). The two overlay settings are independent;
the Git/SVN switch hides version-control badges and prevents new status scans.
The hover tooltip identifies OneDrive explicitly and explains its availability.
Blue cloud = online only; outlined green check = locally available; solid green
check = always available offline; blue arrows = syncing/pending; red X = error;
amber pause/warning = paused or warning/excluded/incomplete provider state.
Locally available is not permanently pinned: storage cleanup may remove its
local copy. See the [UI/UX review](ui-ux-review-2026-09-19.md) for the full legend
and design proposals.

The native reader uses `SHGetPropertyStoreFromParsingName` with
`GPS_FASTPROPERTIESONLY | GPS_BESTEFFORT` (0x48), never the slow-item flag. It reads
`System.SyncTransferStatus`, `System.FilePlaceholderStatus`, and file attributes.
Errors/paused/transferring take precedence over availability. PINNED alone is an
intent, not proof that a complete local stream exists. Unknown or unsupported
properties produce **no badge**, not an invented "synced" state. If a provider
does not expose a value through fast properties, it is deliberately not queried
using a slower/content-loading fallback.

Microsoft contracts:

- [Fast property-store flags](https://learn.microsoft.com/en-us/windows/win32/api/propsys/ne-propsys-getpropertystoreflags)
- [Sync transfer status](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/ne-shobjidl_core-sync_transfer_status)
- [Placeholder status](https://learn.microsoft.com/en-us/windows/win32/properties/props-system-fileplaceholderstatus)
- [File attributes](https://learn.microsoft.com/en-us/windows/win32/fileio/file-attribute-constants)

Offline tests cover the ABI on ordinary local files, injected provider statuses,
badge rendering, preferences, worker isolation and drag stability. They cannot
prove live OneDrive state transitions on an authenticated corporate account.
