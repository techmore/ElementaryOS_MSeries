# OS 9 implementation / Claude Code handoff

Updated 2026-10-15. Repository: techmore/ElementaryOS_MSeries.

## Current hardware state — 2026-10-14

The transformed elementary OS 9 desktop is running on a 14-inch M1 Pro through
LightDM and Pantheon. The display is set to scale 1.5; Gala edge tiling and
Super+Left/Right window tiling are enabled. The centered clock is visible.

The experimental `7.1.13-elementary-fairydust-usb4` kernel boots from a
non-default GRUB entry. With the matching J314s device tree and newer pinned
m1n1, a Dell dock's hub, mouse, keyboard, and USB audio work. After the owner
installed newer m1n1 and rebooted, they reported that mouse and dock Ethernet
appear to work; this has not been independently rechecked. Dock video remains
unsupported upstream; avoid suspend with a USB4 link connected. Details and
recovery guidance: [`fairydust/usb4/CUTOVER.md`](fairydust/usb4/CUTOVER.md).

The 0003 Apple Video Decoder allocation fix still needs a long-uptime decode
check on this kernel. The one-command installer has not been run on a wiped Mac,
and the factory ISO remains unverified on Apple hardware. Do not describe the
desktop result as validation of either installation path.

Next: run the long-uptime decode check, complete the encrypted backup using the
owner's normal backup procedure, and keep the installer and factory-image
qualification work separate from the already-running transformed desktop.

## USB4 DP-tunnel experiment 1 — 2026-10-15

Owner direction: **make the dock carry video** (they will not plug a display
into the Mac's own ports), so the RE path is active. Reverse-engineered the
missing data path and wrote it up in
[`fairydust/usb4/DP-TUNNEL-RE.md`](fairydust/usb4/DP-TUNNEL-RE.md). Key finding:
the display crossbar driver already supports routing a controller stream to the
ACIO DP IN adapters (`dpin0`/`dpin1` ⇒ "USB4 Tunnel #0/#1"), and on this machine
`atcphy1_xbar` (`b0304c000`, the dock's port) currently routes `dispext1,0` to
`dpphy` instead. The only missing pieces are (a) the crossbar mux selection and
(b) the trigger that makes the DCP drive the DP IN adapter.

Landed (experiment 1, off by default):
- `fairydust/usb4/0002-experimental-dp-tunnel.patch` — device tree routing of
  `dcpext1` to `<&atcphy1_xbar 1>` (dpin0), a `thunderbolt.allow_dp_tunnel`
  module parameter that un-suppresses Apple DP tunnels, and a per-connector
  `force_link` debugfs to drive the DPTX endpoint by hand.
- `fairydust/usb4/test-dp-tunnel.sh` — read-only evidence collector + verdict.
- `fairydust/debian/build.sh` builds the experimental kernel only when
  `FAIRYDUST_DP_TUNNEL=1`, as release `7.1.13-elementary-fairydust-usb4-dptunnel`
  / package `7.1.13+elementary.usb4-dp1` (distinct, so it cannot be confused with
  the working `-usb4` kernel). `.github/workflows/daily-9.0.yml` gained a
  `fairydust_tunnel` dispatch input.
- `fairydust/usb4/install-ci-kernel.sh` can now select a variant
  (`KERNEL_SUFFIX`/`KERNEL_ENTRY_ID`/`KERNEL_EXTRA_CMDLINE`; defaults unchanged)
  and swap just the `j314s` DTB inside the existing boot image (`--swap-dtb`), so
  the experimental kernel installs side by side as its own GRUB entry. Nothing
  was installed or booted.
- Cleared the proxyclient dependency blocker without touching the system:
  `fairydust/usb4/m1n1-trace-deps.sh` vendors `construct==2.10.70` and
  `pyserial==3.5` into `~/.local/share/m1n1-proxyclient/site` (no pip/apt/sudo).
  Verified `proxyclient/tools/run_guest.py --help` and the tracer imports work.
  `proxyclient/hv/` already ships `trace_dcp.py` (AFK/ASC endpoint tracer) and
  `trace_dptx.py`, so the macOS trace is now a tooling-free step.
- Validated the `--swap-dtb` install step without root: against the live
  `/boot/m1n1/boot.bin`, `swap-dtb.py` finds the 110-tree DTB run, matches
  exactly one `apple,j314s` tree (#25, 93189 bytes) and an identity swap
  reproduces the input byte for byte (sha256 `5cbc5f30…`). `sudo` here wants a
  password and there is no TTY for the agent, so the dry run and `--apply` must
  be launched from a real terminal.
- CI run `38776005043` built the experiment-1 kernel (25m17s; the ISO job in the
  same run failed and is unrelated) from `083f3a19`. Verified without root: the
  `.deb` checksums pass, release is `7.1.13-elementary-fairydust-usb4-dptunnel`,
  the DTB is at the path `--swap-dtb` expects, the compiled DTB has
  `dcp@28cc00000` (dcpext1) `mux-controls = (153,1)` (dpin0) vs `(153,0)`
  (dpphy) in the working boot.bin with the HDMI node unchanged, and
  `appledrm.ko`/`thunderbolt.ko` carry `force_link` and the `allow_dp_tunnel`
  module parameter respectively. Nothing installed or booted.

Verified: patch applies cleanly to the prepared source, hashes match, `build.sh`
syntax and the workflow YAML parse.

**Installed 2026-10-15 and tested on hardware — no video yet.** The kernel was
installed side by side as its own non-default GRUB entry (`elementary OS
(M-series, fairydust-usb4-dptunnel test)`, via `--swap-dtb`), with the working
entry and `GRUB_DEFAULT` untouched. Independent post-install check: the installed
`boot.bin` differs from its pre-install backup by exactly one byte
(`mux-controls` for `dcp@28cc00000`, arg 0 `dpphy` → arg 1 `dpin0`), the HDMI
route and `mux-index` are unchanged, and the backup still hashes to the original
`5cbc5f30…`. Because m1n1 consumes `boot.bin` before GRUB, that tree is shared by
every entry; the original is kept at
`/boot/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-20261015-140455` and
`/root/usb4-backup-20261015-140455/boot.bin`.

On the booted test (2026-10-15 14:13-15:32) the tree was armed (`mux-controls`
arg 1) and the crossbar logged the new route (`Switched dpin0 to dispext1,0`),
but dock video still failed — one step later than before. The tunnel now reaches
path activation: host DP IN `0:5` pairs with a dock DP OUT adapter, bandwidth is
allocated in allocation mode (22500 Mb/s), and the Video, AUX TX and AUX RX paths
all report `activation complete` (4x over the session). Every attempt then dies
reading the sink's DPCD: `DPRX read timeout` x25533 (21479 on `1:13`, 4054 on
`1:14`), with no link rate, no training, no video. Whole-journal check: this is
the only boot that has ever reached path activation. `force_link` was never
exercised, and no boot has yet A/B'd the old `dpphy` route against the new one, so
the crossbar change's role is not isolated — the tunnel-side steps are
host-router <-> dock-router and do not involve the crossbar at all. Both are the
next cheapest steps; `fairydust/usb4/DP-TUNNEL-RE.md` has the log excerpt.

Related: suspend with the dock attached remains unsafe — the next boot hung at
`PM: suspend entry (s2idle)` and needed a power-cycle. More importantly, the test
boot's unplug wedged the Type-C port (deadlock in `apple_nhi_remove` vs the
`tps6598x` mutex, triggered by a DPRX read in flight); that is diagnosed and
documented on the `re/usb4-exp2` branch, which also carries experiment 2
(`dprx_bypass`) and its install. The two branches have diverged in this file and
in `DP-TUNNEL-RE.md`; consolidating them is a git-ownership decision, not one to
make silently here.

## Monitor / dock-video decision — 2026-10-15

Checked the current upstream state for external-display video and recorded a
decision in [`fairydust/usb4/DOCK-VIDEO-DECISION.md`](fairydust/usb4/DOCK-VIDEO-DECISION.md):
use the Mac's **built-in HDMI port** (supported; DCP firmware 13.5 confirmed
locally) as the everyday external display, or a **direct USB-C→HDMI/DP adapter
on the front-left port** for the DP Alt Mode route. **Dock video (HDMI or DP on
the WD22TB4) is not targeted** — it needs USB4 DisplayPort tunnelling, which is
unimplemented; dock HDMI and dock DP are the same problem. The `fairydust` HEAD
is `ce9f2eba` (2026-09-08), the revision this repo already builds, so there is
nothing new to rebuild. Added read-only helper `mseries/check-display-paths.sh`
(DCP firmware, support modules, DRM connectors, per-path verdict) and updated the
ROADMAP open-problem row. No kernel, bootloader or audio change was made.

## New desktop bugs reported — 2026-10-13

Added three separate owner-reported findings to
[`BUG-FIX-ROADMAP.md`](BUG-FIX-ROADMAP.md): inconsistent app-window rounding
versus the Mac display, reds/blues that still feel too harsh, and network
usage/speed indicators that do not always recover around Ethernet
suspend/resume or reboot. These need visual review or reproduction before
implementation; no desktop code was changed for these reports.

## Additional owner-reported bugs — 2026-10-13

Added backlog entries for the non-native signal-strength dropdown, an
unspecified Tasks bug, an unspecified Energy Monitor bug, Touch ID for passkey
user verification, and remembering successful authentication for a defined
period. Also recorded the requested pastel red-orange cue near network-link
saturation. The app-specific reports need reproduction details; Touch ID
support remains unverified, and the remembered-auth duration/security policy
still needs definition. See [`BUG-FIX-ROADMAP.md`](BUG-FIX-ROADMAP.md).

## Latest test result — 2026-10-13

Downloaded CI run 38479577898's ARM64 installer artifact and independently
matched its ISO SHA-256 against the included `INSTALLER-SHA256SUMS`. Booted the
ISO with QEMU 10.2.1/KVM and AAVMF to the graphical installer language screen;
serial output reached the OS 9 login prompt. The test used read-only ISO media
and attached no writable guest or host disk. Evidence and test boundary are in
[`VM-SMOKE-TEST.md`](VM-SMOKE-TEST.md); screenshot:
[`os9-ci-38479577898-installer.png`](../docs/images/os9-ci-38479577898-installer.png).

This ISO boot uses the generic live kernel, so it does not test the Fairydust
kernel or the Apple m1n1 hardware path. The Fairydust kernel has a separate
direct QEMU userspace-handoff smoke test; it now passes under QEMU TCG when
KVM is unavailable. See
[`fairydust/debian/TCG-SMOKE-TEST.md`](fairydust/debian/TCG-SMOKE-TEST.md).
The owner-approved model and mkosi caches and completed kernel compiler
objects were cleaned after validation; the tested kernel `.deb`, source and
build records remain. Local preflight now finds 37.6 GiB free, 22.4 GiB below
its conservative 60 GiB guard, so no build was started. Next: boot a disposable installed image with
the Fairydust kernel/initramfs and validate the Apple DTB selection path; Mac
hardware boot remains unverified. Do not write the host ESP or change the
running host kernel.

## CodexBar notch placement — 2026-10-13

The owner asked for CodexBar to sit left of the MacBook notch. Wingpanel 8.0.4
normally assigns non-special indicators to its right group, while the date
occupies the center. Added a source patch that places only `codexbar` in the
left group immediately after the application launcher; other indicators and
the clock stay in their existing groups. Its installer also reapplies the
existing optional right-clock ordering. The pinned source built and its Meson
tests passed, then the patched binary was installed. The original binary is
backed up at `/usr/local/lib/mseries/io.elementary.wingpanel.pre-codexbar-left`;
`bash mseries/install-wingpanel-codexbar-left.sh --uninstall` restores it.
Log out and back in to load the panel placement.

## Keyboard brightness slider audit correction — 2026-10-14

The Pantheon Quick Settings patch includes a **Keyboard Brightness** slider
(`mseries/quick-settings/KeyboardBrightness.vala`). The manual post-install
`quick` stage and the transform's firstboot `quick` module both install it; the
Apple Silicon overlay now builds and preserves the plugin against the matching
Quick Settings package version. This is separate from the ambient keyboard
backlight helper. Added an explicit live UI check to `POST-BOOT-CHECKS.md` and
tracked the image build in `ROADMAP.md`. The new image path has not yet been
built or booted; current panel visibility and slider operation still need an
on-device check.

Factory-image follow-up: the Apple Silicon overlay includes the matching
Wingpanel network and Quick Settings packages while compiling the pinned
plugins, then retains only the built plugins. The Quick Settings build adds the
keyboard slider; the network build adds speed readouts. Both version mismatches
now stop the image build instead of silently omitting a requested feature. This
path has only received code review; an ARM64 image build and Mac boot remain
pending.

## Source verified

The official public elementary/os repository was cloned to
/tmp/elementary-os9-public-source. Its main HEAD is
7024fd04646a6a8565bf6805989b59fd72de928c, already merged into this port.
OS 9 is developed on main, not a 9.0 branch. No sponsor-only source or
Early Access binary was used. Component source/licensing still needs
per-component review before importing new patches.

## First implementation

