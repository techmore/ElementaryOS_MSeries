# elementary OS for Apple Silicon (M-series)

> **Source of truth for apps:** the Rust Pantheon SDK and first-party apps are edited in
> [techmore/mseries-sdk-apps](https://github.com/techmore/mseries-sdk-apps); their copies here are frozen
> snapshots guarded by CI. See [mseries/REPO-OWNERSHIP.md](mseries/REPO-OWNERSHIP.md).

elementary OS 9 on an M1/M2-family Mac, alongside macOS: Asahi Alarm as the boot
layer, elementary (Pantheon) as the system you use, installed with one command,
full-disk encryption included. Modelled on [omarchy-mac](https://github.com/omarchy-mac/omarchy-mac),
whose Asahi boot and encryption tools it reuses.

> 🚧 **Work in progress.** Not yet run end to end on a freshly wiped Mac. Back up everything first. [Status](#status)

**The whole install, in three commands** (details for each step below):

1. In **macOS Terminal**: `curl https://asahi-alarm.org/installer-bootstrap.sh | sh`
2. Boot Linux, log in as `root` / `root`, run `nmtui` to join Wi-Fi.
3. As root: `curl -fsSL https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/main/bin/elementary-mac-setup | bash`

---

## Before you begin

- A recent backup of macOS (Time Machine or similar) and of anything you keep on this Mac.
- An Apple Silicon Mac (M1/M2 family): [device support](https://asahilinux.org/fedora/#device-support).
- At least 60 GB for Linux (the installer refuses to build with under 40 GB free), on AC power.
- Internet access.

## Install

### 1. Run the Asahi Alarm installer, from macOS Terminal

```bash
curl https://asahi-alarm.org/installer-bootstrap.sh | sh
```

Choose `Asahi Alarm Minimal (BTRFS)` and give Linux at least 60 GB.

### 2. Boot into Arch and get online

Log in as `root` (password `root`), then connect to Wi-Fi:

```bash
nmtui
```

Choose `Activate a connection`, then `Quit`. If `nmtui` shows an error right after activating, reboot and try again.

### 3. One command

Still as root:

```bash
curl -fsSL https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/main/bin/elementary-mac-setup | bash
```

Nothing to prepare beyond the network. It asks whether to encrypt the disk, then your username, hostname and
password, and runs by itself from there. To read it first, or to pass options:

```bash
curl -LO https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/main/bin/elementary-mac-setup
bash elementary-mac-setup --no-encrypt
```

### 4. What happens (leave it alone, it reboots on its own)

| Step | What | Time |
|---|---|---|
| prerequisites | full `pacman -Syu`; reboots first if the kernel changed | 5-20 min |
| boot layout | `/boot` moves onto the EFI partition, reboot | 1-2 min |
| encryption | next boot: you **choose the disk passphrase**, then the partition is rewritten in place | 20-60+ min |
| elementary build | downloads Ubuntu base, installs the desktop, creates your account, unlock screen, auto-login, default boot entry | 30-60 min |
| first boot | you are logged in; Brave, hardware video decode, gestures and panel patches install in the background | 15-40 min |

Encryption rewrites the whole root partition and there is **no recovery key**: if you lose the passphrase, the
data is gone. With encryption on, every boot shows the **elementary unlock screen** (elementary Plymouth theme,
Inter font) and then logs you straight in, because the passphrase is the authentication.

### 5. Check it

```bash
elementary-mac-setup --status          # where the installer is
elementary-mac-enhance --status        # first-boot enhancements: brave / video / gestures / ...
sudo mseries-power status              # battery charge limit
bash mseries/check-video-decode.sh     # hardware video decode, 720p / 1080p / 4K (from a clone of this repo)
```

More checks: [`mseries/POST-BOOT-CHECKS.md`](mseries/POST-BOOT-CHECKS.md).

### If something goes wrong

The Asahi Alarm system stays in the boot menu as a rescue system (it keeps Asahi Alarm's stock `root`/`root`
login, same as upstream omarchy-mac; the machine runs no SSH server by default, change it with `passwd` if you
expose the machine). If setup stops, fix the cause and run `elementary-mac-setup --resume`; `--abort` stops it
without undoing anything. Logs: `/var/log/elementary-mac-setup.log`, `/var/log/elementary-mac-setup-grow.log`,
`/var/log/elementary-mac-enhance.log`. Recovery steps for each case are in
[`mseries/REINSTALL-RUNBOOK.md`](mseries/REINSTALL-RUNBOOK.md#5-if-something-fails).

### Options

`--no-encrypt`, `--user`, `--hostname`, `--keymap`, `--keep-default` (don't change the default boot entry),
`--no-enhancements`, `--repo <owner/repo>` (install from a fork), `--status`, `--resume`, `--abort`, `--unlock-screen`.

## What you get without asking

zram swap and no ModemManager; an 80% battery charge limit with a Quick Settings switch (`sudo mseries-power limit 100`
to lift it) and a lower CPU ceiling on battery; docked-lid mode (lid locks instead of suspending while a USB4 dock is
attached); GNOME-style brightness compatibility; ambient keyboard lighting; Wi-Fi resume recovery and firmware
provisioning; speaker protection (`speakersafetyd`); softer accent colours; and the display-crossbar and Apple HID
fixes in the boot image so the trackpad and screen come up reliably.

On the first boot with network, a one-shot job (log in `/var/log/elementary-mac-enhance.log`) adds **Brave**,
**hardware video decode** (VA-API driver for the Apple Video Decoder, built from a pinned, checksum-verified source
and checked with `vainfo`), the Touchegg gesture daemon, and the patched panel pieces (network speed graph, brightness
and charge controls in Quick Settings, sound/keyboard indicator fixes, the Files login-stall fix, the on-screen-keyboard
guard). Each is built from a pinned commit, version-gated and best-effort.

Optional, not automatic: `elementary-mac-enhance --run --with firefox`, rounded screen corners
(`mseries/install-gala-screen-corners.sh`), the Asahi speaker DSP (`mseries/install-pipewire-lv2.sh` then
`install-audio-stack.sh --with-dsp`), and the Command/Ctrl key layout (`mseries/apply-desktop-settings.py`).
For a native GitHub repository dashboard, see the optional [RepoBar-style elementary OS port](mseries/REPOBAR-PORT.md).

---

## Status

Experimental and unfinished. Current state, blockers and the next task: [`mseries/OS9-HANDOFF.md`](mseries/OS9-HANDOFF.md).

| Part | State |
|---|---|
| One-command installer (boot layout, encryption, build, enhancements) | written, sandbox-tested, **not run on a wiped Mac** |
| elementary unlock screen (Plymouth) | written, **not seen on hardware** |
| Hardware video decode | 720p/1080p/4K passed on the earlier stock-kernel setup. Requalification on Aurora and long-uptime checks remain separate; see [video decode](mseries/video-decode/README.md). |
| Running Aurora `.20` kernel | Boots on the J314S M1 Pro; the owner confirms a working dock display at 1080p/60. Sustained VRR, dock stability and suspend/resume remain open. See the [hardware receipt](mseries/aurora/hardware-tests/2026-10-18-j314s-vrr-and-boot-archive.md). |
| Earlier Fairydust USB4 kernel | Historical boot and peripheral results are retained in [CUTOVER.md](mseries/fairydust/usb4/CUTOVER.md); its older dock-video limitations do not describe the newer Aurora result. |
| Power and performance parity with macOS | **Not established.** Matched workload, battery and sustained-performance comparisons remain open. |
| Factory ISO | builds in CI and locally (about 17 min on the M1 Pro), boots to the installer in a VM, **unverified on Apple hardware** |
| Documentation index | [`mseries/DOCS.md`](mseries/DOCS.md) |

### What works on an M-series Mac today

Observed on the owner's 14-inch M1 Pro (J314S) running the transformed desktop on Aurora `.20`, as of
October 20, 2026. "Works" means used daily; "partial" means it works with a documented limit; "open" means
not working or not yet qualified. Other Mac models have no results of their own.

| Hardware / feature | State | Notes |
|---|---|---|
| Boot menu, kernel, Pantheon desktop | works | Asahi Alarm stays as the rescue entry; Aurora `.20` is the running kernel ([kernel flow](mseries/KERNEL-FLOW.md)) |
| Internal keyboard and trackpad | works | Apple HID loaded early in the initramfs so the trackpad is up at the greeter |
| Built-in display, brightness keys, notch layout | works | 120 Hz panel; full-height notch-aware Wingpanel profile ([display space](mseries/display-space/README.md)) |
| ProMotion / VRR | partial | brief kernel activation seen (3 of 25 samples); sustained variable refresh unverified ([receipt](mseries/aurora/hardware-tests/2026-10-18-j314s-vrr-and-boot-archive.md)) |
| GPU acceleration (Asahi/AGX, Honeykrisp Vulkan) | works | no Metal-parity or benchmark claim |
| Hardware video decode (Apple Video Decoder, VA-API) | partial | 720p/1080p/4K passed on the earlier stock kernel; not yet requalified on Aurora ([video decode](mseries/video-decode/README.md)) |
| Wi-Fi | works | firmware provisioned at install; `brcmfmac` reload after resume ([firmware](mseries/FIRMWARE-WIFI.md)) |
| Bluetooth | partial | radio and paired devices from Quick Settings, resume recovery unit ([hardware](mseries/hardware/)); BlueZ 5.85, so Tether's SMS/OTP bearer (needs 5.86) is out; the owner's device check is still open |
| Speakers | works | `speakersafetyd` protection on; the Asahi DSP chain passed its output check (`install-audio-stack.sh --with-dsp`) |
| Built-in microphone | works | used by F5 dictation ([acceptance](mseries/dictation/F5-ENGLISH-ACCEPTANCE.md)) |
| Headphone jack, dock audio | open | no headphone result recorded; dock TV audio unresolved with display audio off in the running kernel ([dock TV audio](mseries/audio/DOCK-TV-AUDIO.md)) |
| Ambient keyboard backlight | works | AOP illuminance sensor plus UPower ([keyboard backlight](mseries/keyboard-backlight/README.md)) |
| Battery charge limit (80 %) and battery CPU ceiling | works | `sudo mseries-power status`; Quick Settings switch |
| USB4 / Thunderbolt dock (WD22TB4): hub, Ethernet | works | Realtek firmware and a persistent adapter-bound profile |
| External display through the dock's HDMI | works | 1920x1080 at 60 Hz confirmed by the owner; long idle, replug and DPMS cycles still open (#200) |
| USB-C DisplayPort alt mode (monitor straight on a port) | open | needs the experimental kernel path ([dock notes](mseries/USB-C-DOCK-DP-ALT-MODE.md)) |
| Suspend / resume | partial | an undocked cycle passed on the earlier Fairydust kernel; on Aurora `.20` and with a dock attached it is open; docked-lid mode locks instead of suspending |
| Camera (ISP) | open | not qualified on this stack |
| Touch ID | open | fingerprint matching lives in the Secure Enclave and has no Linux path; probing the sensor froze the machine once (#70) |
| Full-disk encryption, unlock screen | partial | implemented in the installer; not yet run on a freshly wiped Mac |
| Power / performance parity with macOS | open | no matched measurements yet ([power roadmap](mseries/POWER-ROADMAP.md)) |

The full post-install checklist, with the exact commands, is [`mseries/POST-BOOT-CHECKS.md`](mseries/POST-BOOT-CHECKS.md).

## Fixes, tests and remaining work

Status recorded **October 18, 2026**, primarily on the **14-inch M1 Pro (J314S)**.
The sections below distinguish implemented fixes from recorded tests and pending
hardware acceptance. They are not a support claim for every M-series Mac.
The transformed desktop, experimental kernels and factory image have separate
qualification; a successful build does not establish a successful hardware boot.

### Desktop dock and window layout

- **Fixed / implemented:** Native dock positioning persists across restarts and
  clamps to the available screen space. The compact profile uses 40-pixel icons,
  preserves pinned apps and drawers, and hides when any window overlaps. Gala
  reserves space while the dock is visible and returns it when hidden. Maximized,
  half-snapped and managed quarter windows follow the work area; manually sized
  windows retain their size. Fullscreen and secondary-monitor handling avoid
  stale reservations and repeated hide/reveal resize loops.
- **Tested:** ARM64 dock, Gala and quarter-plugin builds pass. Ten isolated
  real-dock/GTK Wayland checks cover reveal/hide, overlap, half/quarter snapping,
  manual sizing, fullscreen and two monitors. Nine existing quarter shortcut,
  corner-drag and Escape checks also pass. The native dock is installed; the
  rebuilt compositor/plugins load at the next sign-in.
- **Left to do:** Confirm reveal, resize, placement persistence and monitor
  switching in the physical desktop after sign-in. Confirm the updated YouTube
  launcher icon after reopening its window. No dock power saving is claimed.

Details: [desktop space](mseries/display-space/README.md),
[window snapping](mseries/window-snapping/README.md).

### Work Mode wallpaper

The `mseries/install-work-mode.sh` installer adds a native Work Mode panel under
System Settings → Personal. It provides an on/off switch, a separate Blue Flow
work wallpaper (and image picker), and optional weekday start/end times. A per-user systemd timer checks
the schedule every minute; when work hours end, the wallpaper saved before Work
Mode began is restored. This is implemented in source and has not yet been
installed or visually qualified on the owner’s desktop.

### OS bar, menus and indicators

- **Fixed / implemented:** The native Wingpanel profile protects the camera gap
  on the full-height J314 display, moves the existing clock/calendar beside it,
  and scrolls crowded controls. Cropped and external layouts keep the centered
  clock. Panel work also includes network-speed/usage views, brightness and
  charging controls, battery estimates, sound/keyboard fixes, and the custom
  CodexBar account/usage integration. The calendar dropdown now has Events and
  Tasks tabs backed by Evolution Data Server (EDS), plus an account-setup action.
  Tasks can be added to a chosen writable list and checked off directly in the panel, including repeating tasks.
  Events defaults to a compact upcoming 30-day list with optional Month, Week
  and Day views. Week/Day use time slots and event blocks with overlap lanes;
  Month/Upcoming retain compact lists. Open blocks for full event details.
- **Tested:** ARM64 builds and isolated notch-layout checks cover cropped,
  full-height, external, fractional-scale and crowded layouts. Twenty-one real-plugin
  EDS workflow groups cover time-grid geometry, navigation, task creation,
  checkbox saves, live edits, completion/deletion and source changes. CodexBar has recorded build/
  deploy checks and an owner-confirmed native Claude account-switch round trip.
- **Left to do:** Accept the full-height layout after a hardware boot, including
  clock/popovers and crowded indicators. Complete Google sign-in and a real
  Calendar sync round trip. Network-rate recovery across Ethernet suspend/reboot
  and the reported signal dropdown issues remain on the bug backlog. Tests of
  individual indicators do not qualify every panel interaction or factory boot.

Details: [desktop space](mseries/display-space/README.md),
[calendar](mseries/calendar/README.md), [CodexBar port](mseries/CODEXBAR-PORT.md),
[bug backlog](mseries/BUG-FIX-ROADMAP.md).

### Kernel and Apple hardware support

- **Fixed / implemented:** The Apple Silicon integration carries early Apple
  HID loading, display routing, firmware provisioning and Wi-Fi resume recovery.
  Aurora `.20` includes J314S power-controller/fabric-idle support, external
  scanout votes, USB4/display-tunnel work and optional Thunderbolt sleep controls.
  Native Debian enhancement packages and a separate unified-kernel candidate
  are built as distinct experimental lanes.
- **Tested:** Aurora `.20` boots on this J314S, with scoped kernel/artifact,
  power-controller, idle, GPU and filesystem checks recorded. Earlier Fairydust
  results cover USB peripherals and an undocked suspend/resume cycle; those
  results are specific to that kernel and setup. Enhancement package CI passes.
- **Left to do:** Qualify `.20-enh1` and the unified candidate independently,
  including recovery and suspend/resume. Touch ID sensor probing has caused a
  freeze and remains unresolved; a boot with SEP loaded is not a Touch ID pass.
  The factory ISO still needs Apple hardware boot acceptance, and other Mac
  models require their own results.

Details: [kernel flow](mseries/KERNEL-FLOW.md),
[Aurora qualification](mseries/aurora/hardware-tests/README.md),
[trial and rollback](mseries/aurora/trial/README.md),
[hardware port map](mseries/PORT-MAP.md).

### External USB4 dock, Ethernet and displays

- **Fixed / implemented:** The newer Aurora path brings up the WD22TB4 USB4
  connection and external display tunnel. Ethernet work adds Realtek firmware
  and a persistent adapter-bound connection profile. Display profiles retain
  monitor modes/layouts; docked-lid handling provides a lock-without-suspend path.
- **Tested:** USB4 authorization, hub/Ethernet presence, display link training,
  EDID and an enabled connector are recorded on `.20`. The owner confirms the
  dock works and both displays look normal; the scoped visual receipt records
  external 1920×1080 at 60 Hz. Built-in VRR was briefly active in 3 of 25 samples.
- **Left to do:** Verify the physical HDMI/DP port independently, long docked
  idle, repeated unplug/replug, lock/display sleep, docked lid handling and
  suspend/resume. Recheck Ethernet persistence and indicator recovery through
  those cycles. Dock TV audio remains unresolved with display audio disabled
  in the running kernel. Brief VRR activation does not prove sustained VRR.

Details: [dock/VRR hardware receipt](mseries/aurora/hardware-tests/2026-10-18-j314s-vrr-and-boot-archive.md),
[dock TV audio](mseries/audio/DOCK-TV-AUDIO.md),
[dock and power evidence map](mseries/power/README.md).

### Power usage and battery parity with macOS

- **Fixed / implemented:** An 80% charge limit, battery-aware CPU ceilings and
  power-profile integration are available. Power monitoring and a macOS/Linux
  comparison harness track whole-machine usage, idle, video, sleep and component
  activity. Audio idle handling and application/display overhead have been
  investigated; remaining speaker activity is still tracked.
- **Tested:** Earlier controlled refresh-rate comparisons measured about
  1.7–2.0 W less at 60 Hz than 120 Hz in those setups. Local H.264 hardware decode
  also reduced power in an earlier playback comparison. These are scoped
  observations, not savings established on the current Aurora configuration.
  Current `.20` activity captures are observational, not matched idle baselines.
- **Left to do:** Collect matching macOS and Linux workloads on the same machine,
  brightness, refresh, topology and app state, with repeated alternating trials
  and median/p10/p90 results. Measure sleep drain, recovery, sustained VRR and
  current-kernel video usage. **Power/battery parity with macOS is not established.**
  Charge limiting protects battery wear; it does not demonstrate lower power use.

Details: [power roadmap](mseries/POWER-ROADMAP.md),
[macOS baseline method](mseries/power/macos-baseline/README.md),
[parity checklist](mseries/power/macos-baseline/PARITY.md).

### Overall performance parity with macOS

- **Fixed / implemented:** The desktop includes native window-layout fixes,
  zram, an Apple video-decode integration and local-AI runtime/profile management.
  These address specific usability and workload issues; they do not establish
  equivalent macOS responsiveness or throughput.
- **Tested:** Earlier stock-kernel records cover hardware decoding at 720p,
  1080p and 4K. Isolated window-layout checks and local-AI task/client benchmarks
  have retained results. Browser codec paths and runtime workloads differ, so
  these results are not a single cross-OS performance comparison.
- **Left to do:** Benchmark startup, interaction latency, multitasking, builds,
  sustained CPU/GPU workloads and media on matched macOS/Linux configurations.
  Record memory pressure, thermals and background activity alongside speed.
  **Overall performance parity remains unproven**; optimization candidates are
  proposals until measured and qualified.

Details: [benchmark harness](mseries/benchmarks/README.md),
[video decode](mseries/video-decode/README.md),
[performance candidates](mseries/PERFORMANCE-PORT-CANDIDATES-2026-10-18.md).

### CPU scheduling, scaling and idle

- **Fixed / implemented:** Battery CPU ceilings follow the selected power profile
  so performance requests can lift the battery cap. The current kernel provides
  frequency scaling and idle support; efficiency/performance-core behavior and
  timer/interrupt overhead are tracked separately.
- **Tested:** Earlier frequency sampling measured a roughly 76–79 ms P-cluster
  ramp to 90% of peak clock. Idle-state residency and interrupt measurements are
  recorded. Clock ramp is not application latency, CPU-rail power ramp or a
  macOS throughput comparison.
- **Left to do:** Recheck current-kernel scaling, core placement, deep-idle
  residency, sustained throughput and return-to-idle under matched workloads.
  Scheduler/tick changes remain experimental; proposed sched_ext schedulers
  require kernel support and Apple ARM64 qualification. CPU parity is unproven.

Details: [CPU/power workstreams](mseries/POWER-ROADMAP.md),
[scheduler candidates](mseries/PERFORMANCE-PORT-CANDIDATES-2026-10-18.md).

### GPU graphics, video and AI compute

- **Fixed / implemented:** The desktop uses Apple GPU acceleration with
  Honeykrisp Vulkan available. Local AI uses a separately pinned private Linux
  MLX/compute stack. Apple Video Decoder support is a separate media path;
  graphics acceleration does not imply every video codec is hardware-decoded.
- **Tested:** Graphics/runtime inventory, scoped Aurora GPU smoke checks and
  local-AI benchmarks are recorded. Earlier per-process GPU tracing identified
  substantial background work from agent UIs and the compositor. Hardware video
  decode results apply to their recorded kernel, codec and client combinations.
- **Left to do:** Compare graphics and compute throughput, frame pacing, idle
  activity and thermals with matched macOS workloads. Qualify current-kernel
  media paths, sustained VRR and GPU recovery. Vulkan availability does not prove
  Metal performance parity; ANE support is not qualified by GPU results.

Details: [local AI runtime and results](mseries/local-ai/README.md),
[power investigations](mseries/POWER-ROADMAP.md),
[video decode](mseries/video-decode/README.md).

### Local LLMs and file access

- **Fixed / implemented:** Newelle desktop/personal assistants and the separate
  Crush coding profile use measured Qwen3.5 4B defaults, with optional larger
  presets and memory/thermal guards. The desktop MCP adapter reads scoped UTF-8
  files and creates new notes under `~/Documents/Assistant Workspace`; traversal,
  symlink escapes and note overwrites are refused. It also provides explicit
  task/event writes, managed-browser reads, local unsent Mail drafts, energy and
  diagnostic tools. Broad shell and arbitrary-file
  tools are hidden in the preconfigured desktop profile; coding has a separate
  workspace/tool policy. Later user configuration can expand these capabilities.
- **Tested:** File create/read and boundary checks pass in retained tests.
  The adapter records 72 passing contracts, three successful
  note-to-task/read-back trials and three file-instruction rejection trials.
  Calendar/browser/local-draft workflows are documented with retained outcomes
  in the app integration report.
  The coding fixture has its own edit/result verification. These are scoped
  workflow results, not unrestricted autonomous access to the whole computer.
- **Left to do:** Qualify GUI task workflows, reminders and additional adapters.
  Gmail account access, broader browser actions, messaging and Calendar GUI
  reminders need dedicated implementations and tests. Larger-model diagnosis
  and fresh human microphone acceptance retain separate qualification gaps.
  Measure local-AI speed and energy against
  comparable macOS workloads before claiming parity.

Details: [local assistants](mseries/local-ai/README.md),
[file/app access and qualification](mseries/local-ai/APP-INTEGRATION.md),
[measured model results](mseries/local-ai/receipts/2026-10-16.md).

English F5 dictation is merged and activated with quiet Nemotron CPU streaming;
native ANE/MLX options and English voice replies have
[scoped acceptance results](mseries/dictation/F5-ENGLISH-ACCEPTANCE.md).
All seven installed app routes passed within the quiet and memory guards. Read the
[qualification ledger](mseries/dictation/QUALIFICATION-INDEX.md) before speech
benchmarks or continuation work; reuse completed evidence and inspect the
existing queue first.

The [v0.0.1 English F5 desktop update](mseries/releases/v0.0.1/README.md) is a
release candidate. A fresh ChatGPT physical-F5 attempt failed before recording;
its input compatibility launcher is staged and awaits a full app relaunch and
owner check. No v0.0.1 release is published yet.

---

## Other ways in

**Already running omarchy-mac (Apple Silicon)?** Cut over in place. Dry run first, it changes nothing and uploads its log for review:

```bash
git clone --depth 1 https://github.com/techmore/ElementaryOS_MSeries && sudo ./ElementaryOS_MSeries/transform/elementary-grow.sh --upload
```

Only after the dry run is reviewed: `--apply`, reboot, pick **elementary OS (M-series)** in the boot menu. Design and safety contract: [`mseries/TRANSFORM-DESIGN.md`](mseries/TRANSFORM-DESIGN.md).

**More:** [documentation index](mseries/DOCS.md), project overview [`mseries/README.md`](mseries/README.md), kernel and boot flow [`mseries/KERNEL-FLOW.md`](mseries/KERNEL-FLOW.md), bug backlog [`mseries/BUG-FIX-ROADMAP.md`](mseries/BUG-FIX-ROADMAP.md), Apple hardware reference [omacom/omarchy-mac-pkgs](https://github.com/omacom/omarchy-mac-pkgs).

---

## Building the ISO yourself

The factory image is an arm64 elementary OS 9 live ISO with the Apple Silicon layer
(`mkosi.images/apple-silicon/`) built in. It builds in CI (`OS 9 M-series experimental build`,
manual dispatch) and on an M-series Mac that already runs Linux; the recipe below is what the local
build on the J314S used ([`mseries/LOCAL-BUILD.md`](mseries/LOCAL-BUILD.md)). The ISO is **not yet
verified to boot on Apple hardware**; it has reached the graphical installer in a VM.

You need: an arm64 Linux host (the build is native, not cross), `sudo`, and **60 GiB free** on the
filesystem that holds the checkout (a conservative guard; the ISO is about 6.6 GiB and the build keeps
unpacked roots, caches and container layers beside it). The recorded build ran on 32 GB of RAM; a
smaller host is untested.

```bash
sudo apt install just podman zstd rsync         # the only host packages; mkosi runs in a container
git clone https://github.com/techmore/ElementaryOS_MSeries && cd ElementaryOS_MSeries
python3 mseries/local-build-preflight.py        # exit 0: arch, tools and the 60 GiB guard pass
just genkey                                     # once per checkout: image signing keys (mkosi.key/.crt)
just do-daily                                   # the build: about 17 min on an M1 Pro, 26 min in CI
ls -l mkosi.output/elementaryos-*.iso           # the result
sha256sum mkosi.output/elementaryos-*.iso       # record this with the source commit
```

What `just do-daily` does: pulls `ghcr.io/elementary/mkosi:tanit`, runs `mkosi` in a **privileged
podman container with host `/dev`** (loop devices are needed to assemble the image), builds the
`liveiso` and `sysupdate` images for the daily PPA stream, then runs `assemble-iso.sh`. It starts by
removing `mkosi.output/`. Keep the running kernel, bootloader and audio stack out of it: the build
installs nothing on the host.

- **Run it detached, with records:** `bash mseries/local-build-worker.sh` from a committed checkout
  runs the same steps and writes `local-build-records/status.json`, `build.log` and
  `INSTALLER-SHA256SUMS` (phase, elapsed time, exit code, ISO checksum) so a build survives the
  terminal and can be read by [`docs/local-build-status.html`](docs/local-build-status.html).
- **Check the wiring:** `python3 mseries/test-image-wiring.py` confirms the Apple layer is referenced
  by both the live ISO and the sysupdate image (CI also runs it against `just mkosi summary`).
- **Boot it in a VM** (no Apple drivers, but the installer and desktop can be exercised):
  `./mseries/vms/mseries-vm create elementary --iso mkosi.output/elementaryos-*.iso && ./mseries/vms/mseries-vm start elementary`
  ([VM notes](mseries/vms/README.md), [first VM smoke test](mseries/VM-SMOKE-TEST.md)).
- **Other streams:** `just do-stable` (stable PPA) and `just do-proposed`. `just clean` removes the
  caches (`mkosi.cache/`, `mkosi.tools/`, `~/.cache/mkosi`).
- **Before opening a pull request:** `bash mseries/validate.sh` (or `just check`) runs the same
  syntax, lint and unit checks as CI's `Validate M-series wiring` in about half a minute; no image build.

What a successful build proves: the configuration parses, every package installs, the Apple overlay
lands in the live installer. What it does not prove: that the ISO boots on a Mac. Hardware
acceptance is tracked in #201 and [`mseries/FIRST-ISO-BUILD.md`](mseries/FIRST-ISO-BUILD.md).

The rest of this page is the upstream elementary OS build documentation.

<div align="center">
  <a href="https://elementary.io" align="center">
    <center align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/elementary/brand/main/logomark-white.png">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/elementary/brand/main/logomark-black.png">
  <img src="https://raw.githubusercontent.com/elementary/brand/main/logomark-black.png" alt="elementary" align="center" height="200">
</picture>
    </center>
  </a>
  <br>
  <h1 align="center"><center>elementary OS</center></h1>
  <h3 align="center"><center>Build scripts for image creation</center></h3>
  <br>
  <br>
</div>

<p align="center">
  <img src="https://github.com/elementary/os/actions/workflows/daily-8.1.yml/badge.svg" alt="Daily 8.1">
  <img src="https://github.com/elementary/os/actions/workflows/daily-9.0.yml/badge.svg" alt="Daily 9.0">
</p>

---

## Building, Testing, and Installation

You'll need the following runtime dependencies:
* podman
* just
* zstd
* systemd

Generate keys and then build with `just`

```bash
just genkey
just do-daily
```
Create install media with [Fedora Media Writer](https://flathub.org/en/apps/org.fedoraproject.MediaWriter) or [Impression](flathub.org/en/apps/io.gitlab.adhami3310.Impression), or boot with GNOME Boxes (>=51).

### Installation (sysupdate)

Once in the liveiso, inside the terminal or a tty, run:

```bash
sudo elementary-install
```
You will be prompted with installation options.

### Installation (classic)

To install classic mode, follow the steps in the GUI installer from the liveiso.

## Operations

### Upgrades

`updatectl update`

Append the exact version ID at the end to upgrade to a specific version, or downgrade.

## Minimum specs
- UEFI with secure boot disabled
- 8 GB of USB flash drive
- GNOME Boxes >=51 (for VM only)
- 55 GB of destination disk
- 4 GB of system memory (RAM)
