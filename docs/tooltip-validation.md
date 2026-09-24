# Tooltip lifecycle — v0.18.9

## Report and attribution boundary

The user reported a persistent tooltip covering the first tabs after returning
from another application (photo 38936.jpg, PFC v0.18.7). The black message reads
“Click to go back (Alt+Left arrow), hold to see history”. That text is absent from
the PFC source and differs from its yellow path help. A photograph does not expose
the owning process: the source of that black window remains **unconfirmed**.
This release does not manipulate other applications' windows or claim to fix an
external tooltip.

## Confirmed PFC defect and change

Running the previous v0.18.8 ToolTip class in a two-window Tk fixture reproduces
delayed help appearing after focus has already moved to the other window, and
remaining visible without a hovered target. The old class creates globally
topmost windows and depends on Leave/Button events, with no expiry or focus check.

Button/path, tree-row, native-menu and drawn-header-menu help now share one
lifecycle:

- Check visible owner, current focus and actual pointer target before scheduling
  and showing. A 100 ms watchdog exists only while help is pending or visible;
  tree help also verifies the row under the pointer, including scroll without Motion.
- Cancel pending callbacks and visible help on focus loss, owner input/unmap,
  source destruction, scrolling and stale hover. No global topmost attribute.
- Escape or moving onto the help dismisses it; visible help expires in 8 seconds.
  Owner bindings/timers are removed at dismissal rather than accumulating.
- Custom header help uses the same lifecycle. Its former leaf-selection ordering
  scheduled help and immediately cancelled it; scheduling now follows cascade cleanup.
- Reopening a native menu resets its active tooltip entry.

## Validation

`tools/tooltip_check.py` runs actual Tk hover, focus and window lifecycle events,
including an independent Tk process taking OS focus. Run both forms:

```sh
xvfb-run -a python3 tools/tooltip_check.py
xvfb-run -a python3 tools/tooltip_check.py pfc
```

The Linux/Xvfb source and portable checks pass: valid hover, pending/visible
focus loss, external-process focus, Escape, pointer approach, expiry, owner hide,
tree scrolling, native-menu reopen, custom menu closure and source destruction.
Callback exceptions are captured and fail the test. The checks are in the
headless regression runner.

Also passed: the same portable tooltip fixture at 200% Tk scaling, 262 unit tests
(8 platform skips), header popup, three-level menus (source/portable), context
settings (source/portable), portable pathbar, Preview tabs and column menus.
This was a focused regression run, not a new full headless-suite execution.

Windows VM1 was leased and kept offline. Candidate files were staged using QGA,
but the fixed PFC-Test credential was rejected at interactive login; no native
tooltip test ran. No credential reset, network enable or VM reset was attempted.
The lease was released. **Native Windows acceptance and attribution of the black
tooltip in the user's photo remain open**, not counted as passing tests.