- Replaced the fork's scheduled release workflow (which needed upstream
  signing/R2 secrets) with a manual arm64 build. It uploads an experimental
  ISO, checksum, commit record, and build logs to GitHub Actions artifacts.
  Failed builds retain logs. No official release is published.
- Fixed an image-layer dependency gap: apple-silicon/mkosi.finalize deletes
  package payloads; ExtraTrees cannot resolve apt dependencies. The liveiso
  and sysupdate arm64 configs now explicitly install pipewire-pulse,
  pipewire-alsa, rtkit, and python3-gi.
- Added test-image-wiring.py to catch lost runtime packages in either consumer.
- Fixed finalize deleting the brightness helper and its Pantheon autostart
  entry. A temporary-image cleanup test verifies all shipped helper files
  survive while package payloads are pruned.
- Completed the pending audit/status-page edits and specific bug-fix roadmap.

## One-command installer (2026-10-14)

- Added `bin/elementary-mac-setup`, a port of omarchy-mac-setup: state machine
  boot-layout -> encrypt -> elementary, resuming via a systemd unit. Steps 1-2
  run omarchy-mac's `omarchy-system-boot-to-esp` / `-btrfs-migrate` (fetched at
  run time); step 3 runs `transform/elementary-grow.sh --apply` + `--finalize`,
  makes `@elementary` the default GRUB entry (`--keep-default` skips), and adds
  LightDM autologin when encrypted.
- Added `mseries/install-unlock-screen.sh`: elementary Plymouth theme on the
  LUKS passphrase screen (plymouth + keymap hooks via a last-sorted mkinitcpio
  drop-in, backups, image verification with rollback).
- `elementary-grow.sh` now honours `ELEMENTARY_HOSTNAME`, `ELEMENTARY_PASSWORD_HASH`
  and adds `quiet splash` when the elementary theme is configured.
- Verified: `mseries/test-elementary-mac-setup.sh` (state machine, validators,
  config round-trip) and shellcheck. NOT verified: any step on hardware, the
  Plymouth hook order on a real Asahi Alarm initramfs, LightDM autologin.
  Test on a spare/backed-up machine first.

### Installer audit fixes (2026-10-14)

- Upstream Asahi tools are pinned to an omarchy-mac commit (`ELEMENTARY_TOOLS_REF`), not the moving `quattro` branch; they run as root against the partition table.
- GRUB default is selected by `--id elementary-mseries`, not by title (the title carries the kernel version and would silently fall back to Arch after a kernel update).
- A `grown` marker keeps a finished `@elementary` build when a later step fails on resume.
- Unlock-screen script: failure now removes its mkinitcpio drop-in, sizes the ESP check from the real image sizes, matches only the exact `udev` hook, and detects the Inter font exactly.
- Still unverified: whether the initramfs plymouth hook bundles Inter (it may fall back to the default sans); `pacman -Sy` partial-upgrade risk for installing plymouth, same as upstream.

### Audit of omarchy-system-btrfs-migrate @ ba546a6 (full read, 2026-10-14)

Upstream mechanics confirmed: hook staged in the initramfs, worker addressed by PARTUUID, `cryptsetup reencrypt` with 64 MiB fs shrink + 32 MiB header, resumable, `@log`/`@fresh` added, finish service rebuilds initramfs + grub.cfg and removes the hook; refuses without a separate /boot or with systemd hooks. No recovery key exists; `allow-discards` is on (TRIM leaks usage patterns - upstream choice).

Defects found in how we use it, fixed:
- The boot that finishes the encryption still runs on the OLD kernel cmdline (no `cryptdevice=`). Deriving the elementary GRUB entry from it would have produced an entry that cannot unlock. Setup now reboots once before step 3 (`ensure_unlock_cmdline`), and `elementary-grow.sh` refuses to build an encrypted entry without `cryptdevice=`.
- The passphrase is chosen in the initramfs under whatever keymap it has loaded; without the `keymap` hook a non-US passphrase would be created as US keystrokes and rejected later. Setup adds `keymap`/`consolefont` hooks (drop-in) before the encryption boot. `consolefont` is also what makes the large console font apply at the prompt.
- The plan screen now warns that there is no recovery key.

Unverified: all of it on hardware; the rebuilt initramfs vs the staged worker hook ordering with our drop-ins.

### Audit of boot-to-esp and elementary-grow.sh (2026-10-14)

boot-to-esp (upstream, read in full): copies /boot onto the vfat ESP, remounts it at /boot, rewrites fstab, reinstalls GRUB `--removable`, rebuilds the initramfs; keeps /boot.old; refuses ISO shared-ESP layouts. No defects found; note the ESP is small, which is why install-unlock-screen.sh sizes its backups.

Fixed in elementary-grow.sh / setup:
- Kernel updates on the Arch side replace `vmlinuz-linux-asahi` in place, so the elementary entry would boot a newer kernel than the one whose modules were grafted (no Wi-Fi/display). Setup installs a pacman hook (`90-elementary-sync-kernel.hook`) running `--sync-kernel`, and the graft now copies every module tree on the host, always re-copying (custom kernels keep their version string).
- The M-series layer (Wi-Fi units, notch modprobe) was `curl`ed from raw `main` at build time, ignoring `--ref` and unauthenticated; it is now copied from the checkout.
- `ELEMENTARY_HOSTNAME` is validated before it reaches the root chroot script.
- Timezone is copied from the host (the account is created with useradd, which skips first-run setup).

Open: Signal's apt key is fetched at build time without a pinned fingerprint (non-fatal, but a supply-chain choice); `--no-encrypt` on stock Asahi Alarm leaves the ESP at `/boot/efi`, so the new root gets no ESP mount; locale and XKB layout are not carried over.

### Audit of the rest of elementary-grow.sh (2026-10-14)

Confirmed against this machine's real `/boot/grub/grub.cfg`:
- The `40_elementary-grow` file had a comment line above `exec tail -n +3 $0`, so the exec line itself was copied into grub.cfg (GRUB: unknown command). Now `exec` is line 2.
- The kernel/initramfs pair was guessed by modification time (Arch files carry no version): the entry used stock `vmlinuz-linux-asahi` while the machine runs `fairydust-usb4`, so modules did not match. Now derived from `BOOT_IMAGE` (`vmlinuz-X` + `initramfs-X.img`); the fallback image is never chosen.
- Duplicate `rw` on the kernel line removed.

Also fixed: `--rollback` no longer deletes `@elementary-home` when it contains files (`ELEMENTARY_DELETE_HOME=1` to force); the base-tarball checksum match is exact instead of a substring; `--add-user` only uses groups that exist in the root (useradd aborts on an unknown one).

Open: the Ubuntu base tarball is trusted via HTTPS only (SHA256SUMS.gpg is not verified; apt then verifies packages against keys in that tarball); `--finish-root` ignores a failed chroot because of `set -e`; `/tmp` build logs are world-readable; `--status` mounts the btrfs top level read-write.

### Kernel-flow audit (2026-10-14) — see mseries/KERNEL-FLOW.md

Found on the running machine: elementary's root has `initramfs-tools` (`update_initramfs=yes`), `grub-efi-arm64`, `grub2-common` and `/usr/sbin/update-grub`, with the shared ESP mounted at `/boot` (157 MB free). An upgrade of any package with an initramfs hook would write unused `initrd.img-*` onto the ESP, and a grub package upgrade could run `update-grub` and overwrite the Arch-generated `grub.cfg`.
Added `mseries/install-boot-isolation.sh` (update_initramfs=no, apt pin against Ubuntu kernels, dpkg-diverted no-op stubs for update-grub/grub-install/grub-mkconfig), run by the grow script before and after the desktop install and available as `elementary-grow.sh --isolate-boot`. **Not yet applied to the running machine**: run `sudo mseries/install-boot-isolation.sh`.
Open: custom kernel flavours (fairydust*) are only synced by the pacman hook if pacman installs them as `linux-asahi*`/`linux-aarch64*`.

### Installer flow re-audit (2026-10-14)

- Prerequisites used `pacman -Sy <pkgs>` (a partial upgrade: on a months-old Asahi Alarm image git/curl can end up linked against libraries that were not upgraded). It is now `pacman -Syu` once, up front. If that replaced the running kernel (its `/usr/lib/modules/<running>` is gone, so vfat/btrfs/dm-crypt cannot be loaded), the setup reboots onto the new kernel before doing anything else. Later installs use plain `-S` (databases are already current).
- `--no-encrypt` on stock Asahi Alarm (/boot on the btrfs root, kernel under the `@` subvolume): the GRUB entry used `/boot/vmlinuz-...`, which GRUB cannot find because it reads the top level of the filesystem. Now uses `grub-mkrelpath` (`/@/boot/...`). Untested.

### Hardware-layer audit (2026-10-14)

- **Initramfs fixes we were inheriting from Omarchy Mac and no longer get.** `docs`/TRANSFORM-DESIGN assumed the host initramfs already early-loads the HID drivers because Omarchy's install did it. This installer never runs Omarchy's install, so a fresh machine had: no `hid_apple`/`hid_magicmouse` early-load (sometimes-dead trackpad), no display crossbar, and no `keyboard`/`kms` hooks for the graphical unlock prompt. Added `mseries/boot/mkinitcpio-snippet` plus three snippets (`initramfs-console`, `initramfs-splash`, `initramfs-hardware`), applied by the setup (before the encryption boot and, for `--no-encrypt`, in step 3) and by `install-unlock-screen.sh`. Blocks are written into `/etc/mkinitcpio.conf` itself, not `mkinitcpio.conf.d/`, because mkinitcpio ignores the drop-in directory for presets that set `ALL_config` (the fairydust ones) — the drop-in approach used earlier in this session would have silently not applied there. The test script now covers the hook ordering.
- `lspci -nn | grep -q` under `pipefail` fails intermittently (grep exits first, lspci takes SIGPIPE): fixed in `elementary-grow.sh` `detect_chip` and `mseries-wifi-firmware`; `mseries-wifi-resume-fix` `wifi_down` likewise. Wi-Fi firmware handoff now also looks in `/boot/mseries-firmware` (ESP at `/boot`).
- The grown root now also gets the brightness-key helper and its autostart entry (previously only the image factory shipped them).
- Not reviewed: the many `mseries/install-*.sh` scripts and the launcher (user-run, image-specific).

### User-script audit (2026-10-14)

Read: install-system-tuning/audio-stack/power/network-throughput/docked-lid/log-fixes/brightness-bridge/files-portal-fix/native-firefox/signal(+integration)/keyboard-backlight, power/mseries-power, docked-lid, apply-desktop-settings.
Fixed:
- `install-signal-integration.sh` used `rg` (ripgrep), which elementary does not ship: with it missing, `! rg -q` is true, so a re-run never refreshed the alias desktop files. Now `grep`.
- `install-system-tuning.sh` disabled zswap only at runtime (sysfs write); it came back after every boot, double-compressing on top of zram. Now also a tmpfiles.d rule (removed by `--revert`).
- `install-brightness-bridge.sh --uninstall` aborted under `set -e` if the service was not running.
- `mseries-docked-lid`: if the service died or restarted while the lid was closed, the panel stayed at brightness 0 after the lid opened (saved value lived only in memory). It is now persisted in `$XDG_RUNTIME_DIR` and restored on start; `--status` is read-only.
- The Signal apt key in the grown root is now checked against Signal's published fingerprint (`DBA36B51…FB06`, verified against the live key) instead of being trusted blindly; `speakersafetyd` (the safe default of install-audio-stack.sh) is installed in the build, non-fatal. TRANSFORM-DESIGN's claim that it has no Ubuntu package is out of date.
Noted, unchanged: `apply-desktop-settings.py` is the owner's personal shortcut layout (Command↔Ctrl swap etc.) and must not be part of the installer; install-audio-stack's volume restore sets every sink, not just the speakers, to the remembered volume (errs toward quiet); `mseries-power` sources `/etc/mseries/power.conf` as root (file is root-owned).

### Desktop-patch scripts audit (2026-10-14)

Read the Gala/Wingpanel/Quick Settings/indicator/Files-portal/Touchegg/CodexBar/theme scripts. They replace files owned by apt packages with patched builds. Findings, fixed:
- Each kept a single `*.original` backup and `--uninstall` copied it back unconditionally. After a package upgrade (which already overwrote the patched file) that restored the PREVIOUS version's binary over the new package. New `mseries/lib-backup.sh` records the package version with the backup; a restore with a different installed version runs `apt-get install --reinstall <pkg>` instead. Legacy backups without a version file are kept and not trusted. Tested with stubbed dpkg/sudo/apt. Applied to sound, keyboard, quick-settings, gala-daemon, network-throughput, wingpanel-clock-position and the Files portal fix.
- Four scripts guarded the post-build `ldd | rg -q 'not found'` check with ripgrep, which elementary does not ship: with `rg` missing the pipeline fails, the check never trips, and a build with unresolved libraries would be installed over the system file. Now `grep`. (`rg` no longer appears in any script.)
- `install-troubleshooter-wingpanel.sh --uninstall` would `rm -f /libmseries-troubleshooter.so` if `pkg-config` returned nothing; and aborted when the service was not running.
- `disable-notch-for-pantheon.sh` edits the generated `grub.cfg` in place (lost at the next `grub-mkconfig`); marked as a legacy hotfix — `elementary-grow.sh` already writes `appledrm.show_notch=0` into its entry.
Reviewed, no change: `install-gala-screen-corners.sh` (private prefix, per-user drop-in, automatic fallback to stock Gala - good design), CodexBar (sha256 comes from the same release origin, so it guards corruption not tampering; it also runs the downloaded `install.py`), Touchegg (tag, not a commit, pinned).
Not read: the Vala/meson sources under `mseries/clockright`, `codexbar-wingpanel`, `signal-wingpanel`, `troubleshooter-wingpanel`, the `mseries/patches/*.patch` files, `mseries/local-ai/*`, `mseries/brightness`, `mseries/keyboard-backlight`, `mseries/launcher*`, the mkosi image configs and workflows.

