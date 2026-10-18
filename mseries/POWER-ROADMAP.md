# Power and battery-life roadmap

## Current Aurora implementation and qualification — 2026-10-18

The owner's new kernel/release request authorizes the source port and frozen
feature-release work in [the implemented plan](aurora/ENERGY-PORT-PLAN-2026-10-18.md).
It supersedes the older "kernel: data only" task ownership below. The .20
baseline already carries the J314S PMP/DCS fix, idle fabric governor, external
scanout votes and optional Thunderbolt sleep controls. A fresh source comparison
with the draft unified 7.2.10 rebase found no new M1 Pro energy implementation
in those helpers to duplicate. VRR is already implemented in `.20` (the older
"not confirmed" note below is superseded).

The exact current kernel/boot/module/configuration identity now has scoped
hardware evidence and an experimental freeze. Native source enhancement
builds and a separately pinned PR #139 candidate are integrated. Suspend/
recovery/steady workloads/paired energy results remain acceptance gates.
The 64-fix review parity inventory keeps 7.2 build-only until shared GPU/SEP
gaps are resolved. The `.20-enh1` lane retains all reviewed baseline fixes.
Future energy captures record active refresh/VRR/layout/DPMS; exp1 did not
capture active refresh and remains observational. Existing freeze/pin history
is enforced in CI. No refresh, brightness, audio or sleep setting was changed; no watt saving is
claimed. [Hardware status and policy](aurora/hardware-tests/README.md).
Both native profiles passed CI run 39114197052. The exact `.20-enh1` build is
published as a frozen build candidate with all eight asset digests verified;
it has no hardware qualification. Baseline exp1 remains the only running-kernel
freeze, with scoped hardware evidence.

Owner request 2026-10-16: investigate every opportunity to lower light-load power and extend battery runs; document goals
and a comprehensive plan. This is the single plan; evidence is in `POWER-OPPORTUNITIES-2026-10-16.md` and the optimization
repo (`techmore/ElementaryOS_MSeries_Optimization`, `docs/RESULTS.md`). `EFFICIENCY-GOALS.md` keeps the original targets.

Honesty rules (from earlier incidents): report medians and p10/p90, alternate A/B at least three times, never claim a win
from one run, label every number *measured* or *estimate*, never change brightness, refresh rate or display power without
the owner's explicit yes, and leave the kernel to DeepSeek and the audio stack and `speakersafetyd` to the owner.

## Measurement workflow update (2026-10-17)

See the [power documentation map](power/README.md), [baseline instructions](power/macos-baseline/README.md)
and [generated parity checklist](power/macos-baseline/PARITY.md) (11 categories, 52 items).
The retained macOS capture contains inventory and historical sleep only; active scenarios and matched Linux
trials remain open. The fixed watt targets below are planning targets, pending measured macOS workload baselines.
Dock HDMI has a separate branch frontier linked from the power map; older dock notes are historical evidence.

## 1. Goals

| Goal | Today | Target (tier 2, within 1.5x of macOS) | Parity (tier 3) |
| --- | --- | --- | --- |
| Light use (web/office, apps open) | ~14 to 17.6 W measured at 105 to 350/500 | 8 W | 6.5 W |
| 1080p video | 13.2 W local hw decode; 17.7 to 19.3 W YouTube in Brave | 7 W | 5.5 W |
| Idle, screen on, 20% | ~9 to 10 W (best realistic, 60 Hz) | 5 W | 4.5 W |
| Sleep (lid closed on battery) | **unmeasured** | <=1%/h | <=0.5%/h |
| Burst to full speed | CPU ramp 76 to 79 ms measured | <=5 s all cores+GPU, back to low power <=30 s | same |
| Battery wear | 92% health, 93 cycles, 80% charge cap active | keep | keep |

Runtime on the 64.5 Wh pack (`energy_full`): 8 W is ~8 h, 6.5 W is ~10 h, 4.1 W is ~15.7 h.

## 2. Baseline (2026-10-16, read-only)

- Whole machine (SMC `Total System Power`) 17.6 W then 20.5 W on battery with agent apps open; CPU 83% idle.
- GPU jobs/s by process (measured, 3 x 5 s): ChatGPT desktop 4,000 to 5,000; gala 840; claude-desktop 360; Xwayland ~240.
- The ChatGPT app is an **X11 client under Xwayland** (`xlsclients`); Claude Desktop and Brave run native Wayland.
- Gala bursts 9 to 60% of a core; 72 CPU-min over 9.5 h. Interrupts: display mailbox ~480/s, second mailbox ~430/s, audio DMA ~730/s.
- CPU0 idle residency: WFI 19.8 s vs deep `CPU PD` 1.4 s (about 7% of idle time deep). Only these two idle states exist.
- Suspend is **s2idle only** (`/sys/power/mem_sleep` = `[s2idle]`); idle suspend after 15 min on battery; lid = suspend.
- Wi-Fi power save on; NVMe default max APST latency 100 ms; PCIe ASPM policy default; THP not present.
- Speaker PCM and speaker-safety capture PCM `RUNNING` since boot despite the 30 s idle override.
- Incus containers running (`rupert-dev` was running `rails test` at 98% of a core): background dev workloads count against the floor.

