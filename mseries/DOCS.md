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
| [Work Mode panel](work-mode/README.md) | Native System Settings toggle, Blue Flow work wallpaper, and weekday schedule |
| [FIRMWARE-WIFI.md](FIRMWARE-WIFI.md) | Wi-Fi firmware provisioning |
| [USB-C-DOCK-DP-ALT-MODE.md](USB-C-DOCK-DP-ALT-MODE.md) | External displays through a dock |

## Power, battery and dock investigations

Start with the [power documentation map](power/README.md) for current evidence, branch ownership and next steps.

| Document | What it covers |
|---|---|
| [POWER-ROADMAP.md](POWER-ROADMAP.md) | Canonical priorities, goals, gates and verification plan |
| [power/macos-baseline/README.md](power/macos-baseline/README.md) | Collect matching macOS/Linux scenarios and update the checklist |
| [power/macos-baseline/PARITY.md](power/macos-baseline/PARITY.md) | Generated comparison: 11 categories, 52 items |
| [power/macos-baseline/results/README.md](power/macos-baseline/results/README.md) | Retained runs and their limits |
| [POWER-OPPORTUNITIES-2026-10-16.md](POWER-OPPORTUNITIES-2026-10-16.md) | Dated Linux power observations |
| [power/DYNAMIC-REFRESH-AUDIT.md](power/DYNAMIC-REFRESH-AUDIT.md) | Dynamic refresh investigation and experimental patch |
| [power/README.md#dock-hdmi-and-suspend](power/README.md#dock-hdmi-and-suspend) | Newer dock branch frontier, older diagnosis and sleep implications |

## How it works

| Document | What it covers |
|---|---|
| [TRANSFORM-DESIGN.md](TRANSFORM-DESIGN.md) | Design and safety contract of the in-place cut-over (`transform/elementary-grow.sh`) |
| [KERNEL-FLOW.md](KERNEL-FLOW.md) | How the Asahi kernel, initramfs and GRUB boot elementary |
| [STORAGE-PLAN.md](STORAGE-PLAN.md) | Partition and subvolume layout |
| [PORT-MAP.md](PORT-MAP.md) | Which omarchy-mac fixes were ported to Ubuntu/Pantheon, and what is out of scope |
| [UPSTREAM-PINS.md](UPSTREAM-PINS.md) | Pinned upstream revisions and licences |
| [PLATFORM-PLAN.md](PLATFORM-PLAN.md) | Proposal: split into kernel/display/wm/SDK repos, an SDK a small model can build apps with, pipeline and phases |
| [ARCH-REBASE-PLAN.md](ARCH-REBASE-PLAN.md) | Decision and phased plan to rebase the platform on Arch Linux (Asahi Alarm): what gets simpler, caveats, decisions |
| [ASAHI-ALARM-AUDIT-2026-10-23.md](ASAHI-ALARM-AUDIT-2026-10-23.md) | Audit of the Asahi Alarm base: maintainers, repo address, versions vs upstream, cadence, risks |
| [MINIMAL-SYSTEM.md](MINIMAL-SYSTEM.md) | Layered minimum system: every package mapped to Arch/Asahi/ours/drop with why and the leanest form; Rust Pantheon replacement order |
| [SDK-PARITY.md](SDK-PARITY.md) | Frozen baselines (T3 original, Signal, Image Studio), unified standards, the parity score and the LLM pass loop |
| [GTK-PERFORMANCE-ASAHI.md](GTK-PERFORMANCE-ASAHI.md) | What keeps GTK4/Granite apps small and idle on Asahi (renderer, CSD shadow, cursor blink, animations, D-Bus), with every GTK app here listed |
| [DEV-HYGIENE.md](DEV-HYGIENE.md) | Keeping the dev machine clean: the weekly `dev-clean` timer (build output, caches, session scratch, dated Codex exports), one shared cargo target dir, worktree discipline |
| [SMART-REPLY-DESIGN.md](SMART-REPLY-DESIGN.md) | Design only: a window-aware agent that drafts replies in any app (Tab inserts, Esc discards), what it reuses from dictation and the SDK, safety rules, and a scoped first slice |
| [SDK-AGENT-SURFACE.md](SDK-AGENT-SURFACE.md) | Design only: SDK apps declare intents, entities, scopes and risk classes (like Apple's App Intents and entitlements); `msdk` validates them and generates the MCP manifest; the broker enforces user grants |

## Kernel

| Document | What it covers |
|---|---|
| [KERNEL-REPORT.md](KERNEL-REPORT.md) | Kernel verdict |
| [KERNEL-SOURCE.md](KERNEL-SOURCE.md) | Where the kernel source comes from |
| [fairydust/debian/README.md](fairydust/debian/README.md) | The patched kernel package (USB4, Apple Video Decoder fix) and how it is built |
| [fairydust/usb4/DOCK-CODE-REVIEW.md](fairydust/usb4/DOCK-CODE-REVIEW.md) | Dock code review, fixture tests, reproducible patch/DT validation and hardware limits |
| [fairydust/usb4/CUTOVER.md](fairydust/usb4/CUTOVER.md) | Verified M1 Pro USB4 kernel, dock results, limits and recovery pointers |
| [aurora-sep/README.md](aurora-sep/README.md) | Optional Aurora SEP kernel lane: Touch ID via the Secure Enclave |

## Status and planning

| Document | What it covers |
|---|---|
| [OS9-HANDOFF.md](OS9-HANDOFF.md) | Latest state, audit notes, verification results, blockers, next task |
| [ROADMAP.md](ROADMAP.md) | Open problems and stretch goals |
| [OMARCHY-M-ROADMAP.md](OMARCHY-M-ROADMAP.md) | Owner sequence: follow Omarchy M sources, integrate and qualify code, then migrate to Rust with measurements |
| [rust/README.md](rust/README.md) | Rust branch scope, per-project register, parity contract, and daily/weekly upstream update rhythm |
| [rust/mseries-power/README.md](rust/mseries-power/README.md) | First isolated Rust candidate and its parity and rollout gates |
| [rust/wifi-resume/README.md](rust/wifi-resume/README.md) | Apple Silicon Wi-Fi resume recovery Rust candidate and parity gates |
| [ATOMIC-APP-DEPLOYMENT.md](ATOMIC-APP-DEPLOYMENT.md) | Requested atomic app updates, rollback, apt performance investigation and Flatpak/Nix evaluation |
| [UPDATER-DESIGN.md](UPDATER-DESIGN.md) | Customer update mechanism: signed repo, channels, staged apply at next login, automatic rollback, owner decisions |
| [BUG-FIX-ROADMAP.md](BUG-FIX-ROADMAP.md) | Upstream comparison and prioritised bug backlog |
| [OMARCHY-AUDIT-2026-10.md](OMARCHY-AUDIT-2026-10.md) | Audit of omarchy-mac |
| [UPGRADE-SURVEY-2026-10-18.md](UPGRADE-SURVEY-2026-10-18.md) | Pinned-vs-latest upgrade table, Aurora Silicon release lanes, upstream and own WIP branch merge recommendations |

## Factory ISO and VMs (unverified on hardware)

| Document | What it covers |
|---|---|
| [FIRST-ISO-BUILD.md](FIRST-ISO-BUILD.md), [LOCAL-BUILD.md](LOCAL-BUILD.md), [BUILD-NOTES.md](BUILD-NOTES.md) | Building the image |
| [VM-SMOKE-TEST.md](VM-SMOKE-TEST.md), [KVM-VMS.md](KVM-VMS.md), [MACOS-VM.md](MACOS-VM.md) | Testing in virtual machines |

## Build reviews and reports (history)

[BUILD-38396499561-REVIEW.md](BUILD-38396499561-REVIEW.md), [BUILD-ERROR-REVIEW-2026-10-13.md](BUILD-ERROR-REVIEW-2026-10-13.md),
[OPENCODE-BUILD-REPORT.md](OPENCODE-BUILD-REPORT.md), [ICONIDENTIFY-REPOSITORY-REVIEW.md](ICONIDENTIFY-REPOSITORY-REVIEW.md),
[JOSHUA-REPOSITORY-REVIEW.md](JOSHUA-REPOSITORY-REVIEW.md).
