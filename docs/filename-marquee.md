# Long filename scrolling and right-click preference

FilePane labels keep the complete display name (including the existing extension
visibility preference). No middle ellipsis or version-token rewrite is applied.
Path breadcrumbs, tab titles and Compare Target shortening are unchanged.

Only the active pane's focused selected visible row can animate, and only while
the file list has keyboard focus. A Canvas clips the text after the native tree
indent/expander/icon and before the next column. Native item text, path tags and
selection are never replaced by a rolling substring. Raw pointer events are
forwarded in Treeview coordinates, preserving timestamp and modifiers so Tk can
recognize double clicks and drag gestures normally.

Timing: 1 second at the beginning, forward motion at 36 pixels/second times the
font scale, 1.5 seconds at the end, then a new cycle. Animation uses monotonic time
and one 33ms callback for the active name; no filesystem lookup occurs per frame.
Navigation, resizing, scrolling and selection changes recalculate the viewport.
Focus loss, editing, dragging, popups and unmapping cancel animation, and closing
the widget cancels its jobs. Hover help is suppressed for the animated row.

`[view] long_name_scrolling = true` controls the View checkbox. When false, text
is statically clipped, not ellipsized. `[view] right_click_menu = explorer` selects
the native menu; `pfc` selects the existing PFC menu. Missing/invalid values use
true/explorer. Right-click and keyboard context keys share this preference.
Explorer requests still use PFC for virtual archive items or non-Windows systems.
The previous two-second selected-row dwell menu is removed; F8 stays free.

Regression checks: `tests/test_marquee.py`, `tools/marquee_check.py` (package and
portable), the full GUI smoke suite, and offline leased Windows validation.
