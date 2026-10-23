# F3 geometry compatibility and photo-first diagnostics

Candidate: v0.18.42. Maintenance run: `8a78d8375bce40a2b7742098add753bd`.

## Evidence and repair

The reported v0.18.41 failure is a TypeError propagating through preview page,
window construction and request handling. Its complete innermost traceback is
not present in the photographs; the private document was not supplied or tested.

Independently reproduced: a ttk distance option can return `_tkinter.Tcl_Obj`;
calling `int()` on that object raises TypeError. The v0.18.41 activity-strip
geometry code performed that conversion during loading. The replacement caches
numeric requested dimensions rather than interpreting Tk's option values. This
also retains the guard against repeated geometry writes and layout feedback.

The regression check obtains a real Tcl pixel object using a `3p` distance and
forces Frame distance reads to return that object while opening valid JSON and
Markdown through the application's Preview entry point. Ordinary rendering,
structured expansion/cancellation and tab state remain in the test scope.

## Photograph-only reporting

New exception records carry an incident ID. Re-raising the same exception through
multiple handlers produces one selectable incident card; independent exceptions
are not merged just because their type or call site matches. Original audit rows
are retained, and older records without IDs remain separate.

The default card prioritizes version, timezone-qualified system time, innermost
location, Python/OS/Tk runtime and propagation events. It does not print arbitrary
exception messages, document content, local variable values or personal paths.
Only an exact known interpreter message is mapped to a fixed explanatory sentence.
The event list reserves a small area so the selected incident can be photographed
without first scrolling through pretty-printed JSON. A 200% font regression check
asserts that the complete representative card is visible.
Full details remain available inside the same window through a display-only
button; this does not enable or disable diagnostic collection or require export.

## Acceptance

Windows checks use sequential ARM64 and Windows-emulated x64 Python
3.13.15 on Win11-ARM64-VM; they are not native x64 Windows acceptance.

Initial validation exposed an undersized diagnostic time column with Windows
proportional digits and missing release-note translations. Those initial failures
are preserved in the maintenance trace; they are not treated as successful tests.

Final candidate SHA-256:
`14d1f3bcec3137a28f46c3a2fbe5dda8be603aec636300012b33a6fe89ae1a8a`.

- Full source/portable regression: 111 groups passed in 468.4802 seconds. The unit
  inventory contains 460 tests, with nine existing skips.
- Windows ARM64: preview tabs/photo diagnostics 34.176 s, structured expansion
  25.573 s, Render reliability 47.248 s; clean task/network/lease cleanup.
- Windows-emulated x64: the same checks passed in 57.311 s, 29.638 s and 62.615 s;
  the identical artifact hash and clean cleanup were verified.
- Native 200% diagnostic screenshots from both runtimes were visually inspected;
  the representative full summary fits without scrolling.
- The VM lease audit confirmed other validation tasks sharing the FIFO queue.
  This task waited about 46 seconds before ARM64 and queued again before x64;
  it did not concurrently control another task's desktop.
- No comparable end-to-end timing baseline or official token counters are
  available; no speed or token reduction is claimed.
