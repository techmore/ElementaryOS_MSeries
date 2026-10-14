# Documentation index

Everything in `mseries/`, grouped by what you are trying to do. Work in progress: the installer and the
enhancement layer are the current focus, the factory-ISO documents describe an unverified path.

## Installing and recovering (start here)

| Document | What it covers |
|---|---|
| [REINSTALL-RUNBOOK.md](REINSTALL-RUNBOOK.md) | Wipe, reinstall with `elementary-mac-setup`, what to expect, what to bring back if it fails |
| [BACKUP-AND-REINSTALL.md](BACKUP-AND-REINSTALL.md) | Backing up before a reinstall |
| [POST-BOOT-CHECKS.md](POST-BOOT-CHECKS.md) | Checklist after the first boot (trackpad, Wi-Fi, keys, display, video) |
| [DESKTOP-SETUP.md](DESKTOP-SETUP.md) | Desktop tweaks, shortcuts, optional extras |
| [FIRMWARE-WIFI.md](FIRMWARE-WIFI.md) | Wi-Fi firmware provisioning |
| [USB-C-DOCK-DP-ALT-MODE.md](USB-C-DOCK-DP-ALT-MODE.md) | External displays through a dock |

## How it works

| Document | What it covers |
|---|---|
| [TRANSFORM-DESIGN.md](TRANSFORM-DESIGN.md) | Design and safety contract of the in-place cut-over (`transform/elementary-grow.sh`) |
| [KERNEL-FLOW.md](KERNEL-FLOW.md) | How the Asahi kernel, initramfs and GRUB boot elementary |
| [STORAGE-PLAN.md](STORAGE-PLAN.md) | Partition and subvolume layout |
| [PORT-MAP.md](PORT-MAP.md) | Which omarchy-mac fixes were ported to Ubuntu/Pantheon, and what is out of scope |
| [UPSTREAM-PINS.md](UPSTREAM-PINS.md) | Pinned upstream revisions and licences |

## Kernel

| Document | What it covers |
|---|---|
| [KERNEL-REPORT.md](KERNEL-REPORT.md) | Kernel verdict |
| [KERNEL-SOURCE.md](KERNEL-SOURCE.md) | Where the kernel source comes from |
| [fairydust/debian/README.md](fairydust/debian/README.md) | The patched kernel package (USB4, Apple Video Decoder fix) and how it is built |
| [fairydust/usb4/CUTOVER.md](fairydust/usb4/CUTOVER.md) | Verified M1 Pro USB4 kernel, dock results, limits and recovery pointers |

## Status and planning

| Document | What it covers |
|---|---|
| [OS9-HANDOFF.md](OS9-HANDOFF.md) | Latest state, audit notes, verification results, blockers, next task |
| [ROADMAP.md](ROADMAP.md) | Open problems and stretch goals |
| [OMARCHY-M-ROADMAP.md](OMARCHY-M-ROADMAP.md) | Owner sequence: follow Omarchy M sources, integrate and qualify code, then migrate to Rust with measurements |
| [ATOMIC-APP-DEPLOYMENT.md](ATOMIC-APP-DEPLOYMENT.md) | Requested atomic app updates, rollback, apt performance investigation and Flatpak/Nix evaluation |
| [BUG-FIX-ROADMAP.md](BUG-FIX-ROADMAP.md) | Upstream comparison and prioritised bug backlog |
| [OMARCHY-AUDIT-2026-10.md](OMARCHY-AUDIT-2026-10.md) | Audit of omarchy-mac |

## Factory ISO and VMs (unverified on hardware)

| Document | What it covers |
|---|---|
| [FIRST-ISO-BUILD.md](FIRST-ISO-BUILD.md), [LOCAL-BUILD.md](LOCAL-BUILD.md), [BUILD-NOTES.md](BUILD-NOTES.md) | Building the image |
| [VM-SMOKE-TEST.md](VM-SMOKE-TEST.md), [KVM-VMS.md](KVM-VMS.md), [MACOS-VM.md](MACOS-VM.md) | Testing in virtual machines |

## Build reviews and reports (history)

[BUILD-38396499561-REVIEW.md](BUILD-38396499561-REVIEW.md), [BUILD-ERROR-REVIEW-2026-10-13.md](BUILD-ERROR-REVIEW-2026-10-13.md),
[OPENCODE-BUILD-REPORT.md](OPENCODE-BUILD-REPORT.md), [ICONIDENTIFY-REPOSITORY-REVIEW.md](ICONIDENTIFY-REPOSITORY-REVIEW.md),
[JOSHUA-REPOSITORY-REVIEW.md](JOSHUA-REPOSITORY-REVIEW.md).
