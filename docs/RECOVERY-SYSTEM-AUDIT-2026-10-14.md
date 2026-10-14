# Full system audit and recovery runbook: elementary-m1

Audited **2026-10-14**, read-only, immediately before the planned wipe and reinstall to merge
free space into one root. Purpose: rebuild this machine from scratch with nothing lost that
matters.

Secrets are intentionally **not** recorded here (LUKS passphrase, SSH private key, `gh`
token, Tailscale auth, Wi-Fi PSKs, `/etc/nmapui/nmapui.env`). Section 9 says how to
re-establish each one.

---

## 0. TL;DR: what is actually irreplaceable

| Item | Where it lives now | In git? | Action |
| --- | --- | --- | --- |
| Kernel source/patches (fairydust + USB4), PKGBUILDs, kernel `config`, m1n1 build scripts | `ElementaryOS_MSeries/mseries/fairydust/{,usb4/}` | **Yes, pushed** | Nothing, just rebuild |
| Built **m1n1 `boot.bin`** (USB4-tunable build) | ESP `/boot/m1n1/` | No | Rebuild (`usb4/build-m1n1.sh`) or copy off first |
| Built kernels/initramfs (`vmlinuz-*`, `initramfs-*`) | ESP `/boot` | No | Rebuild from the repo |
| GRUB `custom.cfg` (boots USB4 kernel by default) | ESP `/boot/grub/` | Reproduced in section 4 | Recreate |
| Prebuilt kernel pkgs (`*.pkg.tar.xz`, ~60 MB) | `~/fairydust-usb4/pkgs/` | No | Copy off if you do not want to rebuild |
| Non-git working dirs | see section 8 | No | Copy off or accept loss |
| SSH key `~/.ssh/id_ed25519` | `~/.ssh` | n/a | Copy off, or generate a new key and re-add on GitHub |

All 12 repos under `~/code` that are git repos have **0 unpushed commits and a clean tree**
(checked). The exception is `mario-dash`, which is not a git repo.

---

## 1. Hardware / platform

- Apple **MacBook Pro 14" M1 Pro (2021)**, board `apple,j314s`, `MacBookPro18,3`, aarch64
- Disk: **APPLE SSD AP1024R**, 931.8 GiB NVMe, GPT, **4096-byte sectors**
- Wi-Fi/BT: Broadcom BCM4387 (firmware provisioned by `mseries-wifi-firmware.service`)
- Original Asahi installer base: `https://asahi-alarm.org/`, macOS stub **13.5 (22G74)**, install
  dated 2026-09-14. admin user on the macOS side: `seandolbec` (real name `techmore`)

## 2. Partition table (before wipe)

Sector numbers are 4096 B sectors.

```
 #  Start        End          Size(sec)   Content
 1  6            128005       128000      iBootSystemContainer   <-- NEVER TOUCH
 2  128006       188116286    187988281   macOS APFS (~717 GiB)
    188116287    217413381    29297095    FREE (~112 GiB)
 3  217413382    218023685    610304      Asahi stub (APFS, 2.3 GiB)
 4  218023686    218151685    128000      "EFI - ASAHI" FAT32 ESP, flags boot,esp
 5  218151686    242964997    24813312    LUKS2 -> btrfs "asahi-root" (94.7 GiB)
    242964998    242965550    553         free
 6  242965551    244276259    1310709     RecoveryOSContainer    <-- NEVER TOUCH
```

Why it could not simply be grown: the 112 GiB free block sits on the far side of the stub (p3) and
the ESP (p4). Linux resize tools cannot grow a partition backward across them.
Per Asahi's partitioning cheatsheet, only partitions *between* p1 and the last (recovery)
partition may be created/removed. The stub, ESP and root are one unit (delete all three to uninstall).

Identifiers (these change after a reinstall, but are useful for forensics):

| Part | UUID | PARTUUID |
| --- | --- | --- |
| p4 ESP | `9D41-85A1` | `1df64a61-3178-425e-b8d2-ddaf3ed020ab` |
| p5 LUKS | `eec73af3-9f69-43bc-a114-c1197ac09c62` | `395a6aa2-17e9-48e2-b4b6-97c1354fb6b4` |
| btrfs (in LUKS) | `725346d2-f127-47bc-b464-9dd46155e8d6` | n/a |

Stub `vgid`: `2C26A5E3-88C6-44BC-8AE6-420E98057F2F`.

## 3. Filesystem layout

- LUKS2 -> mapper name `root` -> **btrfs**, label `asahi-root`, 94.64 GiB, ~60 GiB used
- Subvolumes: `@elementary` (/), `@elementary-home` (/home). Mount opts:
  `rw,relatime,x-systemd.growfs,compress=zstd:1,subvol=...`
