# Window visibility recovery

The v0.17.22 fix addresses a saved window position on a disconnected monitor.
Previously `Commander` restored INI geometry without checking connected screens.
It could remain running outside the laptop display until that monitor returned.

- A Tk-thread guard checks the main window once per second after startup.
- Windows supplies each monitor's **work area**, with the primary first. Negative
  coordinates are valid, and gaps between monitors are not counted as a screen.
- Two identical snapshots are required before recovery, allowing monitor/DPI
  changes and ordinary window moves to settle. Mouse dragging is ignored.
- A reachable title bar leaves the window alone. Otherwise its frame is centered
  in the primary work area, with size capped to that area. Absolute Win32
  coordinates avoid Tk's right/bottom-relative negative geometry syntax.
- Deliberately minimized/withdrawn windows are not restored. They are checked
  when shown again. Valid maximized windows stay maximized, including the
  DPI-scaled invisible resize border. Recovery does not request keyboard focus.
- Normal configuration saving records the corrected geometry; no preferences,
  tabs, folder paths or user files are reset.

Regression coverage: `tests/test_windowplacement.py` (removed/valid monitors,
negative positions, gaps, title access, large frames, DPI borders and debounce),
and `tools/window_visibility_check.py` for source and portable applications.
Offline Windows 11 validation also covers real Win32 placement outside both
edges, automatic recovery, maximized/minimized behavior and INI persistence.
Physical laptop docking, mixed-DPI hardware and an actual cable disconnect are
not available in the VM and still need confirmation on the affected laptop.
