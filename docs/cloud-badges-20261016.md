# OneDrive badge visibility — v0.18.31

User task: distinguish online-only, locally available, retained offline,
syncing/pending, error and paused states at actual icon size, including selected
rows. This is a rendering repair, not a change to sync-state inference.

## Observations and changes

The previous local-copy badge used a white face and thin green check; it faded
against pale file icons. Online-only and syncing shared blue. A colored outline
alone provided little separation from the icon underneath or the selection bar.

| State | New glyph and face |
|---|---|
| Online only | White cloud on deep blue |
| Locally available | Thick white check on deep green |
| Always available offline | White check with underline on darker green |
| Syncing / pending | Opposing white arrows on purple |
| Sync error | White cross on red |
| Paused | Black pause bars on yellow |
| Warning | Black exclamation mark on yellow |
| Unknown / no metadata | No badge; never treated as synchronized |

Badges retain the square upper-left location; Git badges remain round and
lower-right. White outer and dark inner keylines isolate the badge from light,
dark and selected backgrounds. Glyph strokes increase from normalized .05 to
.065; the badge grows from 55% to 62% of the base icon, or 56% when sharing an
icon with a VCS badge. Base icons, path-specific cache identity, state keys and
image ownership remain unchanged. No new Shell/provider/content reads occur.

All seven face/ink pairs have at least 4.5:1 solid-color luminance contrast.
This is a palette guard, not a claim that every antialiased edge pixel has that
contrast or a substitute for visual inspection. Colors are paired with different
glyphs; paused/warning and local/retained do not rely on hue alone.

## Verification contract and limits

Maintenance trace: `9df1f68f1e6743a3b0a261cbfc2cb14b`.
Before/after fixtures are private `/tmp/pfc-cloud-before-*.png` and
`/tmp/pfc-cloud-*.png`. They composite the actual glyphs over representative gold
folder faces, on light/dark/selection backgrounds at 100/175/200% icon scales.
Small fixture headings are not product UI; large captures identify the states.

Regression coverage includes glyph distinction from 8px upwards, palette contrast,
invalid/unknown state rejection, unchanged metadata precedence, non-cloud/missing
native paths, async status cache, tooltip descriptions, preference toggles, drag
deferral, zoom and independent file-icon identity with both badge types.

Windows checks use the leased dual-runtime adapter, Python 3.13.15 ARM64 and
Windows-emulated x64, with matched candidate bytes and sequential desktop tests.
No guest network, live cloud account, hydration or sync transition is exercised;
the seven UI states are injected fixtures. These results do not establish native
x64 Windows Shell/provider compatibility or guarantee a remote upload completed.

## Matched Windows results

- Final portable SHA256:
  `d8481993d7b086a76400dbbe067bbe18a8e7b7bed4f4e547022dab0cade8f6d0`.
- ARM64 Python 3.13.15: cloud overlay and folder icon checks passed in
  12.852 and 21.282 seconds; request `1534a3b699ef426ba26ea1e4e95037df`.
- Windows-emulated x64 Python 3.13.15: same checks passed in 17.701 and
  38.215 seconds; request `131cea8746ce49bcbdc2b87c83191815`.
- Both reports match the candidate, verify architecture and confirm cleanup.
  Native captures inspected: single versus underlined checks, arrows versus
  cloud, error cross, pause bars and warning remain distinguishable on selected,
  light and dark backgrounds. No guest network was enabled.

These are developer rendering/interaction checks, not live OneDrive acceptance.
Check timings exclude staging/readiness and cannot be claimed as task speedups.
Token counters are unavailable; no comparable whole-task baseline is established.

Final full regression passed: 405 unit tests completed (9 platform skips), plus
all 98 GUI checks in the declared source/portable routes (99 runner checks).
The baseline fixture initially reused row IDs across a font-triggered refresh;
that test assumption was corrected before implementation. No product bug or
passing baseline was inferred from that failed fixture attempt.
