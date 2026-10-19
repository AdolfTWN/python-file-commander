# Icon corners and navigation latency — v0.18.32

Current implementation: **v0.18.33 amended 2026-10-20**, attached beveled
triangles (last section). Earlier layouts and test evidence below are historical,
not current visual acceptance.

Owner-approved layout supersedes the v0.18.31 cloud glyph layout:

- Top-left: existing Git/SVN symbols, palette and diameter formula unchanged;
  only placement changes. Standalone size remains 70% (minimum 12px); shared
  cloud/VCS mode remains 50% (minimum 8px), capped at base icon size.
- Top-right: color-only northeast triangular pennant, 38% of base icon size,
  minimum 8px. Its southwest half is transparent. Thin light/dark keylines
  separate the color from selected, light and dark backgrounds; no inner glyph.
- Bottom-left: preserve the Windows Shell icon, including shortcut adornments.
  Bottom-right: no PFC overlay. Regression compares the full lower quarter with
  the original base image at 16/24/42/48/80px, alone and with both PFC overlays.

| Local metadata state | Triangle |
|---|---|
| Available / pinned and in sync | Bright blue; offline-retention detail stays in tooltip |
| Sync error | Bright red |
| Syncing / pending | Orange, not completion blue |
| Online only | Cyan; not mislabeled an upload error |
| Paused | Yellow |
| Warning | Pink |
| Unknown / absent | No triangle; never claimed synchronized |

Blue is based on the existing last-known local IN_SYNC + local primary-stream
metadata, not a new remote verification. Status precedence and non-hydrating
provider calls are unchanged. Per the owner this indicator is color-only;
tooltip and Settings descriptions retain explicit meanings. It is not a claim
that colors alone are distinguishable for every color-vision condition.

## Latency changes and evidence

The cloud worker remains single, asynchronous and limited to 128 visible items
per batch. A changed visible-path set clears the previous viewport's refresh
delay and starts from its first item; unchanged views keep the two-second
cadence. An active old worker is not duplicated; after it finishes, the latest
visible set is scheduled, retaining path-keyed last-known results for reuse.
This removes the inherited timer wait, not OS/provider read duration.

Both pure PNG renderers now have bounded 128-entry caches by size/state. Tk image
ownership remains in the existing per-provider cache. No new GUI-thread file,
network or provider reads are introduced.

Same-host microbenchmark against v0.18.31, 50 repeated 16px cloud/VCS request
pairs: old uncached rasterization 1.399295 seconds; current warm cache 0.000010
seconds; current first cold pair 0.026345 seconds. Each renderer recorded 50
hits / 1 miss. This isolates PNG reuse, not folder navigation or total application
speed. Existing VCS glyph bytes matched the baseline for every state at five
sizes. A blocked-reader unit fixture proves scheduling returns while the worker
waits and switches directly to the latest viewport without parallel workers.

Trace: `7ce32334828c4146ba3bc98dea467dbf`. Private baseline fixture:
`/tmp/pfc-cloud-before-triangle-200.png`; current fixture captures cover
100/175/200%, light/dark/selected rows, and no-VCS/modified/clean combinations.
Windows validation must use the same candidate under Python 3.13.15 ARM64 and
Windows-emulated x64. Network stays disabled; injected cloud states do not prove
live OneDrive transitions or native x64 Windows compatibility. Provider/OS stalls
can still delay a fresh status; unknown is never displayed as success.

## Matched Windows evidence

- Candidate SHA256:
  `ec5916ddf8df506b1e5a9bc9cc1b275d8bba5c08f5c4fb41e0e74322c751f794`.
- ARM64: cloud overlays, folder icons and Git GUI passed in
  10.478 / 8.844 / 6.038 seconds, request `73812b5c87cb47fabe38c6fcbf09f7ec`.
- Windows-emulated x64: same checks passed in 13.146 / 11.309 / 7.874 seconds,
  request `bacd405a7893486d9f5ba291b2591dfb`.
- Both used real Git CLI in isolated disposable repositories, confirmed
  architecture and cleanup, and tested the same candidate without guest network.
- Eight known-subfolder first paints: ARM64 15.6–22.7ms, x64 23.1–36.7ms;
  neither issued additional Git commands during warm navigation. This does not
  bound cold repository scans, native Shell reads or live OneDrive provider time.
- Inspected 100/200% fixtures: the two top-corner indicators remain separate;
  lower Windows adornments and lower-right base pixels survive. No PFC status
  columns or additional mouse-hit targets are introduced.

Token usage is unknown; whole-task comparison requires matching scopes and is
not inferred from the raster-cache microbenchmark or these native timings.

