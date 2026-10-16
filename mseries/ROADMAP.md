# Roadmap, features and follow-ups (MacBook Pro 14" M1 Pro, elementary OS 9 on Asahi)

Last updated 2026-10-16. Day-to-day pending checks live in the robot: `mseries-verify status`
(seed: `mseries/local-ai/verify-checks.json`). This file is the human-readable plan.

Dock-video update 2026-10-16:
[REA / DeepSeek static-analysis handoff](fairydust/usb4/REA-DPIN-FINDINGS.md)
now records matching T6000/13.5 Apple binary analysis and exact shipped-board
DP-IN ranges. Separate DP-IN inactive/ack/HPD activation and per-tunnel PHY
PCLK/lifetime integration are concrete missing host-driver paths. Existing
USB4 common power/CIO PLL handling remains present. Next: finish T6000
dispatch/clock-plan and interrupt/endpoint mapping, then prepare a guarded
resource-based implementation for review. No live writes or kernel changes.
Latest target check: port2 host/USB4, Dell dock enumerated, bypass Y, external
DP/HDMI disconnected. Older no-device snapshots below are historical.

**Owner constraint: no M1 Pro reboot or power cycle.** Earlier macOS cutover
and guest-boot instructions are future reference only. Current next work is
read-only live enumeration/recovery diagnosis using the Neo where useful,
with hard timeouts in delegated workers and 30-second progress updates. The
Neo cannot install a boot-time hypervisor under the already-running target.

Owner's port2 role attempt returned EIO without a role change. A fixed,
mapping-checked [CD321x read diagnostic](fairydust/usb4/inspect-cd321x-io.py)
is prepared for the owner's regular Terminal; six offline tests and sysfs
dry-run pass. No task/configuration writes or live I2C reads were performed
by this preparation. EIO cause remains unresolved; see the current handoff.

[Earlier bounded live checks](fairydust/usb4/evidence/2026-10-16-neo-live-status.md)
confirm Neo sleep assertions and Dell USB inventory, but no proxy endpoint or
external display picture. The physical dock identity/topology remains
unconfirmed. Compiler smoke has passed; the M1 Pro native baseline, approved
guest route and hardware trace remain. Keep SSH work off the primary chat.

MacBook Neo recorder now reached by SSH; key login installed and verified.
Sleep assertions are active on Neo and the Linux target. Private Python,
matching m1n1 source/build and dependencies are staged; offline checks pass
on Darwin ARM64. See [recorder setup](fairydust/usb4/NEO-RECORDER-SETUP.md)
for verified results and USB/guest gates still remaining.

[`Complete macOS cutover checklist`](fairydust/usb4/MACOS-CUTOVER-CHECKLIST.md)
is published with a native collector, IORegistry metadata parser and raw
DPTX trace hook. Native baseline collection is deferred until fresh reboot
authorization. Full MMIO capture needs
the Neo recorder and matching target XNU kernelcache; the earlier iBoot recipe
was incorrect. Twelve offline tests pass; no macOS trace or picture yet.

