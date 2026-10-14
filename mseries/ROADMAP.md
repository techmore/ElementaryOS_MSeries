# Roadmap, features and follow-ups (MacBook Pro 14" M1 Pro, elementary OS 9 on Asahi)

Last updated 2026-10-14. Day-to-day pending checks live in the robot: `mseries-verify status`
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
| Network indicator speed, connected-only Wi-Fi list, and usage views | Installed on the M1 Pro; user `netusage` service is active and its SQLite database contains app/host and DNS records. Existing panel-speed toggle remains. | Visual check of joined-network-only collapse, chevron expansion, and menu rendering | The pinned build also ships through the Apple Silicon image overlay.
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
| OpenCode Go in M-series CodexBar | The installer enables the provider and passes the existing OpenCode Go CLI credential to CodexBar at runtime. | Install on the working desktop, sign in through OpenCode, and confirm the quota row. |

## Open problems

| Problem | Why | Next step |
|---|---|---|
| **Expand elementary root using the 112 GiB gap** | Gap is before the Asahi stub/EFI/root unit; the added Btrfs member would require early LUKS unlock and initramfs discovery | Verify gap was prepared by Asahi Installer, review read-only preflight and verified backups; see [`procedures/ROOT-EXPANSION.md`](procedures/ROOT-EXPANSION.md) |
| **Monitor through the dock** (2 DP + HDMI on a WD22TB4) | Needs DisplayPort tunnelling inside USB4 (unimplemented upstream; Sven Peter: "requires reverse engineering that is not done yet"). The CD321x firmware picks USB4 and Linux has no mode control, so a fall-back to plain DP Alt Mode can't be forced. | Watch upstream (`upstream-dp-watch` check). To push it ourselves: m1n1-hypervisor trace of macOS driving the dock, from a second computer (see below). |
| Suspend with a USB4 dock attached | `thunderbolt-apple-acio` vetoes suspend by design; the Mac stays awake with the display off | Needs the ACIO sleep/wake handshake (large). Cheap option: a clean "docked lid" mode that locks and stops the 30 s retries. |
| USB-C (non-USB4) devices lost across suspend | `phy-apple-atc` / `dwc3-apple` have no system-sleep PM; tipd resume only re-enables the IRQ | Kernel fix, tested with the user present. |
| Lid-open login needs a power-button press | Resume and greeter start correctly in the log; the panel or input does not respond until the power key | Trace one resume (see BUG-FIX-ROADMAP.md). |
| Dock Ethernet icon dies and is recreated | RTL8153B renamed eth0 to enx...; fresh NetworkManager profile each time; `rtl8153b-2.fw` missing | Add firmware, pin one profile, retest. |
| Wingpanel crash `PanelWindow.on_realize` | Upstream bug; Gala respawns the panel | Report upstream (not done). |
| **One-command installer untested on hardware** | `bin/elementary-mac-setup` + `mseries/install-unlock-screen.sh` (elementary-branded LUKS unlock screen) were written without a spare Mac; only the state machine/config logic is unit-tested | Run on a backed-up Asahi Alarm BTRFS install; confirm plymouth/keymap hook order, passphrase entry, LightDM autologin, then drop this row |
| Hardware video decode | Not available for M1 on Linux | None, upstream. |

## M1 Pro parity with Omarchy M (audited 2026-10-14 against omarchy-mac-pkgs 222f7a8)

Done on the running system: Wi-Fi resume fix, speaker safety and DSP, ambient keyboard light, battery charge limit, dock hub/mouse/Ethernet, docked lid mode, zram and service trimming. Remaining, in order:

1. ~~Port `omarchy-audio-watchdog` (audio-stack self-repair) to Pantheon.~~ Installed on the M1 Pro 2026-10-14 with `sudo bash mseries/enhance.sh --only audio`, together with the no-suspend and headset-mic WirePlumber rules (rules apply at the next login).
2. Decide the Apple function-key default (`fnmode`), then make it explicit.
3. Mic mapping (`omarchy-audio-asahi-mic-map`) re-homed to the elementary audio session.
4. Lid-open login and Touch ID research (see Stretch goal 0).
5. Hardware video decode (AVD firmware plus VA-API bridge) once a kernel supports it.
6. Put the tested audio chain into the factory image.

Performance work stays measured: use `mseries/benchmarks/` before and after each change and keep the medians.

## Stretch goals (rough order of value)