Final full regression passed: 407 unit tests completed (9 platform skips) and
all 98 GUI checks across the declared source/portable routes (99 runner checks).

## v0.18.33 visual follow-up — 2026-10-19

The owner reported that v0.18.32's inline triangle still looked like a folded
or missing icon corner, especially on blue icons. This supersedes the inline
triangle geometry above, not its metadata meanings or status precedence.

Compared at identical sizes/backgrounds:

- Current: inline triangle, partially covering the base icon.
- A: separated triangle in trailing space; less color merging, but still reads
  as a corner fold.
- B (selected candidate): separated circular color-only lamp at the upper right.
  White/dark keylines separate it from light, dark and selected-blue rows.

The lamp is wholly outside the original icon rectangle. Diameter is 34% of the
base icon (minimum 10px), with at least 2px clearance on either side. All rows
reserve the same trailing space, including unknown/no-cloud states, so late
status arrival does not shift filenames. Compared with v0.18.32 this costs about
7–9 additional pixels at 100% rather than adding a new status column. Git/SVN
glyphs and sizing stay unchanged at top-left; both lower corners remain reserved.
No queries, animations, per-row widgets or settings were added. The existing
bounded PNG cache and asynchronous visible-item refresh remain in place.

Native Windows comparisons use the same actual Shell Desktop/Pictures/Documents
icons in each variant, plus explicitly synthetic blue/purple/gold fixtures.
Rows cover no VCS, modified Git and clean Git against light/dark/selected
backgrounds. [100% comparison](images/cloud-status-compare-100.png) and
[200% comparison](images/cloud-status-compare-200.png) show all three variants.
This is a visual judgment, not measured user acceptance; the release is for the
owner's visual trial. Color-only accessibility limitations and explicit tooltip
meanings remain unchanged.

Trace: `4ef1eae82a5e4ba682b92fa1c886f847`. Candidate SHA256:
`7a22475d1c7b203721c2c8f0ac0dbb7f90e3210fed1a22e7f98e27848c14acca`.
Both Python 3.13.15 profiles tested the identical portable artifact, sequentially
on Win11-ARM64-VM with networking disabled and confirmed cleanup:

| Runtime | Cloud / folder / Git GUI checks | Request |
|---|---|---|
| ARM64 | 12.054 / 9.040 / 6.230 seconds | `613d34e9088d41faac8da8b60510cd2d` |
| Windows-emulated x64 | 13.680 / 10.669 / 6.857 seconds | `f3431466e8a54b16a1748a78b8311078` |

Real Git CLI warm navigation across eight subfolders issued zero additional Git
commands: first paint 13.6–20.2ms ARM64 and 18.8–26.0ms x64. These checks do not
establish live OneDrive synchronization, cold-provider latency, whole-navigation
speedups or native x64 Windows acceptance. Pixel regression at 16/24/42/48/80px
checks that every original base-icon pixel survives the cloud lamp unchanged
(apart from the intentionally retained top-left Git overlay), and that status
changes preserve image width. Token usage is unknown; no comparable whole-task
baseline is claimed.

Final full regression passed: 408 unit tests completed (9 platform skips) and
all 98 GUI source/portable checks (99 runner checks including the unit suite).

## v0.18.33 amended — 2026-10-20

Owner rejected the separated lamp: it detached status from the icon. The owner
reported not downloading it and explicitly requested withdrawing/reusing
v0.18.33. Main history is preserved; only this version tag is repointed, using
the old object `9366d85c09163eb90d8d12caa93951a464476424` as an exact lease.
The 2026-10-19 separated-lamp recommendation above is superseded, not accepted.

The new color-only triangle is attached **inside** the upper-right icon corner.
A continuous white diagonal bevel and dark lower lip give separation from the
underlying Shell icon and selected-blue background without an external gap.
Compared original thin edging, a moderate white bevel/shadow, and a heavier
white bevel on identical icons and states: selected the moderate bevel because
it retains more colored face than the heavy variant while making the diagonal
noticeable. This is developer visual review, not owner acceptance. See the
[100% native comparison](images/cloud-status-raised-100.png) and
[200% native comparison](images/cloud-status-raised-200.png). After the owner's
additional lightness suggestion, the final figures compare thin/fixed/adaptive
triangles, with the **rightmost adaptive candidate** selected (see below).

- Size: 42% of the base icon, minimum 8px, capped at half the base width so it
  cannot cover the compact top-left Git/SVN overlay. Restored normal filename
  spacing; no lamp space, status column, reflow or extra click target.
