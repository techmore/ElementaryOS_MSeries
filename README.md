# elementary OS for Apple Silicon (M-series)

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

---

## Status

Experimental and unfinished. Current state, blockers and the next task: [`mseries/OS9-HANDOFF.md`](mseries/OS9-HANDOFF.md).

| Part | State |
|---|---|
| One-command installer (boot layout, encryption, build, enhancements) | written, sandbox-tested, **not run on a wiped Mac** |
| elementary unlock screen (Plymouth) | written, **not seen on hardware** |
| Hardware video decode (720p/1080p/4K verified on the stock kernel) | Works on the current kernel; the usb4.4 kernel's memory-fragmentation fix still needs a long-uptime check |
| Patched kernel (usb4.4) | **Boots on the M1 Pro** (CI `.deb`, test GRUB entry, 2026-10-14). Hub, mouse, keyboard, USB audio and dock Ethernet work with the j314s device tree and newer m1n1. Dock video remains unsupported. See [`CUTOVER.md`](mseries/fairydust/usb4/CUTOVER.md) |
| Factory ISO | builds in CI, **unverified on hardware** |
| Documentation index | [`mseries/DOCS.md`](mseries/DOCS.md) |

---

## Other ways in

**Already running omarchy-mac (Apple Silicon)?** Cut over in place. Dry run first, it changes nothing and uploads its log for review:

```bash
git clone --depth 1 https://github.com/techmore/ElementaryOS_MSeries && sudo ./ElementaryOS_MSeries/transform/elementary-grow.sh --upload
```

Only after the dry run is reviewed: `--apply`, reboot, pick **elementary OS (M-series)** in the boot menu. Design and safety contract: [`mseries/TRANSFORM-DESIGN.md`](mseries/TRANSFORM-DESIGN.md).

**More:** [documentation index](mseries/DOCS.md), project overview [`mseries/README.md`](mseries/README.md), kernel and boot flow [`mseries/KERNEL-FLOW.md`](mseries/KERNEL-FLOW.md), bug backlog [`mseries/BUG-FIX-ROADMAP.md`](mseries/BUG-FIX-ROADMAP.md), Apple hardware reference [omacom/omarchy-mac-pkgs](https://github.com/omacom/omarchy-mac-pkgs).
The factory ISO builds in CI but is unverified on hardware. The rest of this page is the upstream elementary OS build documentation.

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