[`DP-IN/AUX audit`](fairydust/usb4/DPIN-AUX-AUDIT.md) identifies the missing
Apple DP-IN node family and corrects the macOS capture plan. The current
force-link probe reaches DCP but leaves the display disconnected. Future
capture needs DP-IN ranges from macOS IODeviceTree or the m1n1 ADT and the DCP
in a two-host macOS hypervisor session; this is not currently authorized. The owner's
sudo ADT export on Asahi failed with `EPERM`; strict `/dev/mem` is enabled
and the ADT memory driver is not built. No display, kernel, or hardware
qualification is claimed.
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
| Boots Linux by default | Fairydust default helper is implemented, preserving stock Asahi as recovery; applying the persistent override is still pending. The last recorded stock-kernel boot lost dock mouse and Ethernet. | Apply the helper, then confirm kernel, m1n1/DTB chain, dock USB and Ethernet on-device. |
| Network indicator speed, connected-only Wi-Fi list, and usage views | Installed on the M1 Pro; user `netusage` service is active. Manual post-install includes the panel module and user logger. Overlay now includes the matching panel package for version-gated plugin compilation, then preserves the plugin. | Rebuild the image and verify the plugin loads against the final panel; check joined-network collapse, chevron expansion, and menu rendering. |
| Rounded screen corners | patched Gala, radius 14 (`install-gala-screen-corners.sh`) | **needs your look**: `gala-corners-look` |
| Pastel blue/rose theme | `install-theme-tweaks.sh` | **needs your look**: `colors-look` |
| Memory/swap/service tuning | `install-system-tuning.sh` (zram, no ModemManager/AppCenter daemon) | `zram-swap`, `services-trimmed` |
| Speaker tuning | `install-pipewire-lv2.sh` + `install-audio-stack.sh --with-dsp` | `audio-output-ok` passed |
| Battery charge limit 80% + on-battery CPU cap | `install-power.sh` (`mseries-power`) | limit verified; on-battery path simulated, real unplug pending (`power-battery-policy`) |
| Native Firefox (no snap) | `install-native-firefox.sh` | runs |
| Wi-Fi resume fix | `mseries-wifi-resume-fix` (2026-10-14: no longer aborts when the driver is already unloaded; reinstall pending on the M1 Pro) | CI test |
| Tracks upstream | merged `elementary/os` main @ 7024fd0 | `UPSTREAM-PINS.md` |
| Benchmarks | `mseries/benchmarks/` | see `benchmarks/README.md` |

## Owner roadmap: integrate Omarchy M, then migrate to Rust

Follow the Omarchy M people/projects, inventory and integrate their applicable
code into ElementaryOS_MSeries, qualify the complete behavior, then convert the
maintained implementation to Rust with measured performance and parity checks.
See [OMARCHY-M-ROADMAP.md](OMARCHY-M-ROADMAP.md) and the pinned discovery roster
in [upstreams/omarchy-m.json](upstreams/omarchy-m.json). Integration and the Rust
migration remain ongoing; announcement targets are not hardware test results.

## Implemented; runtime validation pending

**New feature request (2026-10-14):** [atomic app deployment and faster package
delivery](ATOMIC-APP-DEPLOYMENT.md). Stage verified releases, switch atomically,
retain rollback, and benchmark Flatpak/Nix alternatives to the current app
install workflow. The observed system uses apt; the reported slowdown is not yet
measured. Backend selection and implementation are open.
The manual installer batch now reuses successful metadata refreshes until a
repository/key changes and logs stage durations; real timing results are pending.
An opt-in Signal prototype (`install-signal.sh --atomic`) now stages verified
releases and supports selector rollback. Fault/concurrency tests pass; real
desktop update/rollback and backend selection remain pending.

The network/DNS logger now uses noninteractive authorization and installs a
polkit rule for read-only DNS monitoring by administrators, addressing repeated
desktop authentication prompts. Apply the updated logger installer once with
sudo available to enable DNS collection without dialogs.

| Feature | Change | Next check |
|---|---|---|
| Deferred per-user setup | Firstboot prepares CodexBar and Widevine tools and DNS policy; the user timer installs apps/services and stops after completion. Staged-root tests cover payload delivery, timer enablement and completion handling. | Verify a fresh desktop user's setup, including starting then quitting Brave to create its profile. |
| Keyboard brightness slider | Added to Pantheon's Quick Settings gear menu by `install-quick-settings-brightness.sh`; included in manual post-install, transform firstboot, and now the Apple Silicon overlay build. | Rebuild the image, then confirm it appears and changes the keyboard backlight on the live desktop. |
| OpenCode Go in M-series CodexBar | The installer enables the provider and passes the existing OpenCode Go CLI credential to CodexBar at runtime. | Install on the working desktop, sign in through OpenCode, and confirm the quota row. |

## Open problems

Owner boot policy: use the installed Fairydust USB4 kernel by default and retain
stock Asahi for recovery. Apply with
`sudo bash mseries/fairydust/usb4/set-default-kernel.sh --apply`; the stock boot
on October 14 did not enumerate the dock's mouse or Ethernet.

