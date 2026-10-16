# Power and battery-life opportunities — survey of 2026-10-16

Read-only survey on the M1 Pro (kernel 7.1.13-fairydust-usb4-dptunnel, on battery, `power-saver`, 68% charge, brightness
untouched). Nothing was changed. Builds on `EFFICIENCY-GOALS.md` and the optimization repo results
(`techmore/ElementaryOS_MSeries_Optimization`, `docs/RESULTS.md`); the earlier A/B numbers below are cited from there, not re-measured.

Snapshot: SMC whole-machine power 17.6 W at the time of the survey with Claude Desktop, ChatGPT, Signal, Brave, Chromium and a
Terminal/OpenCode session open (single reading, not a median). CPU 83% idle. Governor schedutil, battery cap 2064/2208 MHz active.
Apple's implied figures: about 4.1 W video, 6.4 W web. Goal still **not met**.

## Ranked opportunities

| # | Opportunity | Evidence | Size | Gate |
| --- | --- | --- | --- | --- |
| 1 | **60 Hz on battery** (`tuning/refresh-rate`, opt-in) | Repeated alternating A/B: -2.0 W at 21% brightness, -1.7 W at full | -1.7 to -2 W | Display: owner decides |
| 2 | **Lean app mix** | Today: Gala 12.7% average (33% in `top`), ChatGPT 15%, Claude Desktop 4 processes, 3 Signal scopes, 2 Chromium apps; GPU job traffic earlier traced to Claude Desktop 55%, Terminal 27%, Gala 18% | Largest unmeasured lever; floor moves 14 to 24 W with the app mix | Needs A/B with `powerlab/ab.py` |
| 3 | **Gala CPU** | 72 CPU-minutes in 9.5 h uptime; about 340 voluntary context switches/s; no vblank flips at idle (earlier negative result), so it is not page-flip repaint | Unknown (up to ~0.5 to 1 W if halved) | Profile first; animations off is a visible change, ask |
| 4 | **Speaker amplifier never sleeps** | ALSA `pcm1p` (speaker/headphone) is `RUNNING` since boot (trigger_time ~33656 s, uptime ~34400 s) with owner `pipewire`, and `pcm2c` capture (speaker-safety sense) is `RUNNING`, owner `speakersafetyd`, even with the 30 s idle override installed. Likely the always-on DSP filter chain (`effect_output.j314-convolver`) keeps the sink busy | Earlier low-confidence estimate 1.2 W | Audio stack and `speakersafetyd` are owner-gated (AGENTS.md) |
| 5 | **Video: H.264 + VA-API** | mpv hardware decode saves 5.3 W vs software; Brave with the H.264-only extension plus VA-API flags -1.5 W vs stock | -1.5 W web video; -5 W local files | Extension exists in optimization repo; not shipped |
| 6 | **Kernel: HZ 1000 -> 250, DP-tunnel retry back-off, GPU scheduler job rate, deeper idle** | `arch_timer` about 3.9k/s across cores; 36% of idle work items are the DP retry loop, 45% GPU scheduling; cpuidle exposes only WFI and CPU PD | Unmeasured (kernel patches unbuilt) | **DeepSeek owns the kernel**; coordinate on the GitHub issue, no changes here |
| 7 | **Brightness** | 21% -> 5% saved about 0.7 W; 500 -> 105 about 4 W | Up to ~4 W vs full | Display: owner decides |
| 8 | Dynamic refresh (VRR) | Mutter experimental VRR, DCP support unverified | Possible, between 120 and 60 Hz | Investigate read-only, then ask |

## Follow-up measurement, same day: GPU job submission by process

`gpu_scheduler:drm_sched_job_queue` traced three times for 5 s each (read-only, tracing switched off and cleared afterwards), on battery:

| Process | Jobs per 5 s (runs 1 / 2 / 3) | About per second |
| --- | --- | --- |
| **ChatGPT desktop app** (`/usr/lib/chatgpt/ChatGPT`, profile `~/.config/Codex`) | 22,276 / 20,777 / 25,246 | 4,000 to 5,000 |
| gala | 4,199 / 4,200 / 4,200 | 840 |
| claude-desktop | 1,794 / 1,800 / 1,794 | 360 |
| Xwayland | 1,215 (once) | 240 |

The ChatGPT/Codex desktop app alone submits about 3x the GPU work of everything else combined, steadily, and earlier traces (about 665 jobs/s total, Claude Desktop 55%) were before it was running. Whole-machine power read 17.6 W before it and 20.5 W during the third run (single readings, not a controlled pair). So item 2 above has a prime suspect. Gala's CPU (bursts of 9 to 60% of a core) tracks client redraws, consistent with it compositing this app. Not yet measured: power with the app quit versus open. It was not closed because it may belong to a running agent session; a paired A/B needs the owner's okay, or the owner closing it.

## Checked and not worth doing (measured under noise, or worse)

- Background services and sensor pollers (avahi, cups, geoclue, zeitgeist, evolution, iio-sensor-proxy, keyboard backlight): each group under 0.1 W in paired runs. `rpcbind`/`rpc-statd`/`cups` are running with no use here, so disabling is hygiene and attack-surface, not battery.
- PCIe `powersupersave` -0.3 W, USB autosuspend 0, Bluetooth about -0.2 W (kept off when unused), `power-saver` vs balanced on AC no change, idle governor `teo` is +0.8 W worse than `menu`.
- CPU ramp: P cluster reaches 90% clock in under 80 ms, so the battery cap does not hurt responsiveness.
- `vm.swappiness=100` with 1.1 GB swapped is a latency matter, not a measurable power one.

## Battery lifespan (not runtime)

The 80% charge limit is already active (cell health 92% of design). Nothing further to add; do not raise the limit for runtime gains.

## Suggested next steps, in order

1. Owner chooses between 60 Hz on battery (item 1) and a dynamic-refresh investigation (item 8). Either takes one command via the existing tools, but both change the screen, so they wait for a yes.
2. A/B the app mix (item 2): quit one Electron app at a time in fast pairs with `powerlab/ab.py` and publish medians. Needs no display change.
3. Profile Gala (item 3) with `perf`/`sysprof` for a minute at idle to see whether the cost is our patches, blur/shadows, or client surfaces.
4. Ask the owner about the speaker-path idea (item 4); propose a config that lets the DSP chain suspend, test in a spare session, keep `speakersafetyd` untouched.
5. Post items in 6 as context on the kernel issue; do not patch.