## 3. Workstreams

Gate key: **free** = I can do it without the owner; **owner** = needs a yes (display, audio, restarts); **kernel** = DeepSeek.

### A. Apps and compositor (largest suspected floor)
| ID | Item | Est. | Gate | Verification |
| --- | --- | --- | --- | --- |
| A1 | ChatGPT/Codex app to native Wayland (`ELECTRON_OZONE_PLATFORM_HINT=auto`, installed 2026-10-16 via `install-electron-wayland.sh`, active at next login) | Unknown; could cut its 4-5k jobs/s | free (done), needs owner login | Re-trace `drm_sched_job_queue`, paired power A/B at same app state |
| A2 | Paired power A/B with the ChatGPT app closed vs open | Isolates its watts | owner (closing) | `powerlab/ab.py`, 10 x 12 s |
| A3 | Find why the app renders continuously (animation, WebGL, video, devtools); try `--disable-gpu-vsync`-style and `--disable-features` flags in a throwaway profile | Large if it idles | free after A2 | GPU jobs/s at idle < 500 |
| A4 | Same audit for Claude Desktop (360 jobs/s), Signal (3 scopes), Chromium apps | Medium | free | per-app jobs/s table |
| A5 | Profile Gala for 60 s (needs `perf`/sysprof, not installed; ptrace denied); attribute to our patches vs shadows/blur vs clients | Up to ~0.5 to 1 W | free to install perf (apt), owner OK | A/B Gala with a patch disabled |
| A6 | Auto-pause heavy background apps when idle/on battery (suspend/SIGSTOP policy, per-app list the owner picks) | Medium | owner | paired A/B |
| A7 | Throttle dev containers on battery (incus CPU limits when `power-saver`) | Depends on use | owner | container CPU while idle |

### B. Display (owner decides; all measured earlier)
| ID | Item | Est. | Status |
| --- | --- | --- | --- |
| B1 | 60 Hz on battery (`tuning/refresh-rate`, opt-in) | -1.7 to -2.0 W measured | waiting for the owner's yes |
| B2 | Dynamic/variable refresh (Mutter VRR, DCP support unverified) | Between B1 and 120 Hz | read-only investigation first |
| B3 | Adaptive brightness curve, lower floor, dim-on-idle policy | -0.7 W (21% to 5%); -4 W (500 to 105) | owner (brightness) |
| B4 | Dark mode saves no panel power on this mini-LED LCD; do not claim one | 0 | recorded to avoid a false claim |

### C. Audio
| ID | Item | Est. | Gate |
| --- | --- | --- | --- |
| C1 | Let the DSP filter chain and speaker sink suspend when idle (speaker PCM RUNNING since boot) | ~1.2 W low-confidence | owner (audio stack, pops) |
| C2 | Keep `speakersafetyd` untouched; ask upstream whether its capture can pause with the sink | n/a | owner |

### D. Video
| ID | Item | Est. | Gate |
| --- | --- | --- | --- |
| D1 | Ship the H.264-only MV3 extension + VA-API flags for Brave (`browser/h264only`) | -1.5 W while playing | free to package, owner to enable |
| D2 | mpv/IINA-style default player with `--hwdec=vaapi` | -5.3 W local files | free |
| D3 | VP9/AV1 decode in the AVD driver | big for YouTube | kernel |

### E. Kernel and idle (DeepSeek's; contribute data only)
| ID | Item | Est. | Notes |
| --- | --- | --- | --- |
| E1 | `CONFIG_HZ` 1000 to 250 | unmeasured | `arch_timer` ~3.9k/s across cores |
| E2 | DP-tunnel DPRX poll back-off (patch draft exists, unbuilt) | 36% of idle work items | kernel owner builds |
| E3 | DRM scheduler job traffic and DCP/mailbox chatter (~480/s) | unmeasured | find the sender |
| E4 | Deeper idle: CPU PD entry rate, `teo` was worse (+0.8 W), keep `menu` | n/a | measured |
| E5 | s2idle drain; is deeper sleep possible on this SoC | unknown | see F1 |