| Problem | Why | Next step |
|---|---|---|
| **Built-in display dims unexpectedly** (owner-reported urgent bug, 2026-10-14) | The user installer disables ambient screen adjustment and idle dimming, and the image enhancement layer supplies the same defaults to new sessions. Manual brightness, blanking, and suspend remain available. | Apply the brightness stage, then confirm on AC/battery and through suspend/resume. If brightness still changes, capture the backlight value and related power-service logs. Cause remains unconfirmed. |
| Homeboard elementary Tasks sync bridge | It needs `gir1.2-ecal-2.0` and `gir1.2-edataserver-1.2`, then owner Google sign-in. Only the browser launcher is installed so far. | Install the two system packages with admin access, run the upstream Linux installer, and let the owner complete Google sign-in. Do not save credentials in this repository. |
| Emporia elementary desktop client | The Linux client requires WebKitGTK 6; the public HTTPS origin is still gated on TLS and authentication, while a second local poller could duplicate the active SER8 collector. | Install the WebKit dependency, configure only the owner's existing collector tunnel or a verified authenticated HTTPS origin, and test the client without enabling a collector. |
| **Expand elementary root using the 112 GiB gap** | Gap is before the Asahi stub/EFI/root unit; the added Btrfs member would require early LUKS unlock and initramfs discovery | Verify gap was prepared by Asahi Installer, review read-only preflight and verified backups; see [`procedures/ROOT-EXPANSION.md`](procedures/ROOT-EXPANSION.md) |
| **Monitor through the dock** (2 DP + HDMI on a WD22TB4) | Needs DisplayPort tunnelling inside USB4 (unimplemented upstream; Sven Peter: "requires reverse engineering that is not done yet"). The CD321x firmware picks USB4 and Linux has no mode control, so a fall-back to plain DP Alt Mode can't be forced. **Owner directed the RE path (2026-10-15): make the dock work, not the Mac's own ports.** The display crossbar already knows how to route the controller to the ACIO DP IN adapters (`dpin0`/`dpin1`); the missing piece is "who drives the DP IN adapter, and when". Experiment 1 is implemented and awaiting a hardware boot — see [`fairydust/usb4/DP-TUNNEL-RE.md`](fairydust/usb4/DP-TUNNEL-RE.md). Non-dock fallbacks are in [`fairydust/usb4/DOCK-VIDEO-DECISION.md`](fairydust/usb4/DOCK-VIDEO-DECISION.md). | Build the `-dptunnel` kernel (`FAIRYDUST_DP_TUNNEL=1`, or the `fairydust_tunnel` CI dispatch), boot it with `thunderbolt.allow_dp_tunnel=1`, run [`fairydust/usb4/test-dp-tunnel.sh`](fairydust/usb4/test-dp-tunnel.sh), and force the controller link through the connector `force_link` debugfs. Then replace the hammer with the real trigger; the last step needs a macOS m1n1-hypervisor trace from a second computer. |
| Suspend with a USB4 dock attached | `thunderbolt-apple-acio` vetoes suspend by design; the Mac stays awake with the display off | Needs the ACIO sleep/wake handshake (large). Cheap option: a clean "docked lid" mode that locks and stops the 30 s retries. |
| USB-C (non-USB4) devices lost across suspend | `phy-apple-atc` / `dwc3-apple` have no system-sleep PM; tipd resume only re-enables the IRQ | Kernel fix, tested with the user present. |
| Lid-open login needs a power-button press | Resume and greeter start correctly in the log; the panel or input does not respond until the power key | Trace one resume (see BUG-FIX-ROADMAP.md). |
| Dock Ethernet icon dies and is recreated | RTL8153B renamed eth0 to enx...; fresh NetworkManager profile each time; `rtl8153b-2.fw` missing | Add firmware, pin one profile, retest. |
| Wingpanel crash `PanelWindow.on_realize` | Upstream bug; Gala respawns the panel | Report upstream (not done). |
| **One-command installer untested on hardware** | `bin/elementary-mac-setup` + `mseries/install-unlock-screen.sh` (elementary-branded LUKS unlock screen) were written without a spare Mac; only the state machine/config logic is unit-tested | Run on a backed-up Asahi Alarm BTRFS install; confirm plymouth/keymap hook order, passphrase entry, LightDM autologin, then drop this row |
| Hardware video decode after long uptime | H.264 decode at 720p, 1080p and 4K works on the current kernel; the usb4.4 kernel includes a fix for large fragmented allocations | After long uptime on usb4.4, run `mseries/check-video-decode.sh` without compacting memory first. |

