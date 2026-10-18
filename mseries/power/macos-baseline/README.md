# macOS power baseline and the parity checklist

Owner request 2026-10-17: profile everything macOS does on this M1 Pro, set a minimal baseline per category, and check
categories off as elementary OS matches them. This replaces Apple's marketing figures (EFFICIENCY-GOALS.md) with numbers
measured on **this** machine, same battery, same panel.

[Power documentation map](../README.md) · [Retained runs and limitations](results/README.md).
The committed macOS capture is inventory-only; active-use parity still needs matching runs.

## 1. Record the macOS baseline (on the Mac, booted into macOS)

```bash
git clone -b power-usage https://github.com/techmore/ElementaryOS_MSeries && cd ElementaryOS_MSeries
bash mseries/power/macos-baseline/make_test_videos.sh      # 1080p, 1440p and 4K clips into ~/Movies (needs ffmpeg)
# unplug the charger; set brightness to what you use on Linux and note it
sudo python3 mseries/power/macos-baseline/macos_profile.py
```

About 40 minutes, guided: it tells you what to open or quit before each scenario and waits for Enter.
Quick dry run: `--scale 0.2 --only idle_minimal`. Inventory only (what macOS is running, settings, sleep history):
`python3 mseries/power/macos-baseline/macos_profile.py --inventory-only` (no sudo needed). `python3` comes with the Xcode command-line tools.

| Scenario | What happens | Linux counterpart |
| --- | --- | --- |
| `idle_minimal` | nothing open, screen on, 180 s | the floor (W1) |
| `idle_screen_off` | display put to sleep, woken after | W2, and display cost D1 |
| `idle_as_used` | your usual apps open | W3 |
| `web_loop` | Safari opens 6 fixed pages, one per 15 s | W4 |
| `video_local` | QuickTime plays `test-1080p-h264.mp4` | W5, M1 (same file in mpv) |
| `video_local_1440p` | QuickTime plays `test-1440p-h264.mp4` (2K) | W7, M4, M9 (dropped frames) |
| `video_local_2160p` | QuickTime plays `test-2160p-h264.mp4` (4K) | W8, M5, M8 (hardware decode), M10 |
| `video_web` | you start YouTube 1080p | W6, M2 |
| `video_web_1440p` | same video switched to 1440p | W9, M6 |
| `video_web_2160p` | same video switched to 2160p | W10, M7 |
| `cpu_burst` | all cores for 20 s at 100 ms sampling | C5 to C7 |

It does not change brightness, refresh rate, Wi-Fi or Bluetooth; it records them. Output goes to
`results/macos-<stamp>/`: `summary.json` (medians, p10/p90), `raw/` (powermetrics plists, battery samples) and
`inventory/` (processes, launchd jobs, pmset settings and log, assertions, displays, Wi-Fi, Bluetooth).

Whole-machine power is `PowerTelemetryData.SystemLoad` from `AppleSmartBattery`, the macOS equivalent of the SMC
`Total System Power` used on Linux. CPU/GPU/ANE are powermetrics rails; `rest_of_machine_w` is the difference
(panel, backlight, Wi-Fi, SSD, amps, regulator losses). Sleep drain comes from battery-only sleep periods already in
`pmset -g log`, so there is a lid-closed baseline without running a new overnight test.

## 2. Record the Linux side (on the same Mac, booted into elementary OS)

```bash
bash mseries/power/macos-baseline/make_test_videos.sh      # same clips into ~/Videos
python3 mseries/power/macos-baseline/linux_profile.py
```

Same scenarios and output shape, no root. Match display luminance where possible and record both OS brightness settings; equal percentages do not establish equal luminance. Whole-machine
power comes from the SMC `Total System Power` hwmon sensor (falls back to battery `power_now`); CPU numbers come from
cpuidle residency per cluster, `/proc/stat` and `/proc/interrupts` (arch_timer stands in for macOS idle wakeups);
per-process CPU replaces Energy Impact, with `gala` in place of `WindowServer`. For local video it asks mpv over IPC
whether a hardware decoder is really in use and how many frames it dropped (M8 to M10); the target is what QuickTime
does: hardware decode, no drops. It does not read the CPU/GPU rails yet
(C1, G1), and `idle_screen_off` only blanks the panel with `--allow-blank`, because display power is owner-gated.

## 3. Score it

```bash
python3 mseries/power/macos-baseline/parity.py --mac mseries/power/macos-baseline/results/macos-<stamp>/summary.json
python3 mseries/power/macos-baseline/parity.py --linux-run mseries/power/macos-baseline/results/linux-<stamp>/summary.json
python3 mseries/power/macos-baseline/parity.py --linux W1=8.9 --source W1="powerlab ab.py 2026-10-18"
python3 mseries/power/macos-baseline/parity.py --check A2 --note A2="speaker PCM suspends after 30 s"
```

`parity.json` holds 11 super-categories and 52 items, each with the macOS source, the current Linux number (labelled
measured or estimate, with its source doc) and how to measure it on Linux. `PARITY.md` is regenerated with a checkbox
per item: **pass** within 10% of macOS, **close** within 1.5x (tier 2), otherwise **gap**. Yes/no items (speaker PCM
idle, codecs, refresh mode) are passed by hand with `--check`.

Linux numbers carried in today are from `POWER-ROADMAP.md` and `POWER-OPPORTUNITIES-2026-10-16.md`; several are single
readings or estimates and must be re-measured with paired runs before an item is checked off.

## Validation and collection limits

Run the offline regressions before changing the collectors or scoring:

```bash
python3 mseries/test-power-cap.py
python3 mseries/test-power-install.py
python3 -m unittest discover -s mseries/power/macos-baseline -p 'test_*.py'
```

Quick CPU runs retain a minimum 30 seconds (lead-in, full 20-second load, recovery).
Collectors clean up owned workers and restore a blanked display on interruption. Run directories
include seconds and microseconds so repeated collections cannot overwrite an earlier run in the same minute.
Interrupted macOS raw plists without completion metadata are excluded from resummarization.
QuickTime loops and closes only the requested clip; mpv early exits invalidate a local video collection.

Linux clock ramp and activity recovery are diagnostic fields, not CPU-rail power ramp/recovery equivalents;
C5/C6 remain unmeasured until comparable rail data is available. A partial Linux import clears missing
mapped values instead of retaining measurements from an older run. Omission from a top-process list means
unknown, not zero. Unknown decoder properties also remain unmeasured. Numeric/informational items cannot
be manually checked off; `--check` is reserved for qualitative items.

These checks validate software behavior with fixtures; actual battery unplug/replug, suspend, display
restore, media automation and rail readings still need validation on the target OS and hardware.