- (The older Arch `@`/`@home` roots from the original Asahi ALARM install are already gone.)
- `/boot` = p4 FAT32 (`fmask=0022,dmask=0022`)
- Swap: zram 8 GiB (`systemd-zram-generator`, `/etc/sysctl.d/99-mseries-zram.conf`)

`/etc/fstab`:
```
UUID=<btrfs> /     btrfs rw,relatime,x-systemd.growfs,compress=zstd:1,subvol=@elementary      0 0
UUID=<esp>   /boot vfat  rw,relatime,fmask=0022,dmask=0022,codepage=437,iocharset=iso8859-1,shortname=mixed,errors=remount-ro 0 2
UUID=<btrfs> /home btrfs rw,relatime,x-systemd.growfs,compress=zstd:1,subvol=@elementary-home 0 0
```
Kernel cmdline: `root=UUID=<btrfs> rw cryptdevice=UUID=<luks>:root:allow-discards loglevel=3 quiet splash rootflags=subvol=@elementary`

## 4. Boot chain: the part that breaks

`iBoot -> stub (p3) -> m1n1 (/boot/m1n1/boot.bin on ESP) -> U-Boot/EFI -> GRUB -> kernel+initramfs`

- `boot.bin` is the **single point of failure**: if it is bad, no OS boots and GRUB cannot help.
  The ESP is FAT32 and readable from macOS. `/boot/m1n1/RECOVERY.txt` documents the swap
  procedure; the full text is `mseries/fairydust/usb4/RECOVERY.md` in the repo.
- Known-good images kept in `/boot/m1n1/`: `boot.bin.KNOWN-GOOD-usb4-test` (m1n1 v1.6.1 + fixed
  USB4 DTBs, booted fine on 7.1.13-1-2-fairydust-usb4) and `boot.bin.KNOWN-GOOD-fairydust-original`
  (pre-USB4).
- Kernels present: `vmlinuz-linux-asahi` (stock), `-asahi-fairydust` (DP-altmode), and
  `-asahi-fairydust-usb4` (**default**, `7.1.13-1-2-fairydust-usb4-ARCH`). Module trees in
  `/usr/lib/modules/`: `7.1.13-1-1-fairydust-ARCH`, `7.1.13-1-2-fairydust-usb4-ARCH`, and
  `7.1.13-3-2-ARCH` (stock).
- ESP also holds `/boot/asahi/` (stub_info.json, firmware tarball, installer.log),
  `/boot/vendorfw/` (63 MB Apple firmware). Both are regenerated by the Asahi installer.
- initramfs: Arch-style (`cryptdevice=` hook), not dracut/mkinitcpio on elementary; there is no
  `/etc/mkinitcpio*`. Previous images were saved as `*.bak-20261012-170105`.

`/boot/grub/custom.cfg` (recreate after reinstall; substitute real UUIDs):
```
set default=elementary-usb4-test

menuentry 'elementary OS (M-series, fairydust DP-altmode)' --id elementary-fairydust {
    search --no-floppy --fs-uuid --set=root <ESP-UUID>
    linux /vmlinuz-linux-asahi-fairydust root=UUID=<btrfs> rw cryptdevice=UUID=<luks>:root:allow-discards loglevel=3 quiet splash rootflags=subvol=@elementary rw
    initrd /initramfs-linux-asahi-fairydust.img
}
menuentry 'elementary OS (M-series, fairydust + USB4)' --id elementary-usb4-test {
    search --no-floppy --fs-uuid --set=root <ESP-UUID>
    linux /vmlinuz-linux-asahi-fairydust-usb4 root=UUID=<btrfs> rw cryptdevice=UUID=<luks>:root:allow-discards loglevel=3 quiet splash rootflags=subvol=@elementary rw
    initrd /initramfs-linux-asahi-fairydust-usb4.img
}
```

### Kernel status (from `usb4/README.md`)
USB4 hub enumeration works; USB3 tunnel/dock Ethernet works (Realtek r8152 1 Gb/s). Dock HDMI/DP
video is **not** supported (upstream lacks DP tunnelling). **Suspend while a USB4 link is up is
unsafe** (upstream S2RAM SError panic): do not suspend while docked.

## 5. OS / package state

- **elementary OS 9 "Early Access"** (codename `tanit`) on an Ubuntu `resolute` (26.04) base, aarch64
- Kernel running: `7.1.13-1-2-fairydust-usb4-ARCH` (Arch-built kernel, installed as files, not as a dpkg)
- Host name: `elementary-m1`, user `admin` (uid 1000; groups adm cdrom sudo audio dip video plugdev netdev render kvm input)
- Display manager: LightDM with `/etc/systemd/system/lightdm.service.d/` drop-in (waits up to 30 s for
  `/sys/class/drm/card*-eDP-*`; source: `mseries/fairydust/usb4/lightdm-wait-for-drm.conf`)

