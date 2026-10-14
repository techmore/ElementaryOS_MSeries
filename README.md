<div align="center">
  <p><strong>This is a derivative of the elementary OS 9 build system with an Apple Silicon (M-series) port.</strong> Start at <a href="mseries/README.md">mseries/README.md</a>. The owner has booted an installed elementary OS 9 desktop on an M1 Pro; the factory ISO now builds successfully but remains unverified on hardware. Current Apple hardware reference: <a href="https://github.com/omacom/omarchy-mac-pkgs">omacom/omarchy-mac-pkgs</a>.</p>
</div>

Upstream comparison, concrete bug-fix backlog, and porting boundaries:
[mseries/BUG-FIX-ROADMAP.md](mseries/BUG-FIX-ROADMAP.md).

## Install on an M-series Mac (one command, from Asahi Alarm)

1. From macOS Terminal run the Asahi Alarm installer, choose `Asahi Alarm Minimal (BTRFS)` and give Linux at least 60 GB:

   ```bash
   curl https://asahi-alarm.org/installer-bootstrap.sh | sh
   ```

2. Boot into Arch, log in as `root` / `root`, and get online with `nmtui` (`Activate a connection`).
3. Still as root:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/main/bin/elementary-mac-setup | bash
   ```

It asks whether to encrypt the disk, your username, hostname and password, then runs unattended across a few reboots: boot layout, in-place LUKS2 encryption (you choose the passphrase at the console), then a full elementary OS build into its own subvolume, set as the default boot entry. With encryption, every boot shows the **elementary unlock screen** (elementary Plymouth theme, Inter font) instead of Omarchy's, and logs you straight in because the passphrase is the authentication. The Asahi Alarm system stays in the boot menu as a rescue system. The rescue system keeps Asahi Alarm's stock `root`/`root` login, the same as the upstream omarchy-mac installer: it is the documented bootstrap account, it is the recovery path if elementary fails to boot, and the machine runs no SSH server by default. Change it with `passwd` if you expose the machine.

**What you get without asking:** zram swap and no ModemManager; an 80% battery charge limit with a Quick Settings switch (`sudo mseries-power limit 100` to lift it) and a lower CPU ceiling on battery; docked-lid mode (lid locks instead of suspending while a USB4 dock is attached); GNOME-style brightness compatibility; ambient keyboard lighting; Wi-Fi resume recovery and firmware provisioning; speaker protection (`speakersafetyd`); softer accent colours; and the display-crossbar and Apple HID fixes in the boot image so the trackpad and screen come up reliably. On the first boot with network, a one-shot job (`elementary-mac-enhance --status`, log in `/var/log/elementary-mac-enhance.log`) adds **Brave**, **hardware video decode** (VA-API driver for the Apple Video Decoder, built from a pinned, checksum-verified source and checked with `vainfo`), the Touchegg gesture daemon, and the patched panel pieces (network speed graph, brightness and charge controls in Quick Settings, sound/keyboard indicator fixes, the Files login-stall fix, the on-screen-keyboard guard). Each is built from a pinned commit, version-gated and best-effort. Optional, not automatic: `elementary-mac-enhance --run --with firefox`, rounded screen corners (`mseries/install-gala-screen-corners.sh`), the Asahi speaker DSP (`mseries/install-pipewire-lv2.sh` then `install-audio-stack.sh --with-dsp`), and the Command/Ctrl key layout (`mseries/apply-desktop-settings.py`). `--no-enhancements` skips all of it.

Useful flags: `--no-encrypt`, `--user`, `--hostname`, `--keymap`, `--keep-default` (don't change the default boot entry), `--no-enhancements`, `--status`, `--abort`, `--unlock-screen`. Steps 1 and 2 reuse the Asahi tools of [omarchy-mac](https://github.com/omarchy-mac/omarchy-mac), fetched at run time. **Not yet run end to end on a fresh Mac**: follow [`mseries/REINSTALL-RUNBOOK.md`](mseries/REINSTALL-RUNBOOK.md) for the first real test (backup, what to expect at each reboot, what to bring back if it fails); status in [`mseries/OS9-HANDOFF.md`](mseries/OS9-HANDOFF.md). Encryption rewrites the whole root partition in place, so back up first.

## M-series cutover quickstart (run on omarchy-mac, Apple Silicon)

Dry run first — changes nothing, uploads its log for review:

```bash
git clone --depth 1 https://github.com/techmore/ElementaryOS_MSeries && sudo ./ElementaryOS_MSeries/transform/elementary-grow.sh --upload
```

Paste the printed gist URL back for review. If `gh` isn't logged in over there: `sudo pacman -S github-cli && gh auth login`, then re-run. Only after the dry run is reviewed: `--apply`, reboot, pick **elementary OS (M-series)** in the boot menu. Full design + safety contract: [`mseries/TRANSFORM-DESIGN.md`](mseries/TRANSFORM-DESIGN.md). Post-boot checks: [`mseries/POST-BOOT-CHECKS.md`](mseries/POST-BOOT-CHECKS.md).

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
