# Roadmap, features and follow-ups (MacBook Pro 14" M1 Pro, elementary OS 9 on Asahi)

Last updated 2026-10-13. Day-to-day pending checks live in the robot: `mseries-verify status`
(seed: `mseries/local-ai/verify-checks.json`). This file is the human-readable plan.
The specific regression reports and reproduction steps are tracked in
[`BUG-FIX-ROADMAP.md`](BUG-FIX-ROADMAP.md).
OS 9 implementation progress and Claude Code takeover tasks are in
[`OS9-HANDOFF.md`](OS9-HANDOFF.md).
The first factory arm64 ISO build succeeded on October 13; artifact details
and remaining verification are in [`FIRST-ISO-BUILD.md`](FIRST-ISO-BUILD.md).
Hardware boot remains unverified.
The earlier local ISO reached the graphical installer in an isolated ARM64
KVM VM; see [`VM-SMOKE-TEST.md`](VM-SMOKE-TEST.md). Repeat this on the image
with the corrected live-session hardware overlay before progressing.

## Done and verified

| Feature | How | Evidence |
|---|---|---|
| CodexBar quota ETA | Visible per-limit forecasts and the earliest available limit in the bar; exhausted quotas show reset time | 11 ETA tests, 5 refresh tests, GTK render probe, and installed-module/live-snapshot checks passed |
| CodexBar usage freshness | One-minute backend polling; asynchronous five-second panel reads; throttled refresh on open | Meson policy tests and delayed-IPC GTK probe passed; installed on the working desktop |
| Login-screen stall fixed | `lightdm` drop-in waits for the eDP connector; display crossbar in the fairydust initramfs (`install-initramfs-crossbar.sh`) | greeter 119.7 s -> 0.82 s; dp-xbar deferrals 14 -> 0; first-dcp -> DRM 2.57 s -> 0.01 s |
| USB4 dock data (hub, mouse, headset, 1 Gb/s Ethernet) | Custom kernel `fairydust-usb4`, m1n1 + DTBs, thunderbolt quirks (`mseries/fairydust/usb4/`) | checks `dock-usb4-ethernet`, `dock-dp-retry-silent` passed |
| Boots Linux by default | GRUB default + `asahi-bless` | check `boot-default-usb4` |
| Network speed in dropdown and (toggle) in menu bar | `install-network-throughput.sh` + 3 patches | check `network-row-look` |
| Rounded screen corners | patched Gala, radius 14 (`install-gala-screen-corners.sh`) | **needs your look**: `gala-corners-look` |
| Pastel blue/rose theme | `install-theme-tweaks.sh` | **needs your look**: `colors-look` |
| Memory/swap/service tuning | `install-system-tuning.sh` (zram, no ModemManager/AppCenter daemon) | `zram-swap`, `services-trimmed` |
| Speaker tuning | `install-pipewire-lv2.sh` + `install-audio-stack.sh --with-dsp` | `audio-output-ok` passed |
| Battery charge limit 80% + on-battery CPU cap | `install-power.sh` (`mseries-power`) | limit verified; on-battery path simulated, real unplug pending (`power-battery-policy`) |
| Native Firefox (no snap) | `install-native-firefox.sh` | runs |
| Wi-Fi resume fix | `mseries-wifi-resume-fix` | CI test |
| Tracks upstream | merged `elementary/os` main @ 7024fd0 | `UPSTREAM-PINS.md` |
| Benchmarks | `mseries/benchmarks/` | see `benchmarks/README.md` |

## Implemented; runtime validation pending

| Feature | Change | Next check |
|---|---|---|
| OpenCode Go in M-series CodexBar | The CodexBar installer adds `opencodego` to fresh/default and custom provider selections; Wingpanel labels it OpenCode Go. | Install on the working desktop, add an API key in CodexBar Settings, and confirm the quota row. |

## Open problems