APT sources (`/etc/apt/sources.list.d/`): ubuntu-ports resolute/resolute-updates, elementary
stable + daily + os-patches PPAs (resolute), Brave, Mozilla, Tailscale, Claude Desktop
(`downloads.claude.ai/claude-desktop/apt`), ChatGPT/Codex (`persistent.oaistatic.com`).

Installed from this project's own packaging: `elementary-minimal`, `elementary-torrential
0.1.0-1~mseries3`, `asahi-audio 3.4-2`, `alsa-ucm-conf-asahi`, `asahi-bless 0.4.3-1`,
`asahi-nvram 0.2.4-1`, `speakersafetyd`, `tailscale`, `podman`, `transmission-daemon`, `just`, `gh`,
`ghostty`, `opencode`, `claude-desktop`, `chatgpt`, `brave-browser`, `firefox`, `chromium-browser`
(snap), `nmap`, `uhubctl`, `stress-ng`, `sysbench`, `fio`, `glmark2-es2-wayland`, `sqlite3`,
`shellcheck`, `golang-go`, `rustc`, clang-21/llvm-21 and the large set of `lib*-dev` build deps
for the Pantheon/Gala/Wingpanel rebuilds. 237 manually-marked packages; to regenerate:
`apt-mark showmanual > manual.txt`.

Snaps: chromium, cups, gnome-46-2404, gtk-common-themes, mesa-2404, core24, core26, snapd, bare.
Flatpaks (appcenter): calculator, camera, capnet-assist, maps, music, screenshot, videos, FileRoller,
Papers, font-viewer; (flathub) Epiphany, **Signal**.
Podman images cached: ruby 3.4/4.0, rust, python 3.11/3.12, node 22, postgres 16, golang 1.25. All pullable.
`/opt`: `OpenCode`, `brave.com`, `nmapui`.

## 6. Custom system config that is NOT a package default

All of this is created by the repo's `mseries/install-*.sh` scripts (28 of them) unless noted.

| Item | Detail |
| --- | --- |
| `mseries-power.service` + `/usr/local/sbin/mseries-power` + `80-mseries-power.rules` | Battery charge limit 80% (start 75), CPU perf-cluster cap 2.4 GHz on battery, `power-saver` on battery / `balanced` on AC. Config `/etc/mseries/power.conf` (absent: defaults apply). `install-power.sh` |
| `mseries-wifi-firmware.service` | Provisions BCM4387 firmware before NetworkManager (`FIRMWARE-WIFI.md`) |
| `omarchy-wifi-resume-fix.service` | Reloads `brcmfmac` if Wi-Fi does not return after resume |
| `nmapui.service` | `/usr/local/bin/nmapui-run`, `/opt/nmapui/current`, env in `/etc/nmapui/nmapui.env` (root-only, **not captured**) |
| `/etc/modprobe.d/asahi-notch.conf`, `zz-pantheon-notch.conf` | Notch handling; `disable-notch-for-pantheon.sh`, `grub.cfg.pre-pantheon-notch` is the pre-change backup |
| `/etc/NetworkManager/conf.d/default-wifi-powersave-on.conf` | Wi-Fi powersave on |
| User units | `mseries-docked-lid`, `netusage` (+ standard Pantheon/pipewire/wireplumber set) |
| Other system services enabled | tailscaled, ufw (**inactive**), openvpn, avahi, cups-browsed, chrony, power-profiles-daemon, touchegg, qemu-kvm, snapd, sysstat |

Patched Pantheon pieces (all patch files are in `mseries/patches/`): files-portal startup
deadlock, gala OSK input-purpose, gala screen corners, keyboard popover, network panel
(null devices, speed, throughput), quick-settings brightness.

User tools in `~/.local/bin`: `mseries-{agent,ask,brief,launcher,troubleshoot,verify}`,
`mlx-omarchy*`, `codexbar{,-linux}`, `coreglass`, `energy-monitor`, `herdr`, `crush`, `signal-desktop`,
`claude`. Most come from `ElementaryOS_MSeries/mseries/*` installers or the Documents repos in section 8.

## 7. Network / identity (names only)

- Interfaces: `wld0` (Wi-Fi), USB dock Ethernet (`enx...`), `tailscale0`
- NetworkManager profiles: 1 wired, 2 Wi-Fi networks (PSKs not recorded; re-enter or restore from backup)
- Tailscale tailnet of `sdolbec1@`: re-join with `sudo tailscale up` (needs interactive login)
- Git identity: `techmore <9263712+techmore@users.noreply.github.com>`; credential helper `gh auth git-credential`;
  `gh` logged in as `techmore`
- SSH: one ed25519 key pair, `known_hosts`
- GnuPG dir exists (`~/.gnupg`): check for keys with `gpg --list-secret-keys` before wiping

## 8. Data inventory

**In git and pushed (nothing to do):** ElementaryOS_MSeries, rupert, TM-NmapUI,
TM-Meraki_Baseline_Reporter, TM-Sonder, WhoPiratesThePirates, mtg-board-layout, shopfloor, swartzit,
tm-daedalus, torrentMore, Emporia-Vue3-Mac-Utility-Monitor, plus upstream clones under
`~/Documents` (CodexBar, coreglass, omarchy-*, mesa-mlx-compute, openbubbles-app, TorrentialFork,
homeboard, elementary panel-power).

**NOT in git (would be lost):**

| Path | Size / note |
| --- | --- |
| `~/code/mario-dash` | not a repo |
| `~/fairydust-usb4/{pkgs,kit,base,work,gala,netspeed,modfix,wp}` | built kernel pkgs (2x ~30 MB), `linux-usb4.tar.gz` 334 MB, `source-trees-before-cleanup.tar.zst` 474 MB. Source is reproducible from the repo |
| `~/Documents/os9-iso-test` | 7.0 GB, test ISOs; reproducible |
| `~/Documents/os9-fairydust-deb-20261013` | 1.8 GB, deb build output; reproducible |
| `~/Documents/os9-corrected-*`, `os9-vm-smoke-*`, `torrential-build-cache` (1 GB), `TorrentialNative`, `mseries-ane-staging` | build outputs and staging |
| `~/Documents/Home_LAN_Inventory_2026-10-13`, `Local Agent`, `Default Project`, `FREE-SPACE-2026-10-13.md` | personal notes/inventory (LAN details, so keep out of public repos) |
| `~/Documents/storage-recovery` (root-owned) | recovery stash |
| `~/Documents/ElementaryOS_MSeries-settings.bundle`, `elementary-os9-*-summary.txt` | exported settings/summaries |
| `~/fairydust-build.sh`, `~/fairydust-driver.sh` | the original Arch-chroot build scripts; superseded by `mseries/fairydust/build-and-install.sh` |
| `~/mlx-backups` | energy-monitor client config + tunnel unit (the client JSON may be a credential) |
| `~/.claude*`, `~/.codex`, `~/.config/Claude`, `~/.opencode`, `~/.codexbar` | tool config and chat history |

## 9. Rebuild runbook (order matters)

1. **From macOS** (the only place the installer can run): delete the three Asahi partitions
   (stub p3, ESP p4, root p5) with `diskutil`, as in the Asahi cheatsheet. Verify numbers with
   `diskutil list` first. Never touch p1 or the last (recovery) partition. Set macOS as the default
   boot OS first. Result: ~209 GiB contiguous free space.
2. Run the Asahi installer in macOS and give the Linux install the whole free block. Pick an Asahi
   Fedora/Arch/minimal base. Our stack was Arch-ALARM -> elementary-os9.
3. Reinstall the elementary OS 9 / Ubuntu `resolute` userland per `mseries/LOCAL-BUILD.md` and
   `mseries/OS9-HANDOFF.md` (mkosi). LUKS2 + btrfs with `@elementary` / `@elementary-home`
   subvolumes (match section 3).
4. Clone and apply the project: `git clone https://github.com/techmore/ElementaryOS_MSeries`, then run the
   `mseries/install-*.sh` scripts (power, audio, brightness, wifi, gala fixes, docked-lid, etc.).
5. Rebuild the kernel: `mseries/fairydust/build-and-install.sh` (+ `usb4/` PKGBUILD and
   `0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch`), then `usb4/build-m1n1.sh` /
   `usb4/install-m1n1.sh`. Keep a known-good `boot.bin.KNOWN-GOOD-*` before swapping m1n1.
6. Recreate `/boot/grub/custom.cfg` (section 4) with the new UUIDs.
7. Secrets: new `ssh-keygen` and add to GitHub (or restore `~/.ssh`); `gh auth login`; `sudo tailscale up`;
   re-add Wi-Fi networks; recreate `/etc/nmapui/nmapui.env`.
8. Re-enable apt sources (section 5), `apt install` from the `apt-mark showmanual` list, reinstall
   flatpaks and snaps.
9. Verify with `mseries/fairydust/verify.sh`, `mseries/POST-BOOT-CHECKS.md` and `mseries-verify`.

### If the machine will not boot after the wipe
Power off, hold the power button -> "Loading startup options" -> macOS -> Terminal. Mount "EFI -
ASAHI" and restore a known-good `m1n1/boot.bin` (see section 4). If the stub was deleted, re-run
the Asahi installer from macOS.
