# Repository ownership (phase 1: one writable source per app)

Status 2026-10-27. Implements the first step of [REPOSITORY-TOPOLOGY.md](REPOSITORY-TOPOLOGY.md):
apps now live in [`techmore/mseries-sdk-apps`](https://github.com/techmore/mseries-sdk-apps)
(compared at `origin/main` `40d4445c4414e83da5893500528e088ec599af30`). The OS repo still
holds older duplicate copies. Those are now **frozen migration snapshots**: nothing is
deleted, moved or archived, but PRs that edit them fail the `Frozen paths guard` CI check
(label `allow-frozen-edit` overrides). The guarded list is
[`ci/frozen-paths.txt`](ci/frozen-paths.txt); each frozen directory has a `FROZEN.md`.
Branch rules: [BRANCHING.md](BRANCHING.md). Functional duplicates (Python/Rust/Vala twins, duplicate
launchers) are marked, not removed, in [LEGACY-DUPLICATES.md](LEGACY-DUPLICATES.md).

Method: real trees compared with `diff -rq` between `git archive origin/main` of the SDK repo
and this checkout (`dev` at `7478f2fe`). Phase 2 (kernel split) is owned by another session;
Kernel rows are only tagged.

## Apps already owned by the SDK repo (frozen here)

| Path in OS repo | SDK repo state |
| --- | --- |
| `rust/claude-pantheon-rs` | **Newer** in SDK (plugin registry; 6 files only in SDK, 7 changed) |
| `rust/mseries-messages` | **Newer** in SDK (Signal channel, `signal.rs`; 5 files changed) |
| `rust/mseries-pantheon-kit` | **Newer** in SDK (diff timeline, `timeline.rs`; `lib.rs` changed) |
| `mseries/battery` | One test file differs (`test_battery_enhance.py`); reconcile in SDK |
| `mseries/diskspace-app` | Identical except `test.sh` |
| `mseries/phone-setup` | Identical (SDK tree has a stray `__pycache__`; remove there) |
| `rust/granite-smoke`, `msdk`, `msdk-gtk`, `mseries-ai`, `mseries-apple-dev`, `mseries-broker`, `mseries-diskspace`, `mseries-dock`, `mseries-greeter`, `mseries-power`, `mseries-reply`, `mseries-signal-import`, `mseries-system-monitor`, `mseries-update-core`, `mseries-updates` | Identical |
| `mseries/sdk-tests`, `sdk-bench`, `sdk-status-host`, `messages-mcp`, `polybagger-print-manager`, `updates-app`, `fleet-shepherd` | Identical |
| Docs: `APP-BUILDING-GUIDE.md`, `DOCK-SDK-SPEC.md`, `RUST-PANTHEON-SDK.md`, `RUST-PANTHEON-CLIENTS.md`, `SDK-*.md` (13 files) | Identical (guarded by path; no banner added) |

Caveats: `mseries-update-core` still bundles the OS-owned root helper with the app-facing
contract, and `mseries-power` backs the OS power policy. Both are frozen per the plan; use the
label for helper/policy changes until the contract split in REPOSITORY-TOPOLOGY.md lands.
Also identical but not frozen (decide in later phases): `BATTERY-ETA.md`, `BATTERY-PROFILER.md`,
`MESSAGES-PARITY.md`, `MESSAGING-STATUS.md`, `install-battery*.sh`, `install-phone-setup.sh`,
`install-messaging-bluez.sh`.

## SDK-only (nothing to freeze here)

`rust/mseries-image-studio`, `mseries/image-studio`, `rust/torrential`. In flight: Signal Pantheon as
`mseries/signal-pantheon` (SDK PR #14). SDK `rust/Cargo.toml` lists `mseries-image-studio` and
drops `pantheon-compositor`; the OS workspace keeps the compositor, so the two `Cargo.toml` /
`Cargo.lock` files are intentionally independent and not frozen.

## Exists only in the OS repo: candidates to import (not imported now)

| Path | Note |
| --- | --- |
| `mseries/claude-pantheon-native` | C/Meson client; SDK has the Rust `claude-pantheon-rs` only |
| `mseries/torrential-native`, `mseries/TORRENTIAL-PORT.md` | SDK imported `rust/torrential` with history (#15); confirm what native/port material is still needed |
| `mseries/signal-wingpanel`, `signal-launcher.sh`, `install-signal*.sh`, `SIGNAL-PANTHEON-DESIGN.md` | Signal Pantheon moves with SDK PR #14; deferred per MESSAGING-STATUS.md |
| `mseries/smart-reply`, `SMART-REPLY-DESIGN.md`, `install-smart-reply.sh` | Pairs with `rust/mseries-reply` |
| `mseries/tether`, `TETHER-CONTINUITY.md`, `omdrop*`, `orchard*`, `horizon-rdp`, `opencode-desktop` | Standalone apps; classification needs an owner decision |

## Classification of the rest of `rust/` and `mseries/`

| Class | Paths |
| --- | --- |
| OS (stays) | `rust/pantheon-compositor` (SDK keeps only the vendored protocol XML; its drift check treats this repo as source of truth), `pantheon-rust-compositor`, `gala-*`, `window-*`, `dock-*`, `docked-lid`, `quick-settings`, `panel*`, `wingpanel-tests`, `*-wingpanel` and `install-*wingpanel*` (clockright, codexbar, repobar, share-eyes, t3, troubleshooter), `codexbar*`, `repobar*`, `theme`, `desktop-notifications`, `dark-mode`, `display-*`, `brightness`, `keyboard-backlight`, `audio`, `airplay`, `power`, `touchid-settings`, `icloud-passwords`, `image-actions`, `screenshot-shelf`, `work-mode`, `ui-scale`, `netspeed`, `update`, `releases`, `release`, `debs`, `packages.arm64`, `patches`, `customizations`, `minimal-system`, `enhance*`, `user-enhance.sh`, `post-install.sh`, `validate.sh`, `ci`, remaining `install-*.sh`, `lib-*.sh`, `test-*`, `machine-lab`, `vms`, `muvm-source.sh`, `modrun.py`, `maintenance`, `procedures`, `tools` |
| Kernel (phase 2, other session) | `aurora`, `aurora-sep`, `aurora-touchid*`, `AURORA-SECOND-BOOT.md`, `boot`, `fairydust`, `hardware`, `lid-trace`, `KERNEL-*.md`, `check-kernel-config.py`, `test-kernel-config.py`, `install-initramfs-crossbar.sh`, `install-boot-isolation.sh`, `USB-C-DOCK-DP-ALT-MODE.md`, `FIRMWARE-WIFI.md`, `upstream`, `upstreams`, `upstream-audits`, `UPSTREAM-PINS.md` |
| Hub / docs | All other top-level `*.md` (ROADMAP, OS9-HANDOFF, BRANCHING, REPOSITORY-TOPOLOGY, PORT-MAP, audits, designs, runbooks), `receipts`, `benchmarks`, `local-ai`, `dictation`, `docs/` and the Pages site |

The Kernel and OS lists are grouped by name and judgment, not by exhaustive file audit; items
that fall between classes should be settled in phase 2 or later.

## Where to edit

| You are changing | Edit in |
| --- | --- |
| Anything listed under "already owned by the SDK repo" | `techmore/mseries-sdk-apps` |
| Compositor, panel, installers, packaging, OS services | this repo |
| Kernel/boot | this repo until phase 2 lands |

Cutover revision recorded in every `FROZEN.md`: `mseries-sdk-apps@40d4445c4414e83da5893500528e088ec599af30`.

## Removed from this repo (2026-10-27)

`rust/mseries-diskspace`, `rust/mseries-updates`, `rust/mseries-power`, `rust/granite-smoke`,
`mseries/diskspace-app` and `mseries/updates-app` (with their two CI workflows and `validate.sh` checks) were
deleted here; the source of truth is `techmore/mseries-sdk-apps`. Still here: `rust/mseries-update-core`
(`mseries-pantheon-kit` depends on it and it holds the OS-owned root helper) and `rust/claude-pantheon-rs`
(`rust/msdk` tests, `msdk.yml` and `mseries/sdk-tests` read its `sdk/t3.*` files; remove it together with `msdk`).