### Workflows and Python helpers audit (2026-10-14)

- `stable-9.0.yml` still ran upstream's release pipeline monthly (cron `0 0 1 * *`), and `proposed-9.0.yml` ran it for every non-draft pull request, both with `secrets: inherit` into a job that needs upstream's signing key and R2 credentials. On this fork that is an hour of runner time per PR and a certain failure at the upload (and, if someone ever added those secrets here, a push into upstream-named buckets). The schedule is removed and both jobs are now guarded with `github.repository == 'elementary/os'`, so they stay mergeable from upstream but never run here. `daily-9.0.yml` (manual, no secrets, hash-pinned kernel archive) is the fork's real build and is fine.
- `validate-mseries.yml` now also syntax-checks every `mseries/install-*.sh`, the new installer scripts and the snippet tool, runs `shellcheck -S warning` over them, and runs `mseries/test-elementary-mac-setup.sh`. To keep that gate green, four `ls | grep` patterns in `elementary-grow.sh` (SC2010) were replaced.
- `keyboard-backlight/backlight.py` detected the closed lid through `/proc/acpi/button/lid`, which does not exist on Apple Silicon (checked on this machine), so the check was always false. It now asks logind for `LidClosed` (checked live).
- Reviewed, no change: `mseries-launcher.py`, `brightness/shell-bridge.py`, `local-ai/crash-watch.py` and the first half of `troubleshoot.py` (loopback-only endpoint, no redirects, proxies off, log redaction, no shell), `install-agent.sh` (hash-pinned Crush release). `local-ai/stage-ane.sh` hard-codes `/home/techmore/...` and one kernel version by design (it refuses on any other kernel) — owner-only tooling.
- Still unread: `local-ai/troubleshoot.py` after line 200, `ask.py`, `brief.py`, `verify.py`, `troubleshooter-ui.py`, `repair-panel.py`, the Vala/meson sources for the custom Wingpanel indicators, `mseries/patches/*.patch`, `mseries/fairydust/*`, and the mkosi image configs.
- `build-release.yml` (upstream) interpolates `${{ secrets.SYSUPDATE_GPG_PASS }}` straight into a shell command; upstream's choice, not run here.

### Image-factory configs, patches and kernel build audit (2026-10-14)

Method: diffed the whole tree against a fresh clone of `elementary/os` main, so every fork deviation was read, not just the files named M-series. Deviations: the three workflows (above), `assemble-iso.sh` (relative paths, per-arch apt-cdrom structure, label helper — good), `mkosi.conf` (`WithNetwork=yes`), `arch.arm64.conf` (adds the apple-silicon image), `.gitignore`, the `fairydust` profiles, the arm64 `conf.d` overlays, and the base sysusers/tmpfiles/postinst.
- `mkosi.conf` `WithNetwork=yes` opens the network for every build script in every image, not just `build-network-indicator` (which fetches a pinned commit). Needed today; revisit if more build scripts are added.
- Base image: upstream pins `messagebus` to gid/uid 987 so the setuid `dbus-daemon-launch-helper` group and persistent `/var` ownership stay stable across sysupdate images. The fork drops the pin and chowns to the name `messagebus` after `systemd-sysusers`, relying on the dbus package's own sysusers file. It builds only if that file exists in resolute (the build fails loudly otherwise) but the numeric id may now differ between image builds. Unverified; check on the first successful image.
- `apple-silicon/mkosi.finalize` prunes with a path whitelist under `find -xdev -mindepth 1 -depth ... -delete`; `BUILDROOT` is `realpath`ed with `set -u`, so an unset variable aborts rather than widening the delete. Fine.
- `mseries/patches/*.patch` (small ones read in full): minimal and null-safe. `keyboard-popover-active.patch` mirrors the checked state only on change (a layout button constructed already active would not be shown checked).
- `ChargeLimit.vala` + `org.techmore.mseries.power.policy`: pkexec by path, `auth_admin`, argument allow-listed to `80|100` in `mseries-power` — a sound privilege boundary. The toggle hides itself unless `/usr/local/sbin/mseries-power` exists, which the grown root does not install by default (install-power.sh does).
- `fairydust/debian/build.sh`: source archive, kernel config and patch all sha256-checked, fresh work dir enforced, free-space watchdog, deterministic build timestamp. Fine.
- Still unread: the large patches (`gala-screen-corners`, `network-*`, `sound-icon-initialization`), the custom indicator sources, `fairydust/usb4/*` and `host/*`, the rest of `local-ai`.

### Enhancements layer (2026-10-14) — the "automagic" half of the installer

Goal: the one-command install should give a finished elementary OS experience, not just a bootable desktop. Added:
- `mseries/enhance.sh [--root DIR] [--only|--skip ...]`: writes the enhancement layer into a root without a session (build time via `elementary-grow.sh`, or on a live system): `tuning` (zram, zswap off, ModemManager off, AppCenter daemon hidden for new users), `power` (mseries-power, polkit action, unit, udev rule), `session` (docked-lid as a global user unit; brightness bridge and keyboard backlight via autostart), `theme` (skel gtk css), `payload` (scripts/patches for the first-boot job), `firstboot` (service). Idempotent, testable against a temp dir (`test-elementary-mac-setup.sh` does).
- `mseries/enhance-firstboot.sh` (installed as `/usr/sbin/elementary-mac-enhance`): one-shot, network-gated, per-module state and attempt counter (3 tries), `--status/--retry/--with`. Modules: Brave (apt repo, all three Brave release key fingerprints pinned), Touchegg, and the version-gated patched components (network, quick-settings, sound, keyboard, Files portal, Gala OSK). A module whose version gate fails is recorded as skipped, not forced.
- `mseries/install-brave.sh` (the owner prefers Brave); Firefox stays available as an opt-in module.
- Setup flag `--no-enhancements` (stored in the resume config) → `ELEMENTARY_ENHANCE=0` to the grow script. The grow script also installs `systemd-zram-generator` (non-fatal).
Deliberately NOT automatic: Command/Ctrl swap + launcher (opinionated), rounded corners (replaces the compositor; has its own fallback), Asahi speaker DSP (needs the LV2 build and the volume-restore logic of a live session; 2026-10-12 incident).
Unverified: every first-boot module on hardware (build dependency lists for sound/keyboard/files/osk are best guesses and will show up as `failed` with the meson error in the log if a package name is wrong); the autostart-triggered brightness/backlight services on a grown root.
Open parity items vs omarchy-mac (see PORT-MAP.md): audio watchdog, headset-mic map, `hid_apple fnmode` default, AVD video decode.

### Completion pass (2026-10-14)

