# Folder icon identity — v0.18.2

## Cause and fix

Windows Shell provides path-specific icons for Known Folders and folders with
`desktop.ini` customization. Previously every directory shared the `<folder>`
cache key. Whichever folder was drawn first supplied the image for all folders
with the same status badges. Changing font size recreated the provider, so the
incorrect icon depended on the new load order.

Directory and shortcut/icon-file keys now use lexical absolute paths (without
resolving links or reading directory contents). Regular files still share their
file-type icons, and executable lookup still uses the safe generic `.exe` icon.
VCS and cloud badges remain independent parts of the cache key. This changes
neither the native icon artwork nor the navigation-tree/prefix-button icons.

Each provider keeps at most 512 recently used entries. Visible and retained tree
rows hold their own Python image references: Tcl image names alone do not keep
`PhotoImage` alive. Navigation, preview and result replacement release those row
references only after deleting the old rows. Clipboard images already have their
own references. A deferred refresh during dragging also retains the old images
when a font-size change replaces the provider.

## Regression coverage

- Complete `tools/run_headless_checks.sh`: 234 unit tests (8 platform skips) and
  64 package/portable GUI check invocations passed. The expanded folder-icon
  lifetime checks also passed separately against both builds and on Windows.
- Unit regression fails on the old implementation in both directory orders;
  separate overlay identities, extension reuse and LRU eviction are checked.
- `tools/folder_icon_check.py` runs against package and portable builds. Colored
  Shell responses make aliasing detectable even on Linux; a two-entry cache
  forces eviction while more rows are displayed. It exercises navigation,
  search, preview, nested trees, clipboard and deferred-drag image lifetimes.
- Windows 11 ARM64: portable build passed direct uncached Shell PNG equality for
  Known Folders and ordinary folders, in both orders, at 100/175/125/200/100%.
  A separate 175% screen review confirmed distinct folder artwork. A 200-folder
  local fixture loaded cold in 0.328 s and refreshed cached in 0.024 s on the test
  VM; these are observations, not cross-device performance guarantees.
- Native drag/refresh and cloud-metadata checks passed. The cloud test injects
  seven status states and checks painting, preferences and row stability; it
  does **not** claim online OneDrive synchronization was tested. VM networking
  remained disabled.
