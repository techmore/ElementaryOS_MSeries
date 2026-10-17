# Power audit + dynamic-refresh (ProMotion) investigation

Branch `power-usage`, 2026-10-16. Owner request: "deeply audit and optimize power usage" and
"nail an implementation for dynamic refresh rate like Apple does" (idle/agents ~low fps,
YouTube 120). Honesty rules from `POWER-ROADMAP.md` apply: every number is *measured* or
*estimate*, nothing display/audio/kernel is changed without the owner's explicit yes.

## 1. What was done

* Killed the `mseries-windows` qemu VM (owner request) — power fell **59.2 W → 41.5 W median**
  (measured, 10 s each). Only an orphaned root-owned `swtpm` remains (harmless, ~0 W; it
  respawns under `systemd --user`, so stop the unit rather than the process).
* Live read-only audit of power, idle, IRQs, tunables, services, display mode.
* Traced the built-in panel's refresh path through the running kernel driver, the Asahi
  `fairydust` tree, and the owner's kernel source trees.

## 2. Measured snapshot (box busy with agents, not idle)

| Metric | Value |
| --- | --- |
| SMC total system power, VM killed | median 41.5 W (min 39.4, max 46.1) |
| SMC power with VM running | median 59.2 W |
| Display | eDP-1 3024x1890 **@120.000 Hz, is-current**; brightness 500/500 (100%) |
| Idle, cpu0 | ~2800 wakeups/s; deep idle (CPU PD) only ~12% |
| `arch_timer` IRQ | ~8800/s (HZ=1000 tick) |
| `IPI1` | ~13500/s |
| Continuous CPU | Gala ~20%, `claude-desktop` 52%+27%, `ai.opencode.desktop` 28%+27% |
| Battery | health 92.4%, 94 cycles, 80% charge limit working |
| Tunables | schedutil, no EPP, no cap (on AC); PCIe ASPM `[default]`; Wi-Fi PS on; USB autosuspend 11/22 |
| Services | rpcbind, cups, cups-browsed, avahi-daemon, geoclue active |

Display and app/compositor CPU are the two dominant, addressable blocks; deep-idle and the
audio amp are kernel/audio-gated.

## 3. Dynamic refresh: what the hardware and driver actually do

Traced through `drivers/gpu/drm/apple`:

* The DCP firmware exposes adaptive sync via **`IOMFBPARAM_ADAPTIVE_SYNC`** (`iomfb.h:55`),
  where `value[0]` is the **minimum refresh rate in 16.16 fixed point** (0 = VRR off).
* `iomfb_template.c:dcp_on_set_parameter()` sends that parameter **with `value = {0}`** — i.e.
  VRR is explicitly **disabled** on every power-on. This is the `minRR = 0x0` line in the DCP
  log. For the internal panel (`dcp->main_display`) the parameter is not sent at all.
* `parser.c` parses `MinimumVariableRefreshRate`/`MaximumVariableRefreshRate` from the DCP
  TimingElements and **marks the 120 Hz mode `vrr = true`** — but only so that
  `use_timestamps` is set, which is the Asahi 6.19 hack that lets the DCP drive 120 Hz at all.
  The comment is explicit: *"We still do not know how to drive VRR ... at least setting
  timestamps drives the display at 120 fps."*
* There is **no KMS VRR plumbing**: no `vrr_capable`, no `vrr_enabled`, no `drm_crtc_set_vrr`.
  `connector` debugfs `vrr_range` reads `Min: 0 / Max: 0`.

**Conclusion:** the running kernel gives a *fixed* 120 Hz (via the timestamp hack); it does
**not** do adaptive sync, and mutter can't see VRR. So the panel never drops below 120 Hz when
idle.

Asahi's own status (progress reports / PR "drm: apple: Adaptive Sync/ProMotion"): DCP adaptive
sync is driven by that one parameter; the internal 14"/16" ProMotion panels support
**[24, 120] Hz**; because DCP needs a modeset to change VRR state they cannot yet expose it
through KMS, so they shipped a `appledrm.force_vrr` module parameter that turns VRR on
unconditionally without telling the compositor.

## 4. Patch: enable adaptive sync (`force_vrr`)

`mseries/power/patches/0001-appledrm-adaptive-sync.patch` (vs the owner's dpin tree, commit
`46bb8b6`) adds:

* `bool force_vrr` module parameter (`appledrm.force_vrr`).
* When set, `dcp_on_set_parameter()` programs `IOMFBPARAM_ADAPTIVE_SYNC` with
  `value[0] = 24 << 16` (24 Hz min for the 14"/16" panel) instead of 0.
* For the internal panel, `iomfb_poweron()` routes through `dcp_on_set_parameter()` so the
  minRR is set **before** the modeset.

Verified: the three files (`dcp.c`, `dcp.h`, `iomfb_template.c`) compile and link into
`appledrm.o`. (A standalone `make ... appledrm.ko` then fails at `modpost` because this tree
has no `vmlinux` — expected; build it inside the full kernel build as usual.)

## 5. Plan

* **Stage 1 (this patch):** build `appledrm.ko` with the fairydust kit, install, boot
  `appledrm.force_vrr=1`. Measure whether Gala idling the frame clock lets the panel fall to
  24 Hz (SMC power + `vrr_range`/DCP log). Risk: display driver change → needs reboot; keep a
  stock/GRUB fallback.
* **Stage 2 (Apple-like):** expose VRR to KMS (`vrr_capable` + `vrr_enabled` → program minRR
  and take the modeset internally) and enable VRR for the monitor in Settings/DisplayConfig,
  so mutter schedules with the deadline timer instead of a fixed 120 Hz clock.
* **Stage 3:** if the compositor still repaints under load, profile Gala's redraw path and the
  Electron agents in place (owner's chosen direction).

## 6. Open questions

* Approve Stage 1 build + reboot (kernel module change)?
* Keep the driver edits in the owner's kernel tree, or land only the patch file in this repo?