Read the rest: all of `local-ai` (troubleshoot, ask, verify, repair-panel, upstream-watch, configure-prefill, crash-watch; only `brief.py` and `troubleshooter-ui.py` were skimmed by pattern search), the Vala indicators (`clockright`, `codexbar-wingpanel`, `signal-wingpanel`, `troubleshooter-wingpanel`: they only spawn fixed binaries in the user's own `~/.local/bin`), the large patches (read-only `/proc`/`/sys` access, a per-user key file; the Gala corner radius is parsed defensively), `fairydust/usb4` + `host` (owner-only: hard-coded `/home/techmore`, `/mnt/fdbuild`; `install-m1n1.sh` refuses to run unless the recovery copies exist), `backup/mseries-backup.sh`. A repository-wide grep found no `shell=True`, `eval`, insecure TLS flags or world-writable modes.
Findings: `netspeed/` is a stale snapshot (its troubleshooter files differ from `local-ai/` by 60-860 diff lines and its network patch overlaps the installer's) - marked in its README. `clockright` ignored a change of "show seconds" while running (timer rate fixed at construction) - fixed. The fairydust presets set `ALL_config` (confirmed in `install-stage1.sh`), which independently confirms that mkinitcpio drop-ins would be ignored for them and the snippet-in-`mkinitcpio.conf` approach is right.
Ported from omarchy-mac-pkgs: WirePlumber `asahi-audio-no-suspend` and `asahi-headset-mic` rules and a Pantheon audio watchdog (`mseries/audio/`, enabled by the `audio` module). Still open: the headset-mic mapper, the `hid_apple fnmode` default (running value 1, upstream hands it to the kernel default 3 - left alone, owner preference), Apple video decode (kernel + firmware + VA-API bridge).
Verified against this machine's real package set (it is a resolute + elementary PPA root): every first-boot build dependency in `enhance-firstboot.sh` exists (`apt-cache show`), and the installed versions satisfy every patch's gate (gala 8.6.2, wingpanel 8.0.4, panel.network 8.0.1, quick-settings 1.4.0, panel.sound 8.0.3, panel.keyboard 2.4.2). That check caught a bug of mine: the Files portal belongs to the package `pantheon-files`, not `io.elementary.files`, so the new backup helper would have aborted that script; fixed, and the script now has a version gate (7.3.3.x) like the others.
Everything else remains unverified on hardware.

### Hardware checks on the M1 Pro itself (2026-10-14) and the last unread files

This repository is being worked on from a running M1 Pro (elementary on the fairydust-usb4 kernel), so several pieces could be exercised for real, read-only:
- **Found a real bug in my audio watchdog**: `pactl` is not installed here (it ships in `pulseaudio-utils`), so the probe failed every time and the watchdog would have "restarted" healthy audio until its budget ran out. The probe now uses `pactl` if present, else `wpctl status` (WirePlumber's own tool, needs the WirePlumber main thread alive), and never reports a failure when neither exists. Four unit tests cover it; the live probe on this machine now reports healthy.
- Confirmed on hardware: logind exposes `LockedHint` for the session (`no` while unlocked) and the user's Display session resolves without `XDG_SESSION_ID`, so the watchdog's lock check has real data; `docked-lid --status` sees the attached dock; `keyboard-backlight --once` reads the ALS (458 lx); `mseries-power status` shows the 80% limit; zram swap is active and ModemManager is disabled; `apple-silicon` device-tree gate passes.
- Read in full now: `local-ai/brief.py` (cosmetic fix: "about None minutes" when the cache age is unknown) and `local-ai/troubleshooter-ui.py` (the `MSeries-Progress:` protocol matches `troubleshoot.py`; a timeout kill skips model release, minor).
- **Apple video decode**: the kernel side is already here (`apple_avd` loaded, `CONFIG_VIDEO_APPLE_AVD=m`, `/dev/video0`, `avd-fw-*` firmware in `/lib/firmware/apple`). Only the userspace VA-API bridge (omarchy's `libva-v4l2_request-avd`) is missing and has no Ubuntu package. Not a packaging job for this installer; tracked as a gap.
- **Headset-mic mapper**: deliberately not ported (Quickshell-specific rationale, see PORT-MAP.md).
What is still genuinely unverified: a full run of `elementary-mac-setup` (boot layout, encryption, unlock screen, auto-login, first-boot modules) on a fresh Asahi Alarm install. That needs a spare or backed-up Mac and cannot be done from this session.

### Apple video decode (2026-10-14) - built and verified on the M1 Pro

`mseries/install-video-decode.sh` builds omacom's `libva-v4l2_request` fork (the one omarchy-mac ships as `libva-v4l2_request-avd`) from the pinned commit c653eaa (sha256 `0d8368fe...` checked before building) against Ubuntu's libva 2.23, installs `v4l2_request_drv_video.so` plus the `asahi_drv_video.so` alias, and verifies with `vainfo`. Run here against a temp driver directory with Ubuntu's own libva/vainfo extracted (nothing installed system-wide): the build succeeded, vainfo found the driver through the `asahi` alias with no environment variable, bound to the Apple Video Decoder ("detected 1 Request API decoder") and listed H.264 (baseline/main/high), HEVC (main/main10) and VP9 (profile 0/2) decode. Not tested: an actual video decode through a player (no ffmpeg/mpv here), and whether Brave uses VA-API on arm64. Wired in as the first-boot `video` module (installs the build dependencies, runs the script, records skipped if the kernel has no `apple_avd`); the setup also installs `avd-fw` on the Arch side so the firmware is copied into the elementary root.
`mseries/REINSTALL-RUNBOOK.md` is the plan for the first real run on a wiped Mac. The setup unit now tees its output to `/var/log/elementary-mac-setup.log` and the build to `/var/log/elementary-mac-setup-grow.log` so a failed run leaves evidence.

### Video decode and watchdog: tested for real on the M1 Pro (2026-10-14)

- **Hardware H.264 decode through VA-API is bit-exact.** With the driver built by `install-video-decode.sh`, a real ffmpeg (VAAPI hwaccel, `/dev/dri/renderD128`) decoded a 720p stream (100 frame hashes, 0 differ from software decode) and a 1080p stream (180 frames, 0 differ) on the Apple Video Decoder.
- **Real kernel bug found on the way.** The apple_avd driver (`avd_init_job`, called from `avd_h264_run`) does an order-10 contiguous kmalloc per decode job. After ~85 minutes of desktop use that allocation failed (`page allocation failure: order:10` in dmesg), and the 1080p stream then failed twice ("decoder reported an error"; once a decode hung with all `av:h264` worker threads idle and had to be killed). After `echo 1 > /proc/sys/vm/compact_memory` the same stream decoded fully, bit-exact, with no new allocation failures. So decode can fail on a machine that has been up a while. Mitigation shipped: `vm.compaction_proactiveness = 60` (unproven). **Root cause found and patched in the source (2026-10-14):** `avd_init_job()` in `avd-drv.c` does `kzalloc(sizeof(struct avd_segment) * MAX_SLICES)` per job = 4096 x (8 + 4x512) B = about 8 MiB, an order-10 allocation on 16K pages; the segments are only read by the CPU, so `kvcalloc`/`kvfree` is correct. `mseries/fairydust/debian/0003-avd-job-segments-use-kvmalloc.patch` (dry-run applies with `--fuzz=0` to the pinned `ce9f2eba72c0` source) is applied by `debian/build.sh` (version bumped to `7.1.13+elementary.usb4.4`, workflow and image profile follow) and by the Arch `usb4/PKGBUILD` (via `build-pkg.sh`). Compiled (see below), not booted: the next kernel build must be followed by a 1080p VA-API decode on a machine that has been up a while without compacting first. Worth sending upstream to Asahi too.
- **Audio watchdog hang simulation.** `mseries/audio/test_audio_watchdog.py` now drives the real main loop with a fast clock and fake system calls: a hang cured by one restart is restarted once; a healthy server, a single failed probe, and a locked screen cause no restart; an incurable hang stops at 3 restarts and notifies exactly once. This is a simulation, not a real wedged WirePlumber.
- Not tested: playing video in an actual player/browser, Brave's use of VA-API, power draw.

### Kernel patches worked through (2026-10-14)

Inventory: `fairydust/usb4/0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch` (11,677 lines, 53 files: Sven Peter's USB4/Thunderbolt host series imported onto the 7.1-based fairydust), `fairydust/debian/0001-runtime-dependencies.patch`, `0002-precreate-apple-dtb-directory.patch` (Debian packaging fixes), and my `0003-avd-job-segments-use-kvmalloc.patch`.
- **All four apply with `patch --fuzz=0` in `build.sh`'s order to the pinned `ce9f2eba72c0` source, and everything they touch compiles** (new `debian/compile-check.sh`): `thunderbolt/{apple,nhi,tb,stream}`, `net/thunderbolt`, `reset-apple-cio`, `phy/apple/atc`, `typec/{class,tipd/core}`, `apple/avd`, and the J314S, J316C, J414S, J416C, J475D device trees (the shared `.dtsi` files feed all five). Zero errors or warnings. Two files (`stream.c`, the net driver) are not built by the shipped config (`USB4_STREAM`/`USB4_NET` are off) so they are inert unless someone enables them; they compile too.
- Hand-reviewed the non-imported glue: `atc.c` (new `atcphy_configure_pipehandler_usb4` shares the extracted `atcphy_pipehandler_set_mux`; the unhandled-state default is now an initial `-EINVAL`), `tipd/core.c` (Thunderbolt/USB4 altmode registration with matching teardown on disconnect, remove and shutdown; `guard(mutex)` in `cd321x_remove` is safe because `tipd_remove` does not hold the lock when it calls it; a failed `typec_mux_set` leaves the altmode inactive so the next status update retries), the `j314-j316` device tree (every `usb4_N_acio` endpoint pairs with a `typec`/`dwc3` endpoint; ATC3, which is HDMI-only, loses its USB4 nodes). No defects found.
- Known upstream limits stay: DisplayPort tunnelling is not implemented, and suspending with a USB4 link up is unsafe (SError) - the docked-lid mode exists because of the second.
- The kit's `usb4/config` plus the build recipe's overrides reproduces the running kernel's `/proc/config.gz` except that `olddefconfig` drops `SERIAL_AMBA_PL011` (checked by diff).
- `fairydust/enable-elementary-fairydust.sh`, `verify.sh`, `host/*`, `usb4/install-*.sh` are the owner's machine-specific tools (hard-coded UUIDs, `/mnt/fdbuild`, `/home/techmore`); for a fresh install `elementary-grow.sh` derives the entry from the running kernel flavour instead.

## Next tasks, in order

Coordination: Codex handles implementation and review; OpenCode handles
build preflight/log analysis using its configured provider (explicitly
approved by the owner). Claude Code can take over from this file. All
agents must document commands, outcomes, blockers, and next steps; commit
and push completed batches. Coordinate Git writes through one agent at a
time. OpenCode's assigned preflight writes only OPENCODE-BUILD-REPORT.md;
Codex reviews and commits its report alongside the implementation.

Model preference recorded from the owner: use Muse 1.3 for OpenCode build
work (`opencode/muse-spark-1.3` is listed as available); DeepSeek 4.1
(`opencode/deepseek-v4.1-flash`) is another preferred option. The initial
preflight used the configured default `opencode/cat-jam-free` before this
preference was supplied. Do not silently claim that run used Muse.

Model-selection references supplied by the owner:
- https://opencode.ai/data/ — usage/session-cost data; assess task results too.
- https://anoma.ly/notes/opencode-2-0/ — service/API and background-task design.
- Owner flagged DeepSeek V4.1 usage credits and a one-week Step 5 Preview
  promotion announced October 8. Verify current eligibility/expiry before
  assuming free use or credits. Step's listed model ID is
  `opencode/step-5-preview-free`.

## GitHub progress

Owner monitoring dashboard: `docs/build-status.html`, linked from the site
home page. It reads public GitHub workflow status every five minutes, shows
actual build stages, and explains when to poke Codex. It cannot wake agents.
GitHub Pages workflow ID 382174750 is used because its workflow is dynamic.
No access tokens are embedded. The dashboard falls back to GitHub links
when requests fail or reach anonymous API limits.

Implementation pushed as 39fd815; reviewed preflight/dependencies pushed as
401dad7. GitHub Pages deployment for 401dad7 succeeded.
The first manual runs were started at 401dad7:
- Experimental arm64 build: https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38396499561
- Validation: https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38396503055

Validation completed successfully, including mkosi config parsing. The
experimental build completed successfully on October 13 (25m 49s).
See FIRST-ISO-BUILD.md for inspected logs, installer/artifact details, and
remaining checks. The installer has not been booted or independently
checksum-verified locally; do not launch duplicate builds without new changes.

Final OpenCode review used `opencode/muse-spark-1.3-contributor-free`, as
requested. It inspected the corrected finalize allowlist, both arm64
consumer configs, workflow, and regression tests; both tests passed and
it reported no new blocker in that scope. No ISO was built by the reviewer.

## Build-log findings and source cleanup

The first successful image log review and dispositions are recorded in
[BUILD-ERROR-REVIEW-2026-10-13.md](BUILD-ERROR-REVIEW-2026-10-13.md).
The ISO label repair now has a focused CI regression test. Follow-up cleanup
also removes a duplicate D-Bus sysuser definition and fixes the image's stale
tmpfiles entries. Run 38400807824 was still building when reviewed; it includes
the ISO-label repair but predates the later sysusers/tmpfiles cleanup. Its
artifact and log should be inspected before starting another full build.

## Next implementation tasks

1. Continue checksum/content/boot qualification from FIRST-ISO-BUILD.md.
   Future workflows retain a small checksum manifest separately from the
   7 GB installer artifact, avoiding a full ISO download just to read its hash.
2. Package the tested Ubuntu speaker chain into the image. Ubuntu supplies
   speakersafetyd/asahi-audio/alsa-ucm-conf-asahi, but its PipeWire build lacks
   the LV2 filter plugin. Build the plugin against the exact image PipeWire
   version and package it reproducibly before enabling DSP. See
   install-pipewire-lv2.sh and install-audio-stack.sh. Do not expose raw
   internal speakers as a fallback or bypass speakersafetyd.
3. Qualify an Asahi kernel and boot path for the factory image. The working
   host uses a custom fairydust kernel; Ubuntu generic is unverified. Do not
   alter this host's bootloader or install an experimental kernel to it.
4. Audit public OS 9 component changes (Gala, Wingpanel, Granite, settings)
   against installed package versions; choose reproducible fixes, not blanket
   desktop upgrades. Record source commits and licenses for each import.
5. Keep omacom/omarchy-mac-pkgs as the Apple hardware behavior reference at
   222f7a8599bbdd287ac6a95362cd51c5b024baae. Translate Arch behavior to
   Ubuntu/Pantheon. Its package repository was not modified by this work.

## Preserve unrelated work

These pre-existing untracked Gala drafts were not changed or committed:
- mseries/gala-daemon-fix/build.py
- mseries/install-gala-osk-fix.sh
- mseries/patches/gala-disabled-osk-input-purpose.patch

Inspect and reproduce the reported OSK issue before incorporating them.

## Verification

Run python3 mseries/test-image-wiring.py and git diff --check.
CI also parses all mkosi configs with just mkosi summary. This workstation
now has just and podman installed and local read-only mkosi summary passed.
Local full image assembly is blocked by disk headroom (see LOCAL-BUILD.md).
The first ISO build succeeded in GitHub CI; no hardware qualification
is claimed. See FIRST-ISO-BUILD.md. This handoff supports manual takeover by Claude Code; it does
not install a timer or automatic agent switch.

## After the successful first build

Public CI log analysis by OpenCode/Muse 1.3 was explicitly authorized by
the owner and completed; see BUILD-38396499561-REVIEW.md. Codex corrected
ARM APT disc architecture metadata and the non-compliant ISO volume label.
Future build records also retain the installer checksum and size separately.
These changes require a new image build; the existing successful artifact
at 401dad7 predates these follow-up fixes. No local kernel/boot/audio changes
were made. Shell syntax and target architecture/label checks passed.

Follow-up runs launched at c1891b6 (queued when recorded):
- Rebuilt installer: https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38400807824
- Validation: https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38400810884
The build dashboard selects the latest run automatically. Inspect these
before starting more builds; the earlier 38396499561 build is complete.

## Local build preparation (October 13)

Owner requested local builds and chose internal storage only if it passes
capacity checks. Installed official Ubuntu just/podman plus dependencies;
local read-only mkosi summary passed and its container sees all 10 CPUs.
Full local image assembly has not started: 37.4 GiB free is below the
conservative 60 GiB disk guard. See LOCAL-BUILD.md and run
`python3 mseries/local-build-preflight.py` before starting a local image.
Disk-boundary/new-directory/tool/architecture tests pass. The public
build monitor now distinguishes this blocked local build from GitHub CI.

## Storage cleanup and expansion plan

Owner authorized clearing downloaded Hugging Face models, disposable caches,
and Fairydust build working copies after validation. The source trees were
archived (452 MiB, zstd integrity test passed), missing build config and actual
running config were preserved in Git, and installed/recovery kernel files
were retained. Six exact snapshots were deleted after explicit approval:
4–7 and migration copies ending 102330/102435; newest rollbacks and all OS
roots remain. Filesystem free space increased from 37.4 to 49.6 GiB.
Full local image build remains blocked by the conservative 60 GiB guard
(10.4 GiB short). See STORAGE-PLAN.md for the actual partition layout and
APFS/Recovery assessment needed before allocating more space to Linux.
No partition resize was performed. Model/browser caches must be downloaded
again when needed; account metadata and installed applications were kept.

## Old OS retirement and local build readiness

Owner explicitly approved the remaining old OS roots and snapshots after
learning that the compiled kernel does not depend on the old build OS.
All approved subvolumes were removed; only @elementary/@elementary-home
remain. Private old-home/config and boot archives passed integrity checks.
Stale Omarchy GRUB entries were removed, preserving elementary's custom USB4
default; active kernel/initramfs/m1n1 SHA-256 checks passed unchanged.
Free space is 69.4 GiB, so local-build preflight now passes. Legacy Arch
rebuild scripts require a new build environment. See STORAGE-PLAN.md.

local-build-worker.sh provides an isolated-checkout build worker with
preflight, source revision, phase/status JSON, build log, final exit status,
and checksum records. It does not install an image or alter host boot files.

First native OS 9 build started at 09:42 EDT October 13, source 89e959d,
isolated checkout `/home/admin/Documents/os9-local-build-20261013`.
User unit: elementary-os9-local-build-20261013.service (Nice=10, no CPU cap).
Worker status/logs are in local-build-records; advancing image-build logs
were verified. Local monitor http://127.0.0.1:8767/ was opened and shows real
phase/log activity. See LOCAL-BUILD.md. Check that job before launching any
more local builds; no local build success or hardware boot is claimed yet.

Native build 89e959d completed successfully October 13, 09:59:08 EDT,
exit 0, elapsed 16m39s. ISO and SHA-256 are recorded in LOCAL-BUILD.md.
Local monitor reads success/complete from the worker status file. Build
artifacts/caches now leave about 39 GiB free; check capacity before rebuilding.
This was image assembly only; no factory-image hardware boot is claimed.

Post-build inspection: ISO SHA-256 verification passed, but the live installer
was missing its Apple hardware overlay. mkosi.profiles/aarch64 is opt-in and
was not selected by daily builds. Fixed by using an Architecture=arm64
mkosi.conf.d drop-in and explicit apple-silicon dependencies. Effective local
summary passes for liveiso and sysupdate. Tests also inspect actual built
liveiso payloads, now called by CI and the local worker. Rebuild required;
the 89e959d image is assembled/hashed successfully but lacks those live-session
helpers. See LOCAL-BUILD.md. Do not describe it as ready for hardware boot.

## Generic VM boot milestone

While corrected GitHub build 38410538372 runs, the existing local 89e959d
ISO booted in QEMU/KVM to the graphical installer language screen. VM had
4 CPUs/4 GiB, network disabled, read-only ISO, no host or writable guest disk.
Screenshot and reproducible command are in VM-SMOKE-TEST.md. Stop at this
milestone: no installer selection, installed guest, or Mac hardware boot was
verified. That ISO still predates the live-session overlay fix; repeat the
content/VM checks on the corrected build before progressing.

## Corrected image completed — 2026-10-13

Run 38410538372, source 32877a7, succeeded at 14:35:12 UTC after 28m27s.
Downloaded small public build records to /tmp/os9-build-38410538372.
image-content.log confirms actual liveiso hardware payload check passed;
checksum manifest and source provenance inspected. Exact ISO/checksum are
in FIRST-ISO-BUILD.md. Installer and records upload steps succeeded.
Next: independently hash and VM-boot this corrected ISO, then implement a
reproducible Asahi kernel/firmware path against KERNEL-REPORT.md. The previous
local ISO's VM boot does not qualify this corrected artifact or Mac hardware.
Untracked Gala drafts remain untouched. No host boot/audio changes.

## Enhanced kernel Debian port started — 2026-10-13

Owner requested merging our kernel enhancements into the test image. Added
fairydust/debian/build.sh: pinned archive/config/USB4 patch hashes, clean patch
application, strict driver/page ABI gate, isolated output, distinct kernel
release, bindeb-pkg, all CPU jobs (explicit dpkg override), and low-space stop.
Source preparation and native Rust toolchain check passed. Installed missing
build dependencies only; no kernel or host boot/audio changes.

The native ARM64 Debian kernel package completed in user unit
elementary-fairydust-deb-20261013c.service, work
/home/admin/Documents/os9-fairydust-deb-20261013, log
/home/admin/Documents/os9-fairydust-build.log. The package was subsequently
rebuilt with built-in PL011 serial support for VM diagnostics. The build helper
supports `--reconfigure` for refreshing a prepared tree and no longer requires
the source archive when resuming a compile. No host kernel or boot files were
changed. Preserved earlier local ISO and build records/kernel config; removed
its regenerable mkosi intermediate outputs and synced Btrfs, restoring ~44 GiB.

Also inspected signed Ubuntu Asahi resolute candidate metadata and packages:
baseline GPU/audio config passes, experimental USB4/video symbols absent.
KERNEL-REPORT.md records verified hashes/fingerprint and the packaging boundary.
check-kernel-config.py plus four regression checks added to validation CI.
Corrected CI ISO download remains active (gh exec session 50981); verify its
checksum before repeating the isolated VM test. It is the generic kernel ISO,
not the newly compiling Fairydust-enhanced image.

## Corrected ISO VM check completed

Corrected run 38410538372 ISO downloaded to os9-corrected-38410538372;
independent sha256sum verification passed. Repeated isolated 4 CPU/4 GiB
KVM/UEFI boot, no network/writable system disk. Graphical installer language
screen and serial login reached. Screenshot committed; see VM-SMOKE-TEST.md.
VM stopped, releasing resources. Enhanced kernel compilation remains active
and separate; next inspect its .deb output and boot hooks, then integrate the
pinned enhanced kernel + m1n1/DTB path into an opt-in test image.


## Fairydust Debian build completed

Native ARM64 .3 package build passed after resolving packaging issues: first
missing libdw-dev, then concurrent DTB directory creation. Corrected source
patch precreates Apple's DTB folder. Completed `elementary-fairydust-deb-20261013f.service`
exit 0. SHA verified at package-inspection time; image .deb SHA
2f48c0619d02b036a625427c2767dc335eb34a0997ab3f371712e2b4541b4b2f.
Extracted contents confirm requested Apple modules and t6000-j314s.dtb.
Runtime dependencies fixed; generic /boot+initramfs hooks still need an
isolated mkosi adaptation. No install or boot test of the new kernel.

Corrected factory ISO independently verified and booted to graphical
installer; see VM-SMOKE-TEST.md. Commit 9edff7f. Next implementation is the
opt-in Fairydust image profile with pinned m1n1, DTBs, packages and mkosi-safe
boot hooks, then VM test. Never touch current host kernel/boot for this work.


## Opt-in image integration staged

Added base/liveiso fairydust mkosi profiles and a manual workflow input to
build the pinned kernel on ARM64 CI and feed it with hash-pinned Ubuntu Asahi
m1n1/U-Boot packages via ignored mkosi.packages. Verified the m1n1 package
contains all three required USB4 tunable/DROM strings. This profile is opt-in.
It does not yet assemble/install the m1n1 ESP boot.bin, so its installer is
for QEMU kernel/installer testing; Mac hardware boot needs that separate step.
Run the workflow with fairydust=true after this commit and inspect summary,
package apt resolution, initramfs, GRUB/ISO boot, then continue m1n1 ESP work.


## Fairydust image workflow first CI attempt (October 13)

Run 38431694534 exercised the new opt-in image workflow. Package source
download, SHA verification, USB4 patch application, config generation, and
strict Fairydust config validation passed. The kernel job then stopped at
`make rustavailable`: GitHub's active rustup stable toolchain lacked its
`rust-src` component. The image job correctly skipped because the kernel
package was not produced. No ISO or host changes resulted.

Fix: explicitly install `rust-src` into the active stable rustup toolchain
before building, and document this requirement. The fetch helper also now
truncates its upstream checksum manifest on rerun. Validation and a fresh
opt-in CI run remain pending.

## Opt-in Fairydust image CI result (October 13)

The first opt-in run 38431694534 failed before compilation because the
runner's Rust toolchain lacked `rust-src`. The workflow now installs that
component explicitly. The fix is commit `4c0cdb9` and has been pushed.

Run [38432118320](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38432118320)
then passed both kernel-package and image jobs. The pinned Fairydust + USB4
kernel package, m1n1 and U-Boot packages were hash-verified and installed in
the image. `test-image-wiring.py` passed; mkosi generated a 79.7 MB Fairydust
UKI and module initrd. The downloaded 7.48 GB ISO passed its independently
recorded SHA-256 and booted to the live login prompt in isolated QEMU/KVM.

Important test boundary: the ISO's GRUB live entry boots `/casper/vmlinuz`
and `/casper/initrd`, which selects the generic kernel. That ISO QEMU run
proves the installer image starts, not the Fairydust kernel. A separate direct
Fairydust-kernel VM smoke test was completed afterward; it verifies generic
ARM64 userspace handoff only. Apple DTB selection, the m1n1 ESP payload and
hardware boot qualification remain open. See `VM-SMOKE-TEST.md` for evidence.


## CodexBar refresh responsiveness (October 13)

Owner approved shortening quota polling after investigation found the local
backend configured for 300 seconds, refresh-on-open disabled, and the native
Wingpanel indicator reading cached snapshots only once per minute.

Changed the native indicator to read snapshots asynchronously every five seconds.
Opening its dropdown requests a refresh when any provider timestamp is missing
or at least 30 seconds old, unless a fetch is running. A monotonic one-minute
cooldown bounds panel-open requests and also accounts for manual refreshes.
The asynchronous reader coalesces overlapping reads, including an open request
that arrives while a snapshot is already being fetched. Provider credentials
and quota fetching remain owned by CodexBar.

Applied `{"refreshSeconds":60,"refreshOnOpen":true}` to the existing backend
through its configure IPC. Installed the tested indicator atomically and sent
Wingpanel SIGTERM so Gala reloaded it. The installed module SHA-256 matches the
built module. Original config and module are retained temporarily at
`/tmp/codexbar-linux-before-refresh.json` and `/tmp/libcodexbar-before-refresh.so`.

Validation: `meson setup /tmp/codexbar-refresh-build mseries/codexbar-wingpanel
--prefix=/usr`, `ninja -C /tmp/codexbar-refresh-build`, and `meson test -C
/tmp/codexbar-refresh-build --print-errorlogs` passed. Five GLib test cases cover
unknown/fresh usage, busy suppression, the exact one-minute cooldown boundary,
and wall-clock changes. The installer now runs these tests before installation.
A temporary GTK/Wayland probe substituted only the backend executable path with
a fake CLI: one-second snapshot delays allowed 143 main-loop ticks in 7.2 seconds,
four snapshot reads, and one refresh despite repeated opens.
`python3 mseries/test-image-wiring.py` passed all four checks; installer shell
syntax and `git diff --check` passed. Source review found no additional blocker.

Live verification observed consecutive Codex fetch timestamps at 14:03:25 and
14:04:25 ET (60 seconds), and Claude at 14:03:34 and 14:04:35 ET (61 seconds),
on October 13. Both cycles completed with empty error fields and `stale:false`.
Wingpanel restarted as PID 625220 and loaded the installed module.

This change is installed on the working desktop; no factory ISO was built.
Next: confirm everyday responsiveness with normal Codex/Claude use.

## Fairydust direct-kernel VM milestone — October 13

The kernel source config enables built-in PL011 console support so ARM64 VM
boot can be observed. Refreshed the prepared build tree with
`build.sh --reconfigure`, rebuilt natively with 10 jobs, and produced kernel
package SHA-256
`6047f67c33c78fd4c614adadb619aa612919e151497d3941fe8949ae08e084f3`.
`vm-kernel-smoke-test.sh` decompresses the Debian kernel image, builds a
temporary BusyBox initramfs, and boots with QEMU/KVM, two vCPUs, no disk, and no
network. Serial output confirmed Linux `7.1.13-elementary-fairydust-usb4`
reached `/init`, emitted `FAIRYDUST_KERNEL_USERSPACE_HANDOFF_OK`, and powered
down cleanly. Config gate and the Fairydust config unit checks pass.

This closes the kernel-decompression/basic-kernel/userspace-handoff check. The
next boot-path milestone is a disposable installed-system test image that can
boot the generated kernel/initramfs and prove Apple DTB selection. It still
needs a reproducible m1n1 `boot.bin`/ESP assembly method. Do not write the
shared host ESP or install this kernel on the host. Full machine boot, Apple
GPU, USB4, speakers, suspend and desktop behavior remain unqualified.

The pinned Asahi m1n1/U-Boot packages can be assembled into stage 2: in a
temporary directory, the package binaries plus 41 Fairydust `t6*.dtb` and
`t81*.dtb` files produced a 5,028,827-byte payload whose FDTs, USB4 tunables,
and compressed U-Boot member all verified. Ubuntu's separate `asahi-scripts`
package contains `update-m1n1`, but its default DTB lookup misses our package
path. Hashes and assembly checks are in `KERNEL-REPORT.md`. Next, add explicit
`DTBS`/`U_BOOT` selection and a disposable image ESP integration before any
hardware path is considered; do not write the shared ESP.

## Fairydust image build and reproducible boot payload — October 13

The opt-in GitHub Actions run 38444570042 succeeded from source commit
`aebf31c97cdb1abd9471b94cec9d2891dd4616f0`: kernel package, image assembly,
live-image hardware-payload check, checksum records, and artifact upload all
passed. The image is 7,481,858,048 bytes with SHA-256
`75b67a02230fc8ac0676e8d8ec7d39fcec8478d9ef9481be7be362c60eab368c`.
The GitHub artifact is [available from the run](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38444570042/artifacts/11841535221);
it was not downloaded because of its size. This is build/image qualification,
not a Mac hardware-boot result.

Added a non-root m1n1 payload assembler and four integration tests. It
reproduced a 5,028,282-byte `boot.bin` from the exact kernel, m1n1 and U-Boot
packages in `/tmp`; SHA-256 and the decompressed U-Boot member are recorded in
`KERNEL-REPORT.md`. The opt-in Fairydust workflow now assembles this payload
from its pinned artifacts, stages it at `efi/m1n1/boot.bin` in the disposable
sysupdate image, and checks the copied ESP file against the source checksum
using `sfdisk` and read-only `mcopy`. The fast validator covers the payload
assembler and GPT offset logic. Full CI run 38479577898 passed and verified
the target ESP entry at GPT offset 1,048,576: `m1n1/boot.bin`, 5,028,282
bytes, SHA-256 `049c5bf29e5e4f379e44e8ef8fffce3a018ede03ee19676c98cc6ee6e8608f8d`.
It completed the installer build and checksumming too. The resulting
`elementaryos-9.0-daily-arm64.20261013230825.iso` is 7,482,648,576 bytes with
SHA-256 `89c74fa25ac72dd8f20f7eb42e456c929ed828f791f77af3edb6f5ce1b7b259d`;
the installer artifact is retained by GitHub for seven days. The image has
not been booted on Apple hardware, and no host ESP was written.

The preceding run 38473436256 exposed an overbroad `elementary_*.raw` guard
that also matched separate partition images. The selector was narrowed to the
timestamped whole-disk image before the successful rerun. See the run's
[build record](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38479577898)
and `mseries/KERNEL-REPORT.md` for verification details.


## CodexBar quota ETA (October 13)

Owner requested a visible ETA for remaining usage. The existing CodexBar Linux
IPC feed already includes the CLI's pace summary for each quota; the native
indicator previously hid it in a tooltip. Added QuotaEta.vala to present those
upstream forecasts and choose the earliest available limiting window.
The bar shows session/general percent remaining plus the limiting quota label
and ETA; both percentages and individual forecasts remain in the dropdown.
An exhausted limit shows its reset countdown. Unknown pace, unsupported wording,
provider errors, snapshots older than three minutes, and expired reset boundaries
suppress forecasts. A safe measured quota does not vouch for an unknown quota.
These are quota estimates based on CodexBar's average usage pace, not exact
remaining token balances or guaranteed exhaustion times. The compact IPC does
not export structured etaSeconds, so recognized upstream summary phrases are
parsed defensively; unknown future wording falls back to unavailable.

Validation: `ninja -C /tmp/codexbar-refresh-build` and `meson test -C
/tmp/codexbar-refresh-build --print-errorlogs` passed (11 ETA cases plus the five
existing refresh cases). Covered session/weekly projections, exhausted-without-
pace, immediate depletion, unavailable/malformed data, stale/provider errors,
expired resets, limiting-window selection, and unknown limits alongside a safe
limit. A temporary GTK/Wayland fixture probe verified rendered bar and dropdown
labels, and the final 332×344 layout was visually inspected. Its synthetic
preview is `/tmp/codexbar-eta-preview/preview.png`; it is not a live account image.
`python3 mseries/test-image-wiring.py` passed all four checks; `git diff --check`
passed. Source review found no remaining blocker.

Installed the built module atomically and reloaded Wingpanel through Gala.
The previous module remains at `/tmp/libcodexbar-before-eta.so` for rollback.
A read-only live snapshot run through the compiled model produced a weekly
forecast for Codex and an exhausted-session reset countdown for Claude.
One-minute backend polling and five-second asynchronous panel reads are retained.
This qualifies the running desktop indicator only; no factory ISO was built.
Next: use the displayed forecasts during ordinary work and reassess if the
upstream pace format changes or a recent-rate estimate is requested.

## Tether continuity branch — October 13

Created `mseries-tether-continuity` from the clean `main` branch to scope an
optional iPhone-to-elementary continuity add-on. Upstream Tether describes
direct iPhone/Linux SMS and iMessage messaging plus OTP handoff; this removes
the architectural need for an always-on Mac relay. Source pin: v0.2.37,
`d1f976aeb71896c411057cea9c899c9e40eb64a5`; upstream ARM64 `.deb` SHA-256 is
recorded in `TETHER-CONTINUITY.md`. License: upstream MIT.

The goals, package boundary, privacy expectations, dependencies, and real
device acceptance checklist are in [`TETHER-CONTINUITY.md`](TETHER-CONTINUITY.md).
AirDrop-style LocalSend and experimental M1 Pro Touch ID/PAM are separate
optional tracks. `mseries/install-tether.sh` now verifies and installs the
upstream ARM64 package, reports BlueZ readiness, and supports package removal
and explicit data purge. `mseries/tether/brave-extension.py` prepares the
Chromium extension and registers/unregisters its native host in Brave's user
profile. Neither installer was executed; no package, base image, auth setting,
Bluetooth pairing, or user data was changed. The host has BlueZ 5.85, below
Tether's 5.86 requirement for Bluetooth messages. Next: determine a supported
OS BlueZ 5.86+ source, then qualify messages with the owner's phone; separately
review the Brave extension's all-sites permission during OTP qualification.

## CodexBar OpenCode Go provider — 2026-10-13

The owner requested OpenCode visibility/sign-in in the M-series CodexBar build.
`install-codexbar.sh` now includes OpenCode Go in the default custom provider
list on a fresh install and appends it to existing Codex, Codex+Claude, or
custom provider selections while preserving other app preferences. Explicit
unrelated single-provider choices remain unchanged. The installer writes the settings
file with owner-only permissions using a same-directory atomic replacement.
Wingpanel now renders the provider name as “OpenCode Go”.

`codexbar-opencode-wrapper.py` reads only the `opencode-go` key from OpenCode's
user `auth.json` and injects it into the environment for CodexBar OpenCode Go
usage queries. Existing `OPENCODE_API_KEY` takes precedence. The credential is
not copied into CodexBar settings or the OS image. `DESKTOP-SETUP.md` documents
signing into OpenCode Go in the CLI and the local-usage estimate boundary.

Validation: `bash -n mseries/install-codexbar.sh`, Python bytecode compilation
of the wrapper, and `git diff --check` passed. No runtime install, authenticated
usage fetch, or automated tests were run. Next: install on the working desktop,
sign into OpenCode Go through its CLI, and confirm the Wingpanel quota row.

## Torrential native desktop and download — 2026-10-13

The local M-series fork at `/home/admin/Documents/TorrentialFork` is committed
as `4082b079dab42a53c80a8ebbb6a11253ac716453`. It fixes unread daemon stdout,
RPC startup timing, per-app config creation, loopback RPC binding, and graceful
SIGTERM/wait shutdown. The native ARM64 package `0.1.0-1~mseries3` installed
with the system Transmission 4.1.1 backend and elementary's `libgranite7`.
A scoped AppArmor addition permits the daemon's Torrential config and Downloads
folder and graceful termination. The fresh system daemon service was disabled
on this host so the app owns its backend. No factory image was changed.

The app launched in the active desktop session and remained running while the
official Ubuntu 26.04.1 Server torrent transferred data. A check showed about
235 MiB downloaded, 50 peers, and 13.5 MiB/s without an error. The full ISO
then completed and matched Ubuntu's published SHA-256. RPC pause/resume checks
passed; the completed test torrent was paused. The initial ARM64 desktop torrent was rejected by Ubuntu's
tracker and removed. The server torrent remains in Downloads. UI button and
close/reopen qualification remain. See `mseries/TORRENTIAL-PORT.md`.

The upstream rewrite has no license grant. The owner-requested fixes are
pushed to the private [`techmore/torrential`](https://github.com/techmore/torrential)
repository on `mseries-native` at `4082b079dab42a53c80a8ebbb6a11253ac716453`.
Keep it private until redistribution permission is clear. This public OS repo
contains only downstream packaging and status. No one was contacted and
nothing was sent to the upstream project.

## Native battery time-to-full — 2026-10-13

Added the charging estimate beside elementary's existing Power indicator
icon. The installer pins and patches official `elementary/panel-power` source,
builds the native Wingpanel module, preserves the original module, and can
restore it with `--uninstall`. The native module built and was installed on the
M1 desktop; Wingpanel restarted and remained running. UPower supplied a valid
charging estimate. Visual confirmation of the label was unavailable in the
isolated desktop command session. Details: `mseries/BATTERY-ETA.md`.

## Network speed readout persistence — 2026-10-13

The user's panel-speed setting was already enabled, but the plugin had been
installed by replacing `libnetwork.so` in the current `/usr` image. A reboot or
OS image deployment restored the stock file. The Apple Silicon mkosi image now
builds pinned `elementary/panel-network` commit
`8685ec8e55a45e48da0c12931a353cd440d11664`, applies the three tracked network
patches, and places the resulting module into the overlay consumed by both
liveiso and sysupdate. The build checks that the target package remains 8.0.1.x.
`test-image-wiring.py --image-output` now checks the module is present in both
final image roots. The local installer remains useful for the current image;
the new image build is what makes the change survive redeployments and image
updates.

No full image build has run for this change. Next: run the M-series validation
workflow, then the full arm64 image build and post-build module check before
deploying the resulting image. The working desktop currently has the patched
module installed and `~/.config/mseries/network-speed.ini` enables the panel
readout.

## Restore Wi-Fi filtering and network usage views — 2026-10-13

Recovered the original network-menu patch from local commit `b28aab1` on the
sibling `mseries-usage-troubleshooter-docked-lid` branch. The connected Wi-Fi
list now hides other networks by default with a chevron to reveal them. The
popover also has Apps, Hosts, and DNS usage views; hostnames are learned from
systemd-resolved's cache and query monitor. Kept this branch's existing
throughput graph and optional panel-speed toggle by applying only the Wi-Fi,
usage-widget, and stylesheet sections from the recovered patch, then wiring
the new widget with `wire-network-usage.py`. The local installer and Apple
Silicon image build both carry the enhancement; `libsqlite3-dev` is now a build
dependency.

The pinned module built and installed on the M1 Pro. The original module is
preserved at `/usr/local/lib/mseries/libnetwork.so.original`, and the new
module has no unresolved shared libraries. Wingpanel was signaled to reload.
The `netusage` user service is enabled and active; its database at
`~/.local/share/netusage/usage.db` contains app/host totals and DNS query rows.
Visual confirmation of the menu and chevron behavior remains pending because
the desktop session is isolated from this command session. No factory image
build was run; image deployment is still needed for persistence across OS
redeployments. Next: visually confirm that the joined SSID is the only one
shown by default, that the chevron reveals other networks, and that Apps,
Hosts, and DNS render in Wingpanel.

## 2026-10-14: hardware decode verified at 720p, 1080p and 4K (current kernel)

- On the M1 Pro (elementary, Arch `7.1.13-1-2-fairydust-usb4` kernel), `mseries/install-video-decode.sh` built and installed the
  VA-API driver (7 decode profiles) and `mseries/check-video-decode.sh` passed: H.264 720p, 1080p and **3840x2160** decode
  bit-identical to software (both compared as NV12). Kernel log clean (no allocation failures, no hangs).
- Caveat: this kernel does not have the 0003 kvmalloc patch, and memory was not fragmented (3h uptime, ~4.7 GB free). The 1080p
  hang is a fragmentation failure, so a pass here does not prove the fix; repeat on the usb4.4 kernel after a long uptime.
- Not yet tested: real files (high bitrate, B-frames, 10-bit HEVC/VP9), a real player, Brave's VA-API.

## 2026-10-14 (end of session): where things stand, for the next agent

**Host facts.** The dev machine is the M1 Pro running **elementary OS 9 (`apt`/`dpkg`)** booted on the **Arch kernel**
`7.1.13-1-2-fairydust-usb4-ARCH` (Asahi Alarm owns kernel/initramfs/GRUB; see `KERNEL-FLOW.md`). 10 cores, 30 GB RAM,
31 GB free on `/` (95 GB btrfs on LUKS `/dev/mapper/root`). The owner is about to **resize the partition** (an hour, done on the
Mac side by the owner; do not touch partitions) before a local image build.

**Done and pushed (main):** one-command installer `bin/elementary-mac-setup` (+ sandboxed flow test, CI), enhancement layer
(`mseries/enhance.sh`, `enhance-firstboot.sh`), elementary unlock screen, kernel patches (0003 AVD kvmalloc, usb4.4), README
rewritten as an omarchy-mac-style install guide with a work-in-progress status table, `mseries/DOCS.md` index,
`mseries/check-video-decode.sh`.

**Verified on hardware this session:** `install-video-decode.sh` builds/installs the VA-API driver here (7 profiles); H.264
720p/1080p/**4K** hardware decode is bit-identical to software on the current kernel (memory not fragmented, so this does
not prove the 0003 fix).

**CI, workflow `daily-9.0.yml` with `fairydust=true`:**
- Run 38582725389 and 38589009211: `build-kernel` **succeeds** (~24 min). Artifact `fairydust-kernel-packages-<run>` has the
  usb4.4 `.deb` (downloaded and checksum-verified once; `apple-avd.ko` uses kvmalloc). Not booted anywhere. It is a Debian package
  for the factory-ISO route; the installer route uses the Arch kernel, so the fix must also ship as an Arch package
  (`mseries/fairydust/usb4/PKGBUILD` + `build-pkg.sh`, needs ~40 GiB free) to reach the installer path.
- `build` (factory ISO) **fails** both times. First failure (fixed in a3ed9f0): `build-network-indicator` version gate read the
  overlay's own dpkg database, always "none". Second failure: no error message. The log ends at 16:06:44 in "Building kernel
  modules initrd" (mkosi-initrd, `modinfo` over 8544 modules), the job ends 16:18:15 with a bare `exit 1`: looks like the process
  was killed (memory or disk on the runner), unconfirmed. Note the early line `depmod: ERROR: could not open directory
  /lib/modules/7.0.0-1017-azure` and `cryptsetup: ERROR: Couldn't resolve device overlayfs` appear but may be benign.

**Next steps, in order:**
1. After the owner's resize: check `df -h /` and `free -g`; run the image recipe locally (the CI step is `just` -> `mkosi`, see
   `.github/workflows/daily-9.0.yml` "Build experimental arm64 image") with all output to a log file and watch memory/disk while it
   runs, to see where and why it dies after "Building kernel modules initrd". Fix what it shows.
2. The factory ISO is optional for the owner's goal. The priority is the **wiped-Mac installer run** (`REINSTALL-RUNBOOK.md`);
   bring back `/var/log/elementary-mac-setup*.log` and `/var/log/elementary-mac-enhance.log`.
3. Boot a usb4.4 kernel (Arch package route), leave it up for a while, run `bash mseries/check-video-decode.sh` to prove the
   1080p/4K fix under fragmentation. Still untested: real files/player, Brave VA-API, audio watchdog against a real hang.

**Standing owner instructions:** always commit and push finished work to `main` without asking; never run deletion-style
commands on user data; "root root" login on the rescue system is deliberate (upstream standard); the owner likes Brave.

## Post-install gaps reported — 2026-10-14

Repeated desktop authentication prompts were traced in polkit's journal to
`org.freedesktop.resolve1.subscribe-query-results` from the netusage DNS monitor.
The monitor now passes `--no-ask-password`; its installer adds a rule allowing
only that read-only action for sudo-group administrators. Installing this rule
requires sudo once. General desktop authentication policies are unchanged.

After reboot, the live system ran stock `7.1.13-3-2-ARCH` and the dock mouse
and Ethernet disappeared. The retained USB4 entry is `elementary-usb4-test`,
loading `7.1.13-elementary-fairydust-usb4` with matching installed modules.
The owner requested this as the persistent default with stock kept for recovery.
`fairydust/usb4/set-default-kernel.sh` implements that policy in `custom.cfg`,
preserving one-time boot selection and a visible recovery menu. Applying the
live change requires sudo authentication.

The default runner previously installed the Wingpanel network module but omitted
the separate `netusage` user service that populates Apps/Hosts/DNS. It now runs
that installer by default after the panel module. Brave DRM support and CodexBar
(desktop/CLI plus the Wingpanel indicator) are also default stages. The
hash-pinned Widevine installer requires Brave to have been launched once and
fully quit. CodexBar installers now install their Qt runtime and Wingpanel build
dependencies. The image enhancement path now installs the CodexBar Qt runtime
and scoped DNS-monitor Polkit rule in firstboot, then retries the user's
CodexBar, netusage and Widevine setup at login without asking for user-level
sudo. `mseries/DESKTOP-SETUP.md` documents the DNS dependency on systemd-resolved
and the Omarchy-reported Brave/AVD green-video workaround.

Verified in this checkout: `post-install.sh --list` and `--dry-run` include all
new stages; `git diff --check` is clean. This command environment cannot inspect
the owner's live user service or browser profile, so apply with Brave fully
quit, then review `bash mseries/post-install.sh --status` and the service logs.

## Current desktop bug — unexpected screen dimming (2026-10-14)

The owner reports that the built-in display keeps dimming unexpectedly. The trigger remains unconfirmed. The default user brightness installer now backs up both GNOME `ambient-enabled` and `idle-dim`, disables them, and restores their prior values on uninstall. The image enhancement layer writes the same values as unlocked system dconf defaults for new sessions. This preserves manual brightness while leaving screen blanking and suspend enabled. Existing preference files are migrated by adding only the missing `idle-dim` value, without replacing the original ambient-brightness snapshot. Owner verification on AC/battery and through suspend/resume is still needed; if brightness changes, capture backlight and power-service logs. See `BUG-FIX-ROADMAP.md`.

## Requested desktop apps — 2026-10-14

- **Homeboard:** the project is hosted at `tasks.stoverparc.org`; `mseries/install-homeboard-launcher.sh` installs a user launcher and has been run. The separate elementary Tasks sync bridge needs `gir1.2-ecal-2.0` and `gir1.2-edataserver-1.2`, then a Google sign-in to register this computer. The current tool shell is not root and cannot install those packages; an `apt-get install` attempt failed on the dpkg lock permissions. The actual sign-in is still for the owner to complete in the desktop browser.
- **Emporia Energy Monitor:** the repository includes an elementary Linux client, not just its macOS Swift app. It connects to the existing SER8 collector and must not start another poller. The client's WebKit 6 GI package is absent in this shell, and upstream's `energy.stoverparc.org` public TLS/auth deployment is still documented as incomplete. Do not enable a local collector or trust the public endpoint until those gates are resolved. The macOS `build.sh` is not the Linux install path.
- **Torrential:** the private M-series source checkout was fetched and its locked ARM64 release build completed. This shell has no `transmission-daemon` or root access to install the daemon/AppArmor package, so it is not installed from this checkout. The handoff and roadmap retain the prior desktop install/transfer evidence; check the live desktop before treating this isolated tool environment as its current package state. Keep the fork private pending license grant.

## Enhancement integration review — 2026-10-14

Fixed the missing dconf profile selection for the system brightness defaults;
existing profile entries are retained and repeated installs add no duplicates.
Fixed POSIX syntax in the netusage installer and included curl, certificates,
Python, unzip and procps in the deferred user setup prerequisites. Completed
user setup stops the globally enabled timer for the current session; each new
login checks the existing completion markers before stopping it again.

Validation: `bash mseries/test-elementary-mac-setup.sh` passes, including staged
payload delivery, timer enablement, profile preservation and completion handling.
Bash/dash syntax checks and `git diff --check` pass. These are installer checks;
a fresh desktop login and factory hardware boot remain unverified.

## Atomic app deployment request — 2026-10-14

Created [issue #50](https://github.com/techmore/ElementaryOS_MSeries/issues/50)
and `ATOMIC-APP-DEPLOYMENT.md` for staged verified app releases, atomic
activation, rollback, concurrency/interruption recovery, user-data migration
handling and measured package-delivery performance. Compare Flatpak, Nix
profiles and versioned publisher bundles before selecting a backend. This
continues the owner's elementary/Nix spin interest. Current environment
inspection shows elementary OS 9 with apt and no apk executable. Slow package
delivery is owner-reported; no timing benchmark or manager migration was run.
Repeated per-installer apt refreshes are an observed performance candidate.

The factory-path inspection also found that the Apple Silicon overlay currently
builds the network/Quick Settings plugins but does not invoke the shared
`enhance.sh` layer. Its finalizer prunes most other files. Connecting the full
enhancement layer requires preservation rules and runtime dependencies; the
sysupdate path emits only `/usr`, so `/etc` configuration and `/usr/local`
helpers need deliberate treatment. This packaging gap remains open.

## Wi-Fi resume fix and mseries-power ordering — 2026-10-14

Found in the live journal (kernel 7.1.13-elementary-fairydust-usb4, uptime 2 h):

- `omarchy-wifi-resume-fix.service` failed at 15:47 with
  `modprobe: ERROR: could not remove 'brcmfmac': No such file or directory`.
  The script ran `modprobe -r` unconditionally, so when the driver was already
  unloaded it aborted before loading it back and Wi-Fi stayed down
  (`lsmod` showed only `brcmutil`; the machine was on USB Ethernet).
  Fix in `mkosi.images/apple-silicon/mkosi.extra/usr/sbin/mseries-wifi-resume-fix`:
  unload only when loaded, then always `modprobe brcmfmac` (and its holders).
- `mseries-power.service` (`After=power-profiles-daemon.service`, which is
  itself after `multi-user.target`) was `WantedBy=multi-user.target`, giving a
  boot ordering cycle that systemd broke by dropping a job. It is now
  `WantedBy=graphical.target` in `install-power.sh` and `enhance.sh`; the
  charger udev rule still triggers it on plug/unplug.

Tests: `mseries/test-wifi-resume.py` (new: missing driver is loaded without an
unload; both power unit templates avoid `multi-user.target`), and
`test-elementary-mac-setup.sh` now expects the `graphical.target.wants` link.
All pass.

NOT applied to the running M1 Pro (needs sudo): reinstall with
`sudo bash mseries/install-power.sh`, `sudo install -m755
mkosi.images/apple-silicon/mkosi.extra/usr/sbin/mseries-wifi-resume-fix
/usr/sbin/`, remove the stale `multi-user.target.wants/mseries-power.service`
link if left over, `sudo systemctl daemon-reload`, `sudo systemctl reset-failed`,
then `sudo modprobe brcmfmac` to bring Wi-Fi back now. Verify after reboot:
no "ordering cycle" line in `journalctl -b -p err`, and one suspend cycle with
Wi-Fi reconnecting.

Still open from the same audit: the DNS-logger polkit rule is probably not
installed (password helper still fires every ten minutes), `user@109` (greeter)
stop timeout from `obexd`, `mseries-verify` not on PATH.

## Package refresh overhead — 2026-10-14

Added `lib-apt.sh` and a temporary per-run cache in the manual post-install
runner. Brave, Firefox and the two CodexBar installers share a successful
repository refresh only while the source definitions and public signing-key
files match. New repositories/key changes force refresh; failures remain
retryable. Standalone installers retain normal refresh behavior. The shared
refresh uses the documented `--error-on=any` option so transient repository failures
cannot be treated as a successful cacheable update with stale metadata. The
helper is included in the firstboot payload, but firstboot itself does not yet
share the manual runner's cache. Each manual stage and actual refresh records
elapsed seconds in its output/log.

Validation: `bash mseries/test-apt-batch.sh` passes with stubbed sudo/package
commands (reuse, repository/key invalidation, failed-refresh retry and standalone
behavior). `bash mseries/test-elementary-mac-setup.sh`, Bash syntax checks and
`git diff --check` pass. No real package install or timing benchmark was run.
Atomic app deployment and the Flatpak/Nix comparison in issue #50 remain open.

## Feature request: True Tone-like display — 2026-10-14

Logged in `ROADMAP.md` (stretch goals) and `BUG-FIX-ROADMAP.md` (P3). Finding: the ambient light sensor on this M1 Pro (`/sys/bus/iio/devices/iio:device1`, `aop-sensors-als`) exposes only `in_illuminance_input`, no colour channels, so the interim design is a lux and time-of-day colour-temperature curve via the night-light path, independent of brightness. Night light is currently off at 4500 K. Not started.

## Screen dimming and 2026-10-14 live audit findings

**Screen kept dimming (fixed on the running desktop).** `idle-dim` was already off, but `org.gnome.settings-daemon.plugins.power ambient-enabled` was still `true`, so the ambient light sensor drove the panel backlight (323, 400, 375 of 500 within seconds). Commit eae7811 turned both off in `install-brightness-bridge.sh`, but it was never run on this Mac. Set both to `false` live with gsettings; the backlight then stayed at 375 for 24 s. `apply-desktop-settings.py` now sets both so a re-run or reinstall keeps them off. A full blank/lock still happens at `idle-delay` 900 s (15 min), which is separate and unchanged.

**Audit findings recorded (nothing hidden):**
- Fixed and pushed (962d4b7): Wi-Fi resume fix aborting when `brcmfmac` is already unloaded; `mseries-power` ordering cycle.
- Open: DNS-logger polkit rule `49-mseries-netusage.rules` probably not installed in `/etc/polkit-1/rules.d` (a password helper still fires every ~10 min since `netusage` started 15:14; `rules.d` is unreadable without root so unconfirmed). Apply with the netusage installer under sudo.
- Open: `user@109` (LightDM greeter) stop timeout because `obexd` ignores SIGTERM.
- Open: `mseries-verify` is not installed on this Mac (`mseries/local-ai/install-verify.sh` puts it in `~/.local/bin`; not present). Run it to get the status robot back.
- Benign log noise: systemd-growfs LUKS resize "Operation not permitted" on /home (filesystem still grew), gkr-pam control file, wpa_supplicant P2P interface -52, tas2764 devicetree parse on two amps, dp-phy -517 deferrals.
- Feature requests logged: True Tone-like display (see above).

Next: install the polkit rule and confirm prompts stop for 30 minutes, install `mseries-verify`, then the `obexd` greeter timeout.

### Verify robot installed; false failure fixed — 2026-10-14

Ran `bash mseries/local-ai/install-verify.sh` (user-level, no sudo): `~/.local/bin/mseries-verify` now exists. Its first run reported `speakersafetyd-active` as failed although the daemon was active: the check grepped the last 40 journal lines for "Sample rate", but the log now says "PCM rate" and a suspend warning pushed it out of the window. The check in `verify-checks.json` now searches the whole boot for either phrase. Status after: 6 passed, 4 ask (owner looks), 10 waiting, 0 failed.

## Watchlist, edge lane and Rust plan — 2026-10-14

- Added `mseries/local-ai/people-watch.py` + `people-watch.json` (13 projects from Omarchy's "Introducing Omarchy M" post plus Tether, BlueFerry, OpenBubbles, iCloud clients), a `upstream-people-watch` verify check, an installer line, and `test_people_watch.py` (passes). Baseline recorded on this Mac. Documented in `mseries/WATCHLIST.md`. Finding: Tether v0.2.38 exists; we pin v0.2.37.
- Added `mseries/EDGE-AND-RUST-PLAN.md`: a 24-hour detect/build/smoke-test lane that does NOT auto-deploy kernel or bootloader changes to the Mac, and a ranked Rust port plan (privileged root helpers and the DNS logger first; installer shell and Vala patches stay). Not started.
- Not done: no CI edge job, no Rust code yet.

### Lead: omarchy-mx-mac and the Aurora kernel — 2026-10-14

Read `maralcbr/omarchy-mx-mac` (README, releases, commits, changelog; read-only). It is feature-frozen; active work is in `omacom/omarchy-mac` (`quattro-upstream`) and `omacom/omarchy-mac-installer`. Its new images use the Aurora kernel (`aurora-silicon/linux`), which it reports as hardware-qualified on the 14-inch M1 Pro. Watchlist updated (15 projects, baseline re-acknowledged). Next: compare Aurora with our fairydust-usb4 kernel on dock USB4, suspend and video (VM/edge lane first, no change to the Mac's kernel or bootloader), and read their LUKS and s2idle work against ours. See `mseries/WATCHLIST.md`.

## Mac installer adoption — 2026-10-14

Owner: "ensure our installer copies" `omacom/omarchy-mac-installer`. Studied it read-only (Swift app + privileged helper + Asahi installer engine + signed catalog + image producer; MIT). Wrote `mseries/MAC-INSTALLER-PLAN.md` (what it is, adoption steps, phases, blockers). Nothing imported or built: this Mac has no Swift/Xcode/macOS, and signing needs an Apple Developer ID. The current `bin/elementary-mac-setup` stays the interim path. Next: owner decisions (where it lives, which Mac builds it, who tests), then Phase 0 (import at a pinned commit, run the portable tests on Linux, write the mkosi payload spec).

### Update 2026-10-14: Mac installer NOT pursued

The owner decided against building the macOS installer. `MAC-INSTALLER-PLAN.md` is marked not pursued and the roadmap item is struck through. Nothing was imported or built. `omacom/omarchy-mac-installer` stays on the watchlist for reference only.

### Watchlist extended; image wiring test fixed — 2026-10-14

- Added the iMessage and iCloud-password projects from our notes (BlueBubbles app and server, rustpush, Bubbles, LiteBubbles, apw, dragosol, passwords-app, deej1721) to `people-watch.json` (24 projects), checked license and activity, baseline re-acknowledged. Note "these new repos" was ambiguous (no links in the request); send links for any others.
- `test-image-wiring.py` failed after the merged commit cecc9fb: the Apple overlay now lists `io.elementary.panel.network` and `io.elementary.quick-settings` but the arm64 liveiso and sysupdate configs did not install them. Added both to those two configs; the test passes. Not built into an image here.
- Marked the launcher and window-button rows in `BUG-FIX-ROADMAP.md` as fixed (owner to confirm).

### Correction: watcher fetch failure — 2026-10-14

The previous entry said the 24-project baseline was acknowledged. It was not: the unauthenticated GitHub limit (60/h) was exhausted by repeated runs, `people-watch.py` swallowed the 403s and re-saved the stale 15-project cache as the baseline. Fixed in `people-watch.py`: a failed entry keeps its previous value and is reported (`--list` prints a WARNING), `--ack` refuses to save a partial baseline (exit 2), and it now uses `GITHUB_TOKEN` or the user's own `gh auth token` (5,000/h; read-only calls to api.github.com). New regression test in `test_people_watch.py`. The real baseline now holds all 24 projects.

### Remaining open fixes worked — 2026-10-14

- **Greeter `obexd` timeout:** root cause found in the journal. The login screen's panel (`io.elementary.wingpanel -g`) D-Bus-activates `obexd`, which then waits on Evolution address-book activation and ignores SIGTERM, so the 5 s `user@109` stop timeout kills it and marks the unit failed (15:47 and 16:33). Added `mseries/install-greeter-obex-fix.sh` (drop-in `TimeoutStopSec=2s`, `--uninstall`, `DESTDIR` for tests) and `mseries/test-greeter-obex-fix.sh` (passes, also added to CI along with `test_people_watch.py`). NOT installed on the Mac: `sudo bash mseries/install-greeter-obex-fix.sh`, then check `systemctl --failed` after the next login. This is a mitigation of the symptom; why obexd hangs is not fixed upstream.
- **Tether pin:** bumped v0.2.37 to v0.2.38 in `install-tether.sh`, `tether/brave-extension.py` and docs. The SHA-256 (`eec88920...57ae`) is the digest GitHub publishes for `tether_0.2.38_arm64.deb`; I did not download the file, and the installer re-verifies it at install time. Source commit `5850727` is the commit behind tag `v0.2.38`. Release content: terminal UI redesign, call button, notification icons; the only Bluetooth-related file changed is ANCS notifications. Tether is still not installed here and messaging still needs BlueZ 5.86.
- **Still needs the owner (sudo):** the DNS-logger polkit rule (`sudo install -Dm644 mseries/netspeed/netusage/49-mseries-netusage.rules /etc/polkit-1/rules.d/49-mseries-netusage.rules`), the Wi-Fi and power fixes from earlier today, and the greeter drop-in above.

### Feature request: universal speech to text — 2026-10-14

Owner: "we are going to need a Siri-like, Whisper-like speech to text, universal on this system." Logged in `ROADMAP.md` (stretch goals) and `BUG-FIX-ROADMAP.md` (P2). Approach to evaluate: local whisper.cpp-class model, push-to-talk, text inserted through an IBus engine so it works in any app; privacy rule: local only, nothing stored by default. Blocker to check first: the built-in microphone path (Omarchy's Asahi mic mapping is not ported). Not started.

### One script for the pending sudo steps

`mseries/apply-pending.sh` (run as your normal user): `--dry-run` prints every command and changes nothing; `--only wifi,power,polkit,greeter`; `--list`. Steps: install the fixed Wi-Fi resume script and load `brcmfmac` if missing, replace the `mseries-power` unit (drops the old multi-user link), install the DNS-logger polkit rule, install the greeter obex drop-in. Backs up any file it replaces to `<file>.pre-mseries`; never touches bootloader, kernel, initramfs or audio. Dry run checked on the live Mac; real run is the owner's.
Facts checked for the speech-to-text request: the session is Wayland (Pantheon), IBus 1.5.34 is installed (so an IBus engine is viable), and ALSA lists a capture device `MacBook Pro J314 High-Power Audio Interface [aop_audio]`; whether it records usable speech is not yet tested. `pactl` is not installed here.
## Atomic app prototype — 2026-10-14

Added `atomic-app.py` with per-app writer locking, prepared release staging,
synced release/generation files, atomic selector activation, retained history,
status and explicit rollback. Its run command pins the resolved release path
before execution. A directory-sync error after selector replacement is reported
as an activated app with unconfirmed durability, rather than a false claim that
activation did not occur. Newly created store ancestors are also synced.

`install-signal.sh --atomic` is the first opt-in integration. The existing
publisher-signature check precedes extraction/staging; the installed CLI and
desktop launcher route through the selected release, and the icon follows it.
Legacy installation files are retained. Default installs still use the existing
path. No live app/profile was migrated during development.

Validation: all nine `test-atomic-app.py` cases pass, covering rollback,
concurrent updates, interrupted copying, failed selector replacement, sync
failure after replacement, launch-path pinning, parent durability, unsafe links
and invalid entrypoints. The existing extracted Signal tree passes read-only
staging validation; installer shell syntax and whitespace checks pass. Desktop
launch/data-migration qualification, automatic health recovery, cleanup and the
Flatpak/Nix comparison remain open in issue #50.

## Owner roadmap: upstream integration, then Rust — 2026-10-14

The owner supplied the Introducing Omarchy M announcement and explicitly set
the sequence: follow its people/projects, integrate the code into this port,
then convert the maintained implementation to Rust for performance. Added
`OMARCHY-M-ROADMAP.md` and `upstreams/omarchy-m.json` with seven observed public
repository branches/revisions, GitHub license metadata, and unresolved source
discovery areas. These are tracking baselines, not changed build pins.

Verified refs through the GitHub API, including the installer (00489dd),
Try Omarchy (afd4f2d), M2 Air DP-Alt-Mode (50b80f4) and MLX (9ab220f).
The M2 Air DTB is not an M1 Pro DTB; MLX's M1 Pro GPU/ANE table is untested;
the announcement's M1/M2 compatibility list is a target. Softened the older
categorical Touch ID absence claim: compatible public source has not been
obtained/verified. Missing code remains an integration task.

The roadmap inventories every applicable component, source/license, model,
elementary translation and qualification evidence before the broad Rust phase.
The Rust phase preserves interfaces/recovery and measures performance against
the integrated baseline. Third-party kernel/firmware/Pantheon feasibility must
be recorded explicitly. No Rust rewrite or driver import happened in this batch.
Created the active daily 10:00 America/New_York heartbeat
`follow-omarchy-m-sources` for read-only source tracking with notifications only
for meaningful actionable changes. JSON parsing and `git diff --check` pass.

## GitHub upstream monitoring — 2026-10-14

`Watch public upstreams` runs every six hours and on demand. It combines
`local-ai/people-watch.json` subscriptions with the explicit branches in
`upstreams/omarchy-m.json`, and maintains one issue with pending revisions,
release changes and fetch failures. Closing the issue acknowledges observations;
new changes reopen it. Failed fetches preserve the last successful observation
and fail the Action. No upstream code is automatically merged or deployed.
The native macOS installer remains reference-only, per the owner decision.

Activated on main: [upstream dashboard #51](https://github.com/techmore/ElementaryOS_MSeries/issues/51).
First Action run 38640456586 completed successfully. The duplicate Codex
heartbeat `follow-omarchy-m-sources` is PAUSED. Review covered initial audited
revision comparison, missing user sources, and trusted dashboard authors.
No new automated tests were run for this watcher.

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


### Battery drain, phone tether, minimum brightness — 2026-10-14

- **Battery:** on battery the M1 Pro drew 12.9 W with the screen at 105/500 and the CPU 87% idle. The WirePlumber no-suspend rule (`session.suspend-timeout-seconds = 0`, from Omarchy, applied when PipeWire restarted at 17:35) kept the speaker stream RUNNING while idle. A user-level override of 30 s closed the stream and the draw fell to 11.7 W (about 1.2 W); `mseries/audio/asahi-audio-no-suspend.conf` now defaults to 30 s. Possible cost: a pop after 30 s of silence. Still unexplained: about 11.7 W total, with AOP mailbox interrupts about 460/s each, SPI HID about 1000/s and busy Electron apps. The power-profile code is working, so the Rust battery-profile migration (owner's idea) is not expected to fix this alone; it stays on the plan and will be judged by before/after power readings.
- **Phone tether:** bug logged with the observed disconnect at 17:39:26 and the unmanaged/no-lease NetworkManager sequence; symptom details still needed from the owner.
- **Minimum brightness:** panel floor is 5/500 (1%); needs the owner's look. See `BUG-FIX-ROADMAP.md`.
- Applied on this Mac without sudo: user-level WirePlumber override only (reversible).

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

### Watt meter in the menu bar; ETA patch repaired; power-draw probe — 2026-10-14

- **Watt meter (owner request):** `mseries/patches/panel-power-watts.patch` adds a live power label (UPower `EnergyRate`, e.g. `12.1 W`, charging or discharging, hidden below 0.1 W) beside the battery icon in elementary's Power indicator. Applied after the ETA patch by `install-battery-eta.sh`. Verified in a scratch tree at `elementary/panel-power` e05723d: both patches apply in order and the indicator compiles to `libpower.so` (valac 0.56.19; the unused `libgtop-2.0` meson dependency was dropped in scratch only because `libgtop2-dev` is not installed here). NOT installed and not seen in the panel: it needs `sudo apt install libgtop2-dev ...` and a module replace + Wingpanel restart. Run `bash mseries/apply-pending.sh --dry-run --only wattmeter`, then without `--dry-run`. Undo: `bash mseries/install-battery-eta.sh --uninstall`.
- **Bug found and fixed:** the old `panel-power-charge-eta.patch` had zero-context hunks; current `git apply` put them after the end of the class in `DisplayWidget.vala`, which cannot compile, so the battery-ETA installer would have failed on a rebuild. Regenerated with context.
- **Power-draw investigation (in progress):** baseline on battery 12.79 W (min 11.62, max 15.02, 15 samples/30 s), screen 105/500, CPU about 87% idle. Interrupt rates per second: DCP mailbox `38bc08000.mbox-recv` 479, mailbox `406408000.mbox-recv` 385, SPI HID `39b10c000.spi` 228 (it read about 1000 earlier, so it follows touching the keyboard/trackpad), Wi-Fi PCIe 60. The `38bc08000` mailbox belongs to the display coprocessor, so Gala/compositor redraws are a suspect. One-change-at-a-time tests are not done yet.

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
