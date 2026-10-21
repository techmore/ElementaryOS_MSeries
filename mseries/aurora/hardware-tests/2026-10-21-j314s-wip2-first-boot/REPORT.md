# J314S Aurora 7.2 wip2: first attended boot, October 21, 2026

**Scoped success with a port-specific dock failure; incomplete qualification.**
The actual boot is `7.2.10-elementary-aurora72-wip2`; live build ID
`e33ad2aa657320824a246a3b04814accdb31df1e` matches the audited Image.
One-shot consumed (`next_entry` empty); persistent default stays `.20`.
Old fallback files and the selected shared `boot.bin` remain unchanged.
[Summary](summary.json), [hardware collector](hardware.json), [smoke](smoke.json).

## Completed checks

- Running boot observed beyond five minutes; PMP ready/started/manages fabric,
  and nonnegative CPU idle-counter deltas.
- All 91 early module hashes and installed package verified. Runtime 37 DART
  providers retain one-cell bindings; GPU/internal/external DCP firmware 13.5.0.
- Real Apple M1 Pro G13S C0, Mesa 26.0.8: shader draw and all 16 RGBA pixels pass.
  1 MiB temporary-file fsync/SHA256 readback passes.
- Owner confirms internal display and input work. Compositor reports internal
  3024x1964 at 120 Hz; later external DP-1 active at 1920x1080/60 Hz.
- Selected severe-message scan through the post-smoke snapshot finds no
  panic/oops/lockup/I/O-error patterns. Display firmware warnings and a Wi-Fi P2P
  address warning also occurred in the previous `.20-enh1` boot. They are not
  silently classified as harmless or a new regression.

## Physical port findings — use the owner's final correction

| Mac USB-C position | Owner result | Scope |
| --- | --- | --- |
| Left, closest to owner/front, farther from hinge | Dock monitor works; picture slow to appear | Scoped visual pass; external 1080p/60 observed |
| Left, nearest hinge/rear | Dock monitor does not work | Failing acceptance check; cause open |
| Right | Not tested | No qualification |

The earlier button answer saying the hinge port worked was explicitly corrected.
Do not propagate it or replace the physical names with guessed logical port IDs.
Initial snapshot had eDP only and no Thunderbolt dock. Later snapshot enumerates
Dell WD22TB4, authorized, and eDP plus external 1080p/60. Log events show training
retries, connection, dock enumeration and DCP `dpin0` routing on two controller
paths (`701ac0000` and `b01ac0000`). This does not prove a picture on both physical
ports. `set_active_lane_count` logged unexpected lane_count4/phy0 while a picture
was nevertheless observed; no clean dedicated rate/lane qualification claimed.

Prior `.20-enh1` also logged 22 AT-register timeouts before one connected event.
These unequal traces do not establish a 7.2 regression or explain the visual
failure. Next controlled comparison must bind the physical port, cable, dock,
monitor, plug-in time, discovery and actual picture; leave audio/display modes,
services and module parameters unchanged for that comparison.

## Evidence limits and next

The collector's `modules/dtbs` hash is the newer packaged on-disk DTB asset;
the selected DTB remains the older legacy J314S tree in unchanged `boot.bin`.
[Runtime/installed verification](installed-runtime-verification.json) records
actual bindings separately. No shared-DTB rewrite was performed.

Active `PowerSaveMode` reporting is still unavailable. Collector control stability
is false; smoke before/after dictionaries comparing equal cannot establish
measured display/power stability. Observed power samples cover startup and owner
hotplug actions; no idle baseline, A/B or energy saving. Raw journal data,
private snapshots and device inventory remain under the owner's private outputs
directory and are not committed.

Next: matched per-port acceptance, then attended return to `.20` to demonstrate
fallback recovery before suspend and power testing. Do not re-arm automatically,
change persistent default, or call this a stable promotion. Full 64-fix semantic
qualification and earlier source-review limits remain open.
