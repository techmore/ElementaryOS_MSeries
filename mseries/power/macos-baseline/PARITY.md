# Power parity: macOS baseline vs elementary OS on the M1 Pro

Updated 2026-10-17. macOS run: `not yet`.

Pass = Linux within 10% of macOS (lower-is-better: linux <= mac x 1.10; higher-is-better: linux >= mac / 1.10). Close = Within 1.5x of macOS (tier 2 in EFFICIENCY-GOALS.md). Same machine, on battery, same brightness and app state, medians with p10/p90, paired runs (POWER-ROADMAP.md honesty rules).

Scoreboard: ⏳ mac 41, ℹ️ 11

## Whole machine (0/10 passed)

What the battery sees in each fixed scenario. These are the headline numbers; every other category explains them.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | W1 | Idle floor, screen on, nothing open | – | 9.50 W (estimate) ~9 to 10 W best realistic, 60 Hz, 20% brightness | ⏳ mac |
| [ ] | W2 | Idle, display asleep | – | (unmeasured) not measured | ⏳ mac |
| [ ] | W3 | Idle with usual apps open | – | 17.60 W (measured) 17.6 W (single reading; 14 to 20.5 W range) | ⏳ mac |
| [ ] | W4 | Scripted web browsing | – | (unmeasured) no scripted loop yet; light use 14 to 17.6 W | ⏳ mac |
| [ ] | W5 | Local 1080p H.264 file | – | 13.20 W (measured) 13.2 W with hardware decode (mpv/VA-API) | ⏳ mac |
| [ ] | W6 | YouTube 1080p in the browser | – | 18.50 W (measured) 17.7 to 19.3 W in Brave | ⏳ mac |
| [ ] | W7 | Local 1440p (2K) H.264 file | – | (estimate) not measured | ⏳ mac |
| [ ] | W8 | Local 2160p (4K) H.264 file | – | (estimate) not measured | ⏳ mac |
| [ ] | W9 | YouTube 1440p (2K) in the browser | – | (estimate) not measured; VP9/AV1 at this size is software decode (M3) | ⏳ mac |
| [ ] | W10 | YouTube 2160p (4K) in the browser | – | (estimate) not measured; VP9/AV1 at 4K in software is the worst case (M3) | ⏳ mac |

## CPU and scheduling (0/7 passed)

How deeply and how often the cores sleep, and how fast they wake for work.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | C1 | CPU rail power at idle | – | (unmeasured) rail split not read on Linux yet (SMC keys) | ⏳ mac |
| [ ] | C2 | E-cluster idle time spent power-gated | – | 7 % (measured) CPU0: CPU PD 1.4 s vs WFI 19.8 s (~7%) | ⏳ mac |
| [ ] | C3 | P-cluster idle time spent power-gated | – | (unmeasured) not split by cluster yet | ⏳ mac |
| [ ] | C4 | Wakeups per second, whole system | – | 3900 /s (measured) arch_timer ~3.9k/s across cores (HZ=1000) | ⏳ mac |
| [ ] | C5 | Burst: time to 90% of peak CPU power | – | 78 ms (measured) P cluster at 90% clock in 76 to 79 ms | ⏳ mac |
| [ ] | C6 | Burst: back to idle after load ends | – | (unmeasured) goal <= 30 s | ⏳ mac |
| [ ] | C7 | Burst: peak P-core clock on battery | – | 2208 MHz (measured) power-saver cap 2064/2208 MHz on battery | ⏳ mac |

## Graphics and compositor (0/4 passed)

WindowServer on macOS, Gala/Mutter on Linux, and the apps that keep them busy.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | G1 | GPU rail power at idle | – | (unmeasured) rail not read yet | ⏳ mac |
| [ ] | G2 | GPU busy at idle | – | (unmeasured) only job counts so far (gala 840/s) | ⏳ mac |
| [ ] | G3 | Compositor CPU, nothing open | – | 127 ms/s (measured) Gala 12.7% of a core average | ⏳ mac |
| [ ] | G4 | Compositor CPU, usual apps open | – | (unmeasured) bursts 9 to 60% of a core | ⏳ mac |
| [ ] | G5 | ChatGPT app background cost | – | (measured) 4,000 to 5,000 GPU jobs/s under Xwayland (different unit) | ℹ️ |

## Display (0/2 passed)

