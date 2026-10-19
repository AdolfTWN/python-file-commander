# Icon corners and navigation latency — v0.18.32

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