## M1 Pro parity with Omarchy M (audited 2026-10-14 against omarchy-mac-pkgs 222f7a8)

Done on the running system: Wi-Fi resume fix, speaker safety and DSP, ambient keyboard light, battery charge limit, dock hub/mouse/Ethernet, docked lid mode, zram and service trimming. Remaining, in order:

1. ~~Port `omarchy-audio-watchdog` (audio-stack self-repair) to Pantheon.~~ Installed on the M1 Pro 2026-10-14 with `sudo bash mseries/enhance.sh --only audio`, together with the no-suspend and headset-mic WirePlumber rules (rules apply at the next login).
2. Decide the Apple function-key default (`fnmode`), then make it explicit.
3. Mic mapping (`omarchy-audio-asahi-mic-map`) re-homed to the elementary audio session.
4. Lid-open login and Touch ID research (see Stretch goal 0).
5. Verify the usb4.4 kernel's AVD allocation fix after long uptime; the VA-API bridge and H.264 720p/1080p/4K decode already work on the current kernel.
6. Put the tested audio chain into the factory image.

Performance work stays measured: use `mseries/benchmarks/` before and after each change and keep the medians.

## Stretch goals (rough order of value)

0. **Apple ecosystem gaps: iCloud password sync and iMessage** (reported 2026-10-14; see `BUG-FIX-ROADMAP.md`). OpenBubbles is the first candidate for iMessage.
0. **ArtCraft apps as native Adobe and Office replacements** (evaluation requested 2026-10-14; see `BUG-FIX-ROADMAP.md`). Build, license-check and benchmark each Rust app on aarch64 before packaging.
0. ~~Native macOS installer modelled on `omacom/omarchy-mac-installer`~~ **Not pursued** (owner, 2026-10-14). Study kept in [`MAC-INSTALLER-PLAN.md`](MAC-INSTALLER-PLAN.md).
0. **Battery drain, phone-tether internet and minimum brightness** (reported 2026-10-14; rows in `BUG-FIX-ROADMAP.md`). The owner suspects the planned Rust battery-profile migration might fix the drain; measurement says the largest found cause was an audio rule, not the profile code, so port it for safety (see `EDGE-AND-RUST-PLAN.md`) but test the claim with before and after power readings.
0. **Universal Siri/Whisper-like speech to text** (requested 2026-10-14; see `BUG-FIX-ROADMAP.md`). Dictate into any focused text field in any app, plus a later voice-assistant layer. Local only (no audio leaves the Mac). Candidate engine: whisper.cpp or similar on the M1 Pro (Vulkan on Honeykrisp, or CPU); universal insertion through an IBus input method (works for GTK, Qt and Electron apps) rather than per-app plugins. Depends on the built-in microphone working: the Asahi mic mapping from Omarchy is not ported yet (parity list item 3). Not started.
0. **Stay within 24 h of upstream, and port privileged code to Rust** (requested 2026-10-14; plan in [`EDGE-AND-RUST-PLAN.md`](EDGE-AND-RUST-PLAN.md)). Watched projects: [`WATCHLIST.md`](WATCHLIST.md).
0. **True Tone-like display** (requested 2026-10-14; see `BUG-FIX-ROADMAP.md`). Shift the display's white point toward the room light. Apple's True Tone uses a multi-channel sensor; the M1 Pro ambient light sensor (`iio:device1`, `aop-sensors-als`) exposes only `in_illuminance_input` (lux) on this kernel, so a faithful version is not possible yet. Interim plan: map lux plus time of day to a colour temperature through the colour plugin's night-light path (`night-light-temperature`, currently 4500 K, night light off), with slow easing and an off switch. Must not touch brightness (ambient auto-brightness stays off, see the dimming fix).
0. **Lid open shows the login screen, with Touch ID.** Today the login needs a power-button press after resume (bug tracked in `BUG-FIX-ROADMAP.md`). First fix the wake path; then investigate fingerprint login. No Linux driver for the Mac Touch ID sensor (Secure Enclave) is known to this project, so treat Touch ID as research, not a plan.

