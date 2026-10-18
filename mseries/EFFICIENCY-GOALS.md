# Efficiency goal: run minimal, scale fast

> Current plan, workstreams and roadmap: [POWER-ROADMAP.md](POWER-ROADMAP.md) (2026-10-16). This file keeps the original targets.

Requested 2026-10-14/15. Goal: the M1 Pro should sip power when idle or lightly used and still reach full
CPU/GPU speed within seconds when work (local AI, builds) needs it. Status: **plan; no efficiency patch beyond
the audio sink timeout has been applied.**

## Where Apple is, and where we are

Apple's published battery figures for the 14-inch MacBook Pro (M1 Pro, 70 Wh battery): up to 17 h video
playback and up to 11 h wireless web. Divided out, that is roughly **4 W** average for video and **6 W** for web
browsing, with idle at the screen's lowest setting lower still. These are Apple's best-case claims, not
independent measurements, and are quoted from memory; check them before using them as a contract. Under load
the whole machine can draw tens of watts (the charger is rated well above 60 W).

Measured here (2026-10-14, kernel fairydust-usb4, Pantheon on Wayland, battery, screen 105/500, CPUs about
87% idle, Wi-Fi/USB tether, Electron apps open):

| State | Draw |
| --- | --- |
| Before the audio change | 12.9 W |
| After closing the idle speaker stream (30 s suspend) | 11.7 W |
| Noise between identical 30 s runs | up to 1.5 W, spikes above 20 W while commands ran |

So we are about **2x to 3x Apple's light-use figure**. At 11.7 W the 61 Wh battery lasts roughly 5 hours.

## Targets (proposal for the owner to adjust)

| Tier | Idle, screen at 20% | Web/office | 1080p video | Notes |
| --- | --- | --- | --- | --- |
| 1 (first month) | 7 W | 10 W | 9 W | Remove obvious waste |
| 2 | 5 W | 8 W | 7 W | Within about 1.5x of macOS |
| 3 | 4.5 W | 6.5 W | 5.5 W | Parity with Apple's claims |

Burst target: all cores and the GPU at full speed **within 5 s** of a heavy job starting, and back to low
power within 30 s of it ending, with no manual switching.

## Method (so numbers can be trusted)

1. One script that samples `power_now` once a second for 5 minutes and reports the **median and 10th/90th
   percentile**, not the mean. Run it from a text console or over SSH so measuring does not cause load.
2. Fixed scenarios: idle with the screen off; idle at 20% brightness; one Brave tab playing local 1080p
   video; a scripted browsing loop; a CPU burst; a local-AI prompt. Same Wi-Fi, same brightness, no charger.
3. Change **one thing at a time**, alternate on/off at least three times, keep the result table in this file.
4. Extend `mseries/benchmarks/run.py` rather than adding a second harness.

## Suspects, in the order to test

1. **Display coprocessor and compositor wakeups.** The display controller mailbox (`38bc08000.mbox`) fired
   about 480 times a second at idle and Gala used 10 to 18% CPU. Find what repaints (animations, the network
   graph, clock, an app's canvas), then fix it or let the compositor skip frames.
2. **Electron and Chromium apps** (Claude, ChatGPT, Brave) were the top CPU users. Test GPU compositing and
   background-throttling flags, and fewer always-open apps.
3. **Always-on processor and sensor traffic** (`406408000.mbox` about 385/s): audio and light-sensor polling by
   `mseries-keyboard-backlight` (every 5 s) and anything holding a capture stream open.
4. **CPU idle and frequency behaviour:** confirm deep idle states are entered, check the schedutil rate limit,
   and compare with the power-saver cap (2064/2208 MHz) that `mseries-power` applies on battery.
5. **Runtime power management:** USB autosuspend (phone tether), PCIe ASPM for Wi-Fi and NVMe, audio codec
   power-down, Bluetooth, SPI HID rate (about 1000 interrupts/s while touching).
6. **Display:** brightness floor and any waste from the always-on-top effects (rounded-corner mask, blur).

## Scaling fast without a manual switch

- Keep **power-saver on battery by default**, but let heavy tasks ask for speed: a `powerprofilesctl hold
  --profile performance` taken by the local-AI service (and long builds) for the duration of the job, released
  automatically when it exits. Verify the policy follows the hold within seconds.
- Make sure the cap in `mseries-power` is lifted by that hold instead of fighting it; today it sets a CPU
  ceiling directly, so test the interaction.
- GPU: the local-AI runtime already starts on demand; confirm the GPU returns to idle after it stops.
- The planned Rust port of `mseries-power` should keep the same behaviour; judge it by these measurements.

## Not allowed to change without the owner

Bootloader, kernel, initramfs and the speaker-safety daemon (`AGENTS.md`). Efficiency work that would touch
them is proposed, measured in a VM or edge lane first, and applied only on the owner's go-ahead.
