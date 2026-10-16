# Power and battery-life roadmap

Owner request 2026-10-16: investigate every opportunity to lower light-load power and extend battery runs; document goals
and a comprehensive plan. This is the single plan; evidence is in `POWER-OPPORTUNITIES-2026-10-16.md` and the optimization
repo (`techmore/ElementaryOS_MSeries_Optimization`, `docs/RESULTS.md`). `EFFICIENCY-GOALS.md` keeps the original targets.

Honesty rules (from earlier incidents): report medians and p10/p90, alternate A/B at least three times, never claim a win
from one run, label every number *measured* or *estimate*, never change brightness, refresh rate or display power without
the owner's explicit yes, and leave the kernel to DeepSeek and the audio stack and `speakersafetyd` to the owner.

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