| Problem | Why | Next step |
|---|---|---|
| **Monitor through the dock** (2 DP + HDMI on a WD22TB4) | Needs DisplayPort tunnelling inside USB4 (unimplemented upstream; Sven Peter: "requires reverse engineering that is not done yet"). The CD321x firmware picks USB4 and Linux has no mode control, so a fall-back to plain DP Alt Mode can't be forced. | Watch upstream (`upstream-dp-watch` check). To push it ourselves: m1n1-hypervisor trace of macOS driving the dock, from a second computer (see below). |
| Suspend with a USB4 dock attached | `thunderbolt-apple-acio` vetoes suspend by design; the Mac stays awake with the display off | Needs the ACIO sleep/wake handshake (large). Cheap option: a clean "docked lid" mode that locks and stops the 30 s retries. |
| USB-C (non-USB4) devices lost across suspend | `phy-apple-atc` / `dwc3-apple` have no system-sleep PM; tipd resume only re-enables the IRQ | Kernel fix, tested with the user present. |
| Wingpanel crash `PanelWindow.on_realize` | Upstream bug; Gala respawns the panel | Report upstream (not done). |
| Hardware video decode | Not available for M1 on Linux | None, upstream. |

## Stretch goals (rough order of value)

1. **Dock video via m1n1 hypervisor trace.** Needs a second computer (below). Result would also help every Asahi user.
2. **Panel toggle for the battery charge limit** (today it is `sudo mseries-power limit 80|100`).
3. **Docked lid mode**: lock + display off without the endless suspend retries.
4. ~~**Linux VMs with KVM**~~ Guide written 2026-10-13: [`KVM-VMS.md`](KVM-VMS.md) (boot verified headless; graphics, networking address and benchmark overhead not yet measured).
5. **Publish benchmark history** for every kernel/Mesa update, plot trends.
6. **Install media / transform script** for other M1/M2 Macs (see `TRANSFORM-DESIGN.md`).
7. **Tether continuity add-on**: pinned, removable ARM64 package installer and optional Brave integration are implemented on `mseries-tether-continuity`; iPhone/Brave qualification remains. Current BlueZ 5.85 is below Tether's 5.86 minimum for Messages. See [`TETHER-CONTINUITY.md`](TETHER-CONTINUITY.md).
8. **Report upstream bugs** (Wingpanel crash; PipeWire missing LV2 plugin in Ubuntu).

Not realistic here: macOS 27 guests (`MACOS-VM.md`), Mac mini M4 (Asahi has no M4 support: no installer, no GPU
driver, M3 only now nearing a first release).

## Second computers available for the m1n1 hypervisor trace

The tracer (m1n1 `proxyclient`) is plain Python over USB serial, so the other machine does not need Asahi Linux, only
Python, a USB-C cable and permission to attach a USB serial device.

| Machine | Verdict |
|---|---|
| Chromebook | Possible via the Linux (Crostini) container with USB passthrough; flaky for raw serial. Second choice. |
| Work Mac (MDM, user is admin) | Best candidate if MDM allows USB serial devices. Everything lives in a user-space Python venv (`pip install pyserial construct`); no system changes. Check policy first, keep it light. |
| Windows PC (password protected) | Skip. |

## How to follow up

- `mseries-verify status` shows what is waiting; `mseries-verify run --notify` re-checks now.
- `python3 mseries/benchmarks/run.py` reruns the benchmarks (plug in the charger).
- Recovery for boot problems: `mseries/fairydust/usb4/RECOVERY.md`.

## Factory image checkpoint — 2026-10-13

Corrected CI image run 38410538372 succeeded at source 32877a7; actual
liveiso hardware helper payload verification passed. See FIRST-ISO-BUILD.md
for provenance and checksum. Next verify the downloaded corrected ISO and
repeat the VM smoke boot, then resolve the Asahi kernel/firmware packaging
gaps. Apple hardware boot remains pending.


Enhanced-kernel test path: pinned Fairydust + USB4 Debian packaging is now
implemented and compiling locally; see fairydust/debian/README.md and the
local kernel monitor. After package inspection, integrate it as an opt-in
experimental image alongside the required pinned m1n1/DTB path. Host boot
remains unchanged. Generic Ubuntu Asahi candidate is a packaging reference,
not a replacement for the enhanced test kernel.