1. **Dock video via m1n1 hypervisor trace.** Needs a second computer (below). Result would also help every Asahi user.
2. ~~**Panel toggle for the battery charge limit**~~ Done 2026-10-13: a switch in the gear menu (`quick-settings/ChargeLimit.vala`, polkit action in `power/`). Pending your click-through: check `charge-limit-toggle`.
3. ~~**Docked lid mode**~~ Done 2026-10-13: `install-docked-lid.sh` (user service). Real lid close pending: check `docked-lid-works`.
4. ~~**Linux VMs with KVM**~~ Guide written 2026-10-13: [`KVM-VMS.md`](KVM-VMS.md) (boot verified headless; graphics, networking address and benchmark overhead not yet measured).
5. **Publish benchmark history** for every kernel/Mesa update, plot trends.
6. **Install media / transform script** for other M1/M2 Macs (see `TRANSFORM-DESIGN.md`).
7. **Tether continuity add-on**: pinned, removable ARM64 package installer and optional Brave integration are implemented (merged to main 2026-10-14); iPhone/Brave qualification remains. Current BlueZ 5.85 is below Tether's 5.86 minimum for Messages. See [`TETHER-CONTINUITY.md`](TETHER-CONTINUITY.md).
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

## GitHub upstream monitoring — 2026-10-14

`Watch public upstreams` runs every six hours and on demand. It combines
`local-ai/people-watch.json` subscriptions with the explicit branches in
`upstreams/omarchy-m.json`, and maintains one issue with pending revisions,
release changes and fetch failures. Closing the issue acknowledges observations;
new changes reopen it. Failed fetches preserve the last successful observation
and fail the Action. No upstream code is automatically merged or deployed.
The native macOS installer remains reference-only, per the owner decision.

## Factory configuration delivery — 2026-10-14

The Apple overlay finalize hook now exports its surviving `/etc` files to
`/usr/share/factory/etc` and generates individual tmpfiles copy/link entries.
This carries Wi-Fi enablement, module options and brightness autostart into
the `/usr`-only sysupdate artifact. Missing files are populated even when
parent directories already exist; administrator edits are preserved.
Export happens after pruning so unrelated base configuration is not claimed.
Implementation reviewed; no tests or image build run in this batch.

Remaining: build and boot qualification; shared enhancement-module integration,
canonical power helper under `/usr`, baked application dependencies and an
immutable-safe per-user setup path. The existing enhancement firstboot job
uses apt/build writes to `/usr` and cannot be enabled unchanged on EROFS.

## Offline factory enhancements integrated — 2026-10-14

Apple overlay finalize now stages `tuning,power,audio,session,theme,payload`
through the shared enhancement installer, then merges them after pruning.
The immutable power helper, polkit policy and compiled Quick Settings now
agree on `/usr/libexec/mseries/power`; `/usr/bin/mseries-power` supplies the CLI.
Both arm64 consumers explicitly install the runtime and CodexBar Qt dependencies.
Netusage authorization is baked, and a factory readiness file replaces the
otherwise unreachable firstboot dependency marker for per-user setup.

Dconf sources/profile are merged with distribution defaults and compiled with
the target binary before pruning. An early service recompiles persistent
`/etc` defaults before login after updates. Per-file factory copies preserve
administrator settings, including existing profiles that do not select local
defaults; those profiles require explicit selection to use these settings.