### F. Standby and battery longevity (not yet measured at all)
| ID | Item | Gate |
| --- | --- | --- |
| F1 | **Measure sleep drain**: charge level delta over a 30-min and an overnight s2idle with `rtcwake -m freeze`, lid closed, Wi-Fi on and off; list wake sources (`/sys/power/wakeup`) | owner (blanks the screen, ends the session briefly; schedule it) |
| F2 | Wake-source audit: Bluetooth, Wi-Fi WoWLAN, USB, lid, keyboard, `omarchy-wifi-resume-fix.service` (15 s in boot blame) | free after F1 |
| F3 | Hibernate/hybrid or suspend-then-shutdown after N hours on battery | owner |
| F4 | Keep 80% cap; consider an "optimized charging" schedule (hold at 80, top up before the owner's usual unplug time) | free design; owner |
| F5 | Thermal/fan: temperature 32.1 C at rest; verify no throttling during burst | free |

### G. Services, tooling and regression guard
| ID | Item | Est. | Gate |
| --- | --- | --- | --- |
| G1 | Disable unused daemons for hygiene (rpcbind, rpc-statd, cups, avahi, cups-browsed, zeitgeist, geoclue demo agent): each < 0.1 W measured | ~0 W; smaller attack surface | free, owner prefers |
| G2 | Fold measured levers into `mseries-profile` (`battery`, `balanced`, `burst`) with an uninstall path | convenience | free |
| G3 | Power canary: a scheduled 60 s idle sample logged to a CSV (median, p10/p90, top GPU jobs by app) so regressions surface | detection | free |
| G4 | Panel indicator: show top power consumer / "heavy app" hint | UX | free |
| G5 | Fix measurement noise: ignore runs while `top` shows other tasks; always log source (SMC vs battery flow) | trust | free |

## 4. Roadmap

**Phase 0, measurement hygiene (this week, free).** G3 canary, G5 rules, record baselines for each scenario (idle 20%,
web loop, 1080p local video) at the owner's current display settings without changing them.

**Phase 1, no-regret changes (free, ship with uninstall paths).** A1 (done, active at next login), D2, D1 packaging, G1/G2,
A4 audit, install `perf` and run A5 once the owner agrees to installing a package.

**Phase 2, owner decisions (ask once, batch).** B1/B2 refresh, B3 brightness policy, A2 close-the-app A/B, A6/A7
background policy, C1 audio idle, F1 overnight sleep test, F3/F4 battery policy. Present as a short list with measured
savings; apply only what is approved.

**Phase 3, kernel coordination.** Post E1 to E3 evidence on DeepSeek's kernel issue; test patches in the edge lane only;
re-measure each with paired medians.

**Phase 4, parity push.** Re-measure all scenarios; update the targets table with real numbers; decide whether tier 3 is
reachable with the hardware/driver support (VP9/AV1 decode, deeper idle) or document the remaining gap.

Exit criteria per phase: before/after medians in `RESULTS.md`, an uninstall path, `OS9-HANDOFF.md` and this file updated.

## 5. Decisions needed from the owner

1. 60 Hz on battery now, a dynamic-refresh investigation, or neither?
2. May I schedule one overnight/lid-closed sleep-drain test (F1)?
3. May I close the ChatGPT/Codex app once for a 2-minute paired A/B (A2)? (Declined on 2026-10-16: do not close it.)
4. OK to apt-install `perf` for the Gala profile (A5)?
5. Which background apps may be paused on battery (A6)? Container CPU limits (A7)?
6. Audio idle experiment (C1), with the pop risk, in a spare session?

## 6. Risks

- Noise: baselines swing 14 to 24 W with the owner's activity; only paired runs count.
- Apps that render continuously can hide any system win; fix the app mix first.
- Wayland mode may break an Electron app; the env var file is removable (`install-electron-wayland.sh --uninstall`).
- Parity may not be reachable on Linux today (video decode codecs, deep sleep); the plan makes the gap measurable instead of assumed.

## Observation log — 2026-10-18 (kernel `7.1.12-2-20261017.20-sep-ARCH`, Aurora `.20`) — NOT an A/B result

SMC `Total System Power` (`hwmon2/power1_input`), 1 s samples, on battery, built-in panel
at 120 Hz, backlight 307/500:

| Conditions | n | median | p10-p90 | min-max |
|---|---|---|---|---|
| Built-in display only, ~5 min after boot, desktop idle-ish, Claude Code session running | 45 | 16.08 W | 14.38-18.45 W | 12.93-21.51 W |
| Dock monitor lit (1080p60, Insignia 65" TV), `claude-desktop` ~55% of a core, ChatGPT app and a 1 Hz logging script running | 60 | 21.12 W | 20.35-22.11 W | 20.06-26.20 W |

The owner's panel watt meter showed ~16 W for the first condition, matching the sample.
**No improvement is claimed.** 16 W sits inside the earlier "light use 14 to 17.6 W" range, and
the second row (20-22 W) is within the earlier 17.6-20.5 W "agent apps open" readings, i.e.
the reading follows what is running and whether an external display is lit, not the kernel.
The conditions differ between rows and between days, so these two rows cannot be compared as
a before/after. A real comparison needs: same workload script, same brightness and refresh,
no external display, >=3 alternating runs per kernel (stock `7.1.13-3-2-ARCH` vs Aurora `.20`),
medians with p10/p90, as the honesty rules above require.

## Upstream power review: omacom/linux-aurora `aurora-wip`, published `.19`/`.20`, open issues — 2026-10-18

`aurora-wip` (tip 2026-09-05) is fully contained in `.20` (0 commits ahead), so the published
release is the thing to look at. Findings, with live checks on this Mac (read-only):

1. **The PMP is running now.** `apple-pmgr-misc: PMP manages fabric and DCS p-states` and
   `apple_pmp 28e700000.pmp: PMP firmware and endpoint ready` appear in this boot's log.
   Upstream `.19` (PR #123, carrying @maralcbr's #91) describes the J314s PMP in its device
   tree and fixes s2idle resume with it; "the PMP runs only when the boot loader switches it
   on, otherwise the J314s keeps the previous power path". Our previous `boot.bin` did not run
   it; the upstream-matched `m1n1-aurora` payload deployed today does. `pmp_report` also reports
   AVD, ISP and the three DCP power states to the PMP. This is the most plausible source of any
   idle-power change seen today, **but no before/after was measured**.
2. **Idle fabric governor** (`apple_pmgr_misc.idle_fabric_pstate`, currently `0`, root-writable
   at runtime): lowers the fabric p-state at idle; external CRTCs hold it up while scanning out.
   Release notes: *not used while a PMP runs*, so with the PMP active toggling it is expected to
   do nothing; not tested here.
3. **CPU idle residency (cpu0, since boot, ~14 min):** WFI 394 s, deep `CPU PD` 154 s, i.e.
   ~28% of idle time in the deep state. The earlier record in this file (2026-10-16, other kernel
   and boot payload, different window) was WFI 19.8 s vs `CPU PD` 1.4 s (~7%). Direction is
   encouraging; the windows and workloads differ, so this is an observation, not a result.
4. **Thunderbolt/s2idle options, all off by default** (PR #124 carrying #92): `s2idle_teardown`
   powers off connected ports with no PCIe tunnel during s2idle (drops USB/display/network behind
   a dock until resume; run on one M1 Pro only), plus `resume_recovery` and `router_sleep`.
   Candidate for sleep-drain work *without* a dock only; untested here.
5. **`vrr` / `tb` branches:** ProMotion variable refresh (`drm: apple: support ProMotion variable
   refresh rate`, 2026-09-12). Not confirmed to be in `.20`; our staged out-of-tree VRR module
   (DeepSeek) is the other route. Variable refresh is the main display-power lever.
6. **Open upstream issues that touch power:** #24 (M1 Max GPU firmware crash after loaded
   s2idle resume), #59 (J516S s2idle keyboard wake / dark panel), #121 (external-display sleep
   veto), #130 (J316S direct USB-C display: DCP crash after idle lock / s2idle). **None is about
   idle watts or battery life** — an open niche where measured data from this Mac would be useful.

Next, without rebooting: record `/sys/devices/system/cpu/cpu*/cpuidle/state*/{usage,time}`
deltas over fixed 5-minute windows while idle and under the standard workload, plus the SMC power
reading, so the same script can later be run on stock `7.1.13-3-2-ARCH` for an honest A/B. With a
reboot: stock vs Aurora `.20`, >=3 alternations (see the honesty rules above).

### Display audio on the dock monitor (owner report 2026-10-18)
The monitor's speakers show as selectable but nothing plays. Live state: `appledrm.hdmi_audio=N`
(the parameter is described as "Enable unstable HDMI audio support" and the `.20` notes say the audio
changes take effect only with `appledrm.hdmi_audio=1`, off by default on M1-M3); only the
internal ALSA card (`AppleJ314`) exists, and PipeWire's sink list shows the internal headphones
plus network (AirPlay/RAOP) outputs, one of them named like a TV (`zTV-Living Room`), which is
likely what appears. Upstream issue #48 ("qualify HDMI/DP audio before changing its default")
is open. Needs a reboot with `appledrm.hdmi_audio=1` on the cmdline to test.