- Local in-sync / pinned: bright cyan-blue `#00d9ff`, instead of the common
  icon blue. Online-only: light violet `#b9a7ff`, to avoid conflating the two.
  Error red / pending orange / paused yellow / warning pink stay unchanged.
  No triangle still means unknown, not verified synchronization. Tooltips and
  Settings legend reflect the revised palette; status-reader semantics unchanged.
- Bottom corners and pixels outside the upper-right badge square remain intact.
  Regression checks actual composed images at 16/24/42/48/80px: no detached pixels
  in the text gap, unchanged row width, white bevel / dark lip / bright color
  surviving rasterization, unchanged lower quarter and top-left VCS placement.
- No extra metadata queries or workers. Bounded PNG caching and asynchronous
  visible-item metadata scheduling remain. No network or live OneDrive test.

Trace `23d64e6a94e74db6bbbae62c2901f1b4`; initial fixed-face portable SHA256
`4d86c393a05d44291482ddbe7c0c3b56528db5a43e57e211d6cb193df6509909`.
ARM64 Windows Python 3.13.15 cloud/folder/real-Git checks passed in
11.654 / 8.436 / 6.026 seconds, request `fa8be8cf9e3842f1ba05ae614b6abaf9`,
cleanup confirmed. Warm Git navigation: 14.9–20.7ms, zero extra Git commands.
The same SHA passed on Windows-emulated x64 Python 3.13.15 in
15.504 / 10.676 / 6.277 seconds, request `4ea45029878f47f8a539ac3173b54910`,
also with confirmed cleanup. x64 warm Git first paint: 16.7–27.9ms and zero
extra Git commands. These are warm fixture timings, not proof of cold Shell or
live cloud-provider latency; ARM Windows does not establish native x64 acceptance.

Same-version publishing requires a precise mirrored tag correction. The mirror
workflow now honors only **forced GitHub tag events**, using that event's prior
object as an exact `--force-with-lease` expectation for that single GitLab tag.
It never force-pushes branches or arbitrary tag sets. Four isolated local Git
tests cover authorized replacement/idempotency, stale leases, nonforced/branch
events and invalid old SHA rejection (`.github/tests/test_mirror_tags.py`).
No stored credentials or global Git settings were changed.

### Adaptive face follow-up in the same task

Owner suggested brightening similar icon/overlay colors. Compared fixed and
adaptive faces on synthetic exact-match cyan/red/green/violet cases, in addition
to real Shell icons. Retained the white bevel and dark lip, adding only a bounded
lighter face when a majority of up to three opaque, already-loaded icon samples
have similar hue/lightness. Never recolor the source icon or sample selection-row
background. Transparent/neutral/dissimilar pixels do not trigger lightening.
Hue is preserved; HLS lightness rises by at most .16 to .74. Already-pale states
stay unchanged, avoiding white-washed status colors. This is not a grayscale or
color-vision accessibility guarantee; explicit tooltip meanings remain necessary.

Composition and the decision are cached by the existing per-provider state key;
PNG variants remain bounded to 128 entries. No extra Shell/file/cloud/network
reads or workers. Same-host microbenchmark: three loaded-pixel samples plus
decision median **5.45 microseconds** across 5 × 10,000 calls. This isolates CPU/Tk
pixel work, not native provider or end-to-end folder navigation latency.
The final comparison's fourth row deliberately matches each icon to its status
color; the adaptive face remains distinguishable without moving off the icon.

Final adaptive candidate SHA256:
`4b37910c16c328b05483f68a7f008b7f322caafeb2678d3a31d3359f21c2c56e`.
The earlier fixed-face Windows results above are not final adaptive acceptance.
Both profiles were rerun on this final artifact with confirmed cleanup:

| Python 3.13.15 runtime | Cloud / folder / real-Git GUI seconds | Request |
|---|---|---|
| ARM64 | 11.665 / 8.846 / 5.030 | `afa145ad85854c1cb12ce0a13d58ed6d` |
| Windows-emulated x64 | 15.502 / 10.687 / 7.255 | `082bd1a1ede547048bfae98bbe29f6f1` |

Pixel checks cover every state against a matching-color icon at all five sizes,
and repeated cached access performs only one Shell-load fixture call. Network
remained disabled; live OneDrive sync and owner visual acceptance remain untested.

Final full regression passed: 410 unit tests (9 platform skips), all 98 GUI
source/portable checks (99 runner checks including unit suite), plus the four
isolated mirror-tag safety cases. Final real-Git warm-navigation first paint was
15.2–24.2ms ARM64 and 15.3–27.2ms x64, zero additional Git commands in eight
subfolder switches each. No end-to-end speedup or token saving is inferred;
token counters and a comparable whole-task baseline are unavailable.
