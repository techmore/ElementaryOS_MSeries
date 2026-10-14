# OS 9 implementation / Claude Code handoff

Updated 2026-10-13. Repository: techmore/ElementaryOS_MSeries.

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

## Network speed readout persistence — 2026-10-13

The user's panel-speed setting was already enabled, but the plugin had been
installed by replacing `libnetwork.so` in the current `/usr` image. A reboot or
OS image deployment restored the stock file. The Apple Silicon mkosi image now
builds pinned `elementary/panel-network` commit
`8685ec8e55a45e48da0c12931a353cd440d11664`, applies the three tracked network
patches, and places the resulting module into the overlay consumed by both
liveiso and sysupdate. The build checks that the target package remains 8.0.1.x.
`test-image-wiring.py --image-output` now checks the plugin is present in the
final liveiso tree; the sysupdate configuration consumes the same overlay. The
local installer remains useful for the current image, while the new image
build makes the change survive redeployments and image updates.

Validation: `just mkosi summary` parsed the new build script and confirmed
network access is enabled for image build scripts. Running
`build-network-indicator` against the matching host package compiled the
patched module into a temporary stage; the output contained only the
321848-byte `libnetwork.so` and its panel-speed toggle marker. `bash -n` and
`git diff --check` passed. No full image build has run yet. Next: run the
M-series validation workflow, then the full arm64 image build and post-build
module check before deploying the resulting image. The working desktop has the
patched module installed and `~/.config/mseries/network-speed.ini` enables the
panel readout.

## Local general agent continuation (October 13)

Crush v0.98.1 ARM64 is installed from a checksum-pinned release, with an
isolated Local Agent workspace, Applications launcher and native robot-menu
entry. `local-ai/install-agent.sh` reproduces it. Qwen3.5-9B 4-bit answered a
short loopback API request and emitted a structured synthetic tool call on
this M1 Pro. The first full Crush prefill exhausted GPU scratch; the private
server now uses 256-token prefill chunks via `configure-prefill.py`, and a full
Crush answer completed. The final profile admits 32k context and one prompt
cache (8.93 GiB estimate, not measured peak); use catalog ID to retain KV facts.
The user explicitly requested killing the port conflict: whop2p is stopped
and disabled at login. The model is an on-demand user service, not enabled
at login. NAS address/share path remains pending; no NAS writes occurred.
ANE artifacts were already staged and remain unactivated. No kernel, device
tree, bootloader or audio changes were made. See local-ai/README.md and the
October 13 agent receipt for final verification and remaining scope.

## 2026-10-14 hardware session

Dock verified (Dell WD22TB4: hub, mouse, Ethernet; no display). Lid-open
resume works without a dock but the login screen needs a power-button press;
the dock Ethernet icon is recreated on each connect. Both are recorded in
BUG-FIX-ROADMAP.md with evidence and are not fixed. Running code that was only
in PR #1 (docked lid mode, troubleshooter, netspeed) is now being merged to
main so the repository matches the installed system. Next: trace a resume,
add the Realtek firmware and a pinned profile, repeat the docked lid-close test.


## Asahi root expansion planning — 2026-10-14

Documented the reported 112 GiB free gap before Asahi p3/p4/p5 and a checkpointed proposal in [`STORAGE-PLAN.md`](STORAGE-PLAN.md) and [`procedures/ROOT-EXPANSION.md`](procedures/ROOT-EXPANSION.md). No disk or filesystem operations were run. The gap's origin and current sector layout still need verification; Asahi guidance limits disk changes to free space prepared by its installer. Next: collect the runbook's read-only preflight output, verify backup/recovery readiness, and review the exact target before any proposed write. The factory ISO remains unqualified on Apple hardware.

## 2026-10-14 pre-reinstall backup

Backup and reinstall notes are in `BACKUP-AND-REINSTALL.md`; the script is `backup/mseries-backup.sh`. A 334 MB staging copy was written and checksum-verified on the same disk. It still has to be copied off the machine (no external destination was mounted). No bug fixes were attempted. Next: copy the backup off, review `~/Downloads`, then reinstall.