Per-user setup stops polling after CodexBar/netusage finish if the default
Brave profile is absent. A profile-change path unit wakes DRM setup later and
restarts retries until Brave closes and installation succeeds. Custom profile
locations retain timer polling. The image still does not bake Brave, video
decode, gestures or the remaining patched desktop components; their apt/build
firstboot modules stay disabled on immutable `/usr`. Speaker safety and full
hardware qualification remain separate requirements.

Reviewed twice by a subagent and corrected its findings. No tests or image
build were run in this batch. Existing pruning fixture now mocks its absent
target dconf compiler; that fixture is not target compilation evidence.
Next: build/boot qualification and bake the remaining network-dependent modules.

## Factory gestures baked at build time — 2026-10-14

Added `build-touchegg` at upstream 2.0.18 commit
`fc30d316e163f4504043353d6610e670ce5c6439` (GPL-3.0-or-later).
CMake builds with the CMake 4 compatibility option and explicit /usr + /etc
paths. Only the daemon, its configuration, service, license/provenance and
build recipe survive pruning. The X11 client autostart is omitted because
Gala consumes the daemon directly. Both image consumers install its runtime
libraries. Offline enablement and a vendor preset cover live and immutable
images; leaf factory export carries the service link. Udev's sysusers file
provides the service's input group.

The manual installer now fetches the same exact commit rather than a mutable
tag. Added Touchegg to GitHub upstream subscriptions. Subagent reviewed source
dependencies, paths, activation and licensing. No tests/build or physical
gesture qualification were run. Remaining browser, video and desktop patches
still require build-time integration; factory hardware qualification is open.

## Factory video-decode bridge candidate — 2026-10-14

Added `build-video-decode` using the existing manual installer's exact c653eaa
archive and SHA256. Meson builds/installs the stripped VA-API shared library;
finalize retains it, the Asahi alias and GPL/source/support documentation.
Competing canonical libraries or foreign Asahi aliases fail closed. Runtime
libva/libdrm and vainfo are declared in both arm64 consumers. The fragmentation
mitigation is shared with the manual installer and exported as a factory default.
Added the source to GitHub watch subscriptions and corrected stale PORT-MAP rows.

This packages a bridge candidate, not qualified hardware decode. The pinned
upstream explicitly has no supported matrix rows, and its M1/T8103 hardware
evidence does not qualify M1 Pro. AV1 compilation requires modern UAPI headers
but proves no hardware AV1 support. Kernel `apple_avd`, matching firmware,
codec/client checks and factory build/boot qualification remain open.
Subagent source/implementation review; no tests or image build run.

Final live/sysupdate post-install hooks also check package ownership of both
VA driver paths, catching a consumer Mesa package collision after overlay
application. Missing ownership metadata or inconsistent payload fails the build.

## Factory sound/keyboard fixes and panel artifact checks — 2026-10-14

Added pinned sound and keyboard builds to the Apple overlay and matching
packages/dependencies to both consumers. Pruning retains their plugins, licenses,
patches and build recipes. `panel-factory-pins.json` inventories all four panel
plugins; each builder records the actual plugin SHA256 and its source metadata.
Both final-image hooks reject missing/changed plugin bytes, incompatible package
versions and mismatched provenance. The recorder checks the build script's
source revision against the pin table before recording it.

Version checks now allow Debian epochs/packaging suffixes while rejecting
`8.0.30` as a substitute for `8.0.3`. The keyboard patch also initializes an
already-active layout's checked state before listening for subsequent changes.
Added the two elementary sources to GitHub subscriptions.

Subagent implemented/reviewed source/dependency and artifact-check pieces;
parent integrated image hooks and initial-state fix. No tests or build run.
Pinned upstream Meson/license contents could not be fetched in this turn;
dependency/license audit used repository installers and installed package
metadata, and the build refuses missing upstream license files. Network access
for Git required sandbox escalation. Factory load/render/boot qualification,
browser integration and remaining Files/Gala patches remain open.