0. **Apple ecosystem gaps: iCloud password sync and iMessage** (reported 2026-10-14; see `BUG-FIX-ROADMAP.md`). OpenBubbles is the first candidate for iMessage.
0. **ArtCraft apps as native Adobe and Office replacements** (evaluation requested 2026-10-14; see `BUG-FIX-ROADMAP.md`). Build, license-check and benchmark each Rust app on aarch64 before packaging.
0. **Lid open shows the login screen, with Touch ID.** Today the login needs a power-button press after resume (bug tracked in `BUG-FIX-ROADMAP.md`). First fix the wake path; then investigate fingerprint login. No Linux driver for the Mac Touch ID sensor (Secure Enclave) is known to this project, so treat Touch ID as research, not a plan.

1. **Dock video via m1n1 hypervisor trace.** Needs a second computer (below). Result would also help every Asahi user.
2. ~~**Panel toggle for the battery charge limit**~~ Done 2026-10-13: a switch in the gear menu (`quick-settings/ChargeLimit.vala`, polkit action in `power/`). Pending your click-through: check `charge-limit-toggle`.
3. ~~**Docked lid mode**~~ Done 2026-10-13: `install-docked-lid.sh` (user service). Real lid close pending: check `docked-lid-works`.
4. ~~**Linux VMs with KVM**~~ Guide written 2026-10-13: [`KVM-VMS.md`](KVM-VMS.md) (boot verified headless; graphics, networking address and benchmark overhead not yet measured).
5. **Publish benchmark history** for every kernel/Mesa update, plot trends.
6. **Install media / transform script** for other M1/M2 Macs (see `TRANSFORM-DESIGN.md`).
7. **Tether continuity add-on**: pinned, removable ARM64 package installer and optional Brave integration are implemented on `mseries-tether-continuity`; iPhone/Brave qualification remains. Current BlueZ 5.85 is below Tether's 5.86 minimum for Messages. See [`TETHER-CONTINUITY.md`](TETHER-CONTINUITY.md).
8. **Native battery time-to-full:** implemented as an optional patch and installer for elementary's Power indicator; built and installed on the M1 desktop. See [`BATTERY-ETA.md`](BATTERY-ETA.md).
9. **Torrential ARM64 native app port and optimization.** Native GTK/Granite
    package installed on the desktop; official Ubuntu torrent data transfer
    and full-ISO SHA-256 verified; RPC pause/resume checks passed. UI interaction,
    close/reopen state restoration, and measured optimization remain. Upstream source and packages stay local pending a
    license grant. See [`TORRENTIAL-PORT.md`](TORRENTIAL-PORT.md).
10. **Report upstream bugs** (Wingpanel crash: draft in `upstream/`). ~~PipeWire missing LV2 plugin in Ubuntu~~: not a bug. Ubuntu ships `libspa-filter-graph-plugin-lv2.so` in `libspa-0.2-modules-extra` (checked 2026-10-13, 1.6.2-1ubuntu1.2, the same version as the installed PipeWire). The notes saying Ubuntu omits it missed that package. Next step: install it instead of building the plugin in `install-pipewire-lv2.sh`, and add it to the factory image. Not yet tested with the Asahi audio chain.

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


Native Fairydust kernel Debian image package builds, with required modules and
Mac DTB. Next adapt maintainer hooks/m1n1/DTBs for opt-in mkosi image testing;
no kernel package installation or kernel VM boot has happened yet.


The optional Fairydust mkosi profile is staged with its kernel and hashed
m1n1/U-Boot package pipeline. It remains QEMU-only until an image-specific
m1n1 boot.bin/ESP step is implemented; no Mac boot claim.


The Ubuntu Asahi m1n1 binary string check confirms its USB4 tunables; the
opt-in workflow pins those packages. This is only a static component check;
ESP/m1n1 boot packaging and a native Mac test are still open.

## Local general agent (October 13)

Crush + Qwen3.5-9B uses the private Honeykrisp GPU runtime, with an on-demand
user service and native robot-menu launcher. Full prompt prefill required
256-token chunks to fit GPU scratch; a short API response, synthetic tool call
and full Crush answer have completed. The final 32k context/one-cache profile
is memory-admitted; it is not a full-context capacity benchmark. NAS connection
awaits the owner's share path/address. ANE activation remains a separate boot
trial; existing staged artifacts do not prove execution.