Panel and backlight cost, refresh behaviour, and the display coprocessor.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | D1 | Display cost (screen on minus screen off) | – | (unmeasured) 500 to 105 brightness saved ~4 W | ⏳ mac |
| [ ] | D2 | Brightness during the macOS run | – | (measured) 105/500 typical; match this before comparing | ℹ️ |
| [ ] | D3 | Refresh at idle (ProMotion vs fixed) | – | (measured) fixed 120 Hz; 60 Hz saves 1.7 to 2.0 W (B1, owner decides) | ℹ️ |
| [ ] | D4 | Display coprocessor mailbox traffic | – | 480 /s (measured) ~480 interrupts/s at idle | ⏳ mac |

## Video and media (0/9 passed)

Cost of playback above the idle floor at 1080p, 1440p and 4K, whether 4K stays in hardware, dropped frames, and which codecs run in hardware.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | M1 | Local 1080p: extra over idle | – | 3.70 W (estimate) 13.2 W minus ~9.5 W idle | ⏳ mac |
| [ ] | M2 | YouTube 1080p: extra over idle | – | 9.00 W (estimate) ~18.5 W minus ~9.5 W idle | ⏳ mac |
| [ ] | M3 | VP9/AV1 web video decoded in hardware | – | (measured) H.264 only in the AVD driver; VP9/AV1 is kernel work (D3) | ℹ️ |
| [ ] | M4 | Local 1440p: extra over idle | – | (estimate) not measured | ⏳ mac |
| [ ] | M5 | Local 4K: extra over idle | – | (estimate) not measured | ⏳ mac |
| [ ] | M6 | YouTube 1440p: extra over idle | – | (estimate) not measured | ⏳ mac |
| [ ] | M7 | YouTube 4K: extra over idle | – | (estimate) not measured | ⏳ mac |
| [ ] | M8 | Local 4K decoded in hardware (1 = yes) | – | (estimate) not checked; AVD H.264 at 4K untested | ⏳ mac |
| [ ] | M9 | Local 1440p: frames dropped in 150 s | – | (estimate) not measured | ⏳ mac |
| [ ] | M10 | Local 4K: frames dropped in 150 s | – | (estimate) not measured | ⏳ mac |

## Audio (0/1 passed)

Whether the speaker path sleeps when nothing plays.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | A1 | Audio daemon CPU at idle | – | (unmeasured) pipewire + filter chain + speakersafetyd | ⏳ mac |
| [ ] | A2 | Speaker PCM stops when silent | – | (measured) FAIL: speaker and sense PCMs RUNNING since boot (~1.2 W, low confidence) | ℹ️ |

## Wireless and I/O (0/1 passed)

Wi-Fi, Bluetooth, USB, and background traffic.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | N1 | Network traffic at idle | – | (unmeasured) | ⏳ mac |
| [ ] | N2 | Bluetooth state during the run | – | 0.20 (measured) ~0.2 W saved when off | ℹ️ |
| [ ] | N3 | Wi-Fi power save / PCIe ASPM / USB autosuspend | – | (measured) power save on; powersupersave -0.3 W; USB autosuspend 0 W | ℹ️ |

## Storage and memory (0/2 passed)

Background disk writes and memory rails.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | S1 | Disk writes at idle | – | (unmeasured) btrfs commits, journald, swap (1.1 GB swapped) | ⏳ mac |
| [ ] | S2 | DRAM rail at idle | – | (unmeasured) | ⏳ mac |

## Background activity (0/2 passed)

What the OS keeps running when you are not doing anything.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | B1 | Processes running | – | (unmeasured) | ⏳ mac |
| [ ] | B2 | Service jobs (launchd vs systemd) | – | (unmeasured) rpcbind, cups, avahi etc. each < 0.1 W | ℹ️ |
| [ ] | B3 | CPU used by everything at idle | – | 1700 ms/s (measured) CPU 83% idle across 10 cores (~1.7 cores busy, apps open) | ⏳ mac |

## Sleep and standby (0/2 passed)

Lid-closed drain and how often the machine wakes itself.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | Z1 | Lid-closed drain on battery | – | (unmeasured) s2idle only; F1 test not run | ⏳ mac |
| [ ] | Z2 | Self-wakes per hour asleep | – | (unmeasured) | ⏳ mac |
| [ ] | Z3 | Standby/hibernate after hours asleep | – | (measured) none: suspend stays s2idle indefinitely | ℹ️ |

## Battery and thermals (0/1 passed)

Cross-checks that both OSes read the same pack the same way.

| | ID | Item | macOS | Linux now | Status |
|---|---|---|---|---|---|
| [ ] | T1 | Battery health | – | 92 % (measured) 92%, 93 cycles | ℹ️ |
| [ ] | T2 | Battery temperature at idle | – | 32.10 °C (measured) 32.1 °C at rest | ⏳ mac |
| [ ] | T3 | Charge limit | – | (measured) 80% cap active on Linux | ℹ️ |
