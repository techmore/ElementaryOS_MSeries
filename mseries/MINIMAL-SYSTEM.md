# Minimal system: what is needed, why, and who owns it (Arch rebase, Phase B)

Status: **proposal, 2026-10-23. Nothing implemented.** Data: [minimal-system/packages.tsv](minimal-system/packages.tsv)
(460 packages, one row each, regenerate with `minimal-system/build-inventory.py`). Companion to
[ARCH-REBASE-PLAN.md](ARCH-REBASE-PLAN.md) and [PLATFORM-PLAN.md](PLATFORM-PLAN.md).

The owner's steer: do not just port the Ubuntu list to Arch. Use the rebase to **decide what the system is**, keep it as small and
fast as it can be, and point development at the **Rust Pantheon and custom display stack**. This document does that by organising the
system in layers and giving every package an owner and an action.

## 1. Decision frame: consume, wrap, replace, drop

| Action | Meaning | Count | Installed today |
|---|---|---:|---:|
| **consume** | Take it from Arch Linux ARM or Asahi Alarm unchanged | 117 | 210 MB |
| **wrap** | Take it for now, with our patches or config; has a planned replacement | 33 | 24 MB |
| **replace** | Our Rust code is (or becomes) the implementation | 4 | 156 MB |
| **implicit** | Library pulled in by pacman dependencies; never listed by hand | 78 | 74 MB |
| **optional** | Install on demand, not in the base image | 40 | 1,564 MB |
| **build-only** | Compilers, headers, test tools: SDK build container, never on a user machine | 112 | 1,145 MB |
| **drop** | Ubuntu/Debian-only, duplicated or redundant | 76 | 3,106 MB |

Of 6.3 GB installed across these packages, **about 4.3 GB is dropped or build-only**, and 1.6 GB is optional. The base the user
actually needs is small: about 460 MB across consume, wrap, replace and implicit.

## 2. Layers

```
L5 build      SDK build container: gcc, clang/LLVM, headers, test tools          (never in the image)
L4 apps       SDK-built Rust apps; third-party (Brave, Firefox, Signal); optional tools
L3 shell      panel, dock, launcher, settings, notifications, greeter, indicators   REPLACE IN RUST, piece by piece
L2 display    compositor, KMS/atomic, EDID, hotplug, input, session                 OURS (mseries-wm + mseries-display)
L1 base       Arch base: systemd, storage, network, audio, power, fonts             CONSUME, trimmed
L0 hardware   Asahi: kernel, m1n1, U-Boot, firmware, speaker safety, GPU userspace  CONSUME, never rewrite
```

### L0 hardware: consume, never rewrite
Asahi Alarm supplies `linux-asahi`, `m1n1` 1.9.9, `uboot-asahi`, `grub`, `asahi-fwextract`, `asahi-audio`, `alsa-ucm-conf-asahi`,
`speakersafetyd`, `tiny-dfr`, `avd-fw`, `asahi-btsync/wifisync/nvram/bless`. **The Mesa question from the audit is resolved:** the Asahi
GPU driver ships in Arch Linux ARM's own `mesa` and `vulkan-asahi` (both `26.2.5` in `extra`), not in Asahi Alarm's repo (which only
adds `mesa-dummy` and FEX overlays). Our own `linux-aurora` kernel becomes a PKGBUILD in `mseries-kernel`. Speaker protection is not
negotiable and not trimmable.

### L1 base: consume, trimmed
Arch `base` replaces Debian's plumbing (76 packages dropped). Keep `sudo-rs`. Two coreutils variants are installed today
(rust-coreutils and GNU); pick GNU unless a benefit is shown. Fonts: keep Liberation and Noto emoji; drop unifont (32 MB), FreeFont,
IPA, Thai and X11 bitmap fonts. `dkms` is not needed because modules ship with the kernel package.

### L2 display: ours, and already running
The live session is `pantheon-rust-wayland`: it runs **`pantheon-compositor` (our Smithay compositor), not Gala**. So the custom display
stack is not a plan, it is the current daily driver. What Arch provides underneath it: `libdrm`, `libinput`, `seatd`, `libdisplay-info`,
`wayland`, `libxkbcommon`, Xwayland, `mesa`/`vulkan-asahi`. What we drop: libmutter and Gala (Arch `mutter` is 51.1 against Ubuntu's 50.1, so
the private libmutter patch becomes moot or must be re-checked). Work for `mseries-wm`/`mseries-display`: lift `edid`, `kms_props`,
`link_status`, `flip_retry`, `hotplug` and `display_config` into compositor-agnostic crates, keep the Pantheon shell protocol v2 as the
contract to the shell.

### L3 shell: replace in Rust, in this order
Arch Linux ARM's `extra` has a **65-package `pantheon` group at the versions we run** (Gala 8.6.2, Wingpanel 8.0.4, Granite 7.8.1,
Switchboard 8.0.3, Files 7.3.2, `pantheon-session` 8.1.0). That makes Pantheon on Arch officially packaged for aarch64, which
corrects the "community-maintained" worry in the rebase plan. It is **scaffolding**: boot it first, then replace pieces with SDK
shell surfaces.

Replacement order, from what runs in the live session today (a single snapshot, not a benchmark; no more measuring until a decision
needs it):

| Order | Piece | Why first | Notes |
|---:|---|---|---|
| 1 | **Dock** | Largest shell process seen: ~535 MB PSS, built locally into `~/.local/lib/mseries/dock` | Vala/GTK; the SDK `List`/`Card` vocabulary covers it |
| 2 | **Wingpanel + indicators** | ~379 MB PSS; hosts our patched indicators and Quick Settings | Needs a plugin-free design: indicators become SDK components |
| 3 | **Notifications, polkit agent, settings daemon** | Always running; small, safe to port | Several `mseries-*` daemons already exist (18 processes, ~300 MB): merge into one Rust supervisor |
| 4 | **Applications menu / launcher** | Frequent, simple UI | First SDK-built shell surface |
| 5 | **Settings (Switchboard)** | Many plugs; port the ones we already patched (Work Mode, Display, Touch ID) | Keep upstream plugs until each is rewritten |
| 6 | **Greeter and lock screen** | Security-sensitive; last | Evaluate `greetd` plus a Rust greeter |

### L4 apps
Ours (SDK targets): `claude-pantheon-rs`, Disk Space, Software Updates, Torrential, Quick Notes. Third party stays optional: Brave, Firefox,
Signal. **Do not carry** the Electron duplicates: ChatGPT desktop (1.6 GB installed; ~4.8 GB across 113 processes in the snapshot) and
Claude desktop (~2.3 GB), or the second Chromium (Google Chrome, 434 MB). `claude-pantheon-rs` already replaces the Claude one at ~60 MB.
The Qt stack (`python3-pyqt6`, `qml6-*`, `qt6-wayland`) exists only for the upstream CodexBar desktop and is dropped once the native
indicator replaces it. The libvirt stack (`libvirt-*`, `virt-manager`, `virtinst`) overlaps Incus and is dropped.

### L5 build
All compilers, LLVM/clang (~800 MB), `-dev` headers (112 build-only packages in all) and test tools move into the SDK build container. Nothing here ships to a
user. This is also what keeps the SDK and benchmark runs fast.

### App store: not in the base, but do not block it
No app-store plan is written down in this repository (AppCenter's daemon is deliberately disabled by `install-system-tuning.sh`), so this is
a recommendation, not a record:

- **The base image ships only default apps with native ports** (the SDK-built Rust apps plus the few upstream apps we keep, e.g. Files and Terminal).
  No store daemon, no catalogue service, nothing resident.
- **A store is a later layer that costs almost nothing now if apps stay well-formed.** Every app, ours or ported, is its own package with
  AppStream metainfo, a `.desktop` file and an icon, which `msdk pack` already has to produce. A store is then just a front end (an SDK app) over
  the signed pacman `apps` suite for our apps, plus Flatpak for third-party ones.
- **Native ports first, wrappers never in the base.** A third-party app enters the default set only as a native port; everything else is
  installed on demand from the store layer.
- Decision for later, when the store is designed: one suite or several (`stable`, `dev`, `apps`), and whether Flatpak stays the third-party route.

### Defaults, login and deploying our apps (owner asks, 2026-10-23)

**Default apps.** Ghostty is the default terminal and Herdr the default agent workspace, replacing `pantheon-terminal`.
Neither is in the Arch Linux ARM repos (`ghostty` and `herdr` are absent from `core`, `extra` and `alarm`), so each needs a PKGBUILD of ours
(or an AUR one we adopt), added to Phase B. Ghostty has a GTK4 front end on Linux, so it meets the native-port rule. Herdr is a Rust terminal
multiplexer that tracks coding-agent state (blocked, working, done, idle) and runs inside Ghostty. **Licence check needed before bundling:**
sources disagree on whether Herdr is AGPL-3.0 or Apache-2.0 and on which GitHub repo is canonical
([overview](https://betterstack.com/community/guides/ai/herdr-ai-agent/)); read the repo's `LICENSE` first.

**Login.** A clean, fast login is a greeter we own:

- `greetd` (Arch `extra` 0.10.3) as the login daemon: tiny, PAM-based, no session logic of its own.
- A Rust greeter written on the SDK, shown by our compositor in a greeter mode (no second compositor). One screen: user, password,
  Touch ID, power; nothing else. Same visual language as the unlock screen and lock screen so the three feel like one thing.
- Touch ID and the existing unlock/lock work plug in through PAM; they stay hardware-gated by the owner.
- `lightdm-pantheon-greeter` (Arch `extra`) is the stopgap that boots on day one. It is replaced when the Rust greeter exists
  (shell replacement order, step 6, moves earlier because login is the first thing seen).

**Deploying our apps.** One path, the same for every app we write, and the answer to "we will be updating":

1. `msdk pack` produces a PKGBUILD-built package with `.desktop`, icon, AppStream metadata and a version.
2. CI builds it in a clean aarch64 chroot and publishes to the signed `dev` suite of our pacman repo on merge; `stable` on release.
3. `mseries-update` (the Updates app's backend, switched from apt to pacman) pulls only our repo, takes a btrfs snapshot first, and never
   restarts the shell or compositor mid-session; apps pick up the new version at next launch.
4. Rollback is the snapshot. Dev machines can also run `msdk deploy` to push a build straight to the local machine for the fast loop.

Blocker already on record: **the repo signing key does not exist yet** ([RELEASE-PIPELINE.md](RELEASE-PIPELINE.md)); until the owner creates it
nothing can publish, apt or pacman. Until the Arch cutover, the same four steps run on the existing deb pipeline.

## 3. Development direction this implies

1. **Do not start over.** The Rust compositor is already the session; the SDK core (`msdk`) exists; the Arch Pantheon group is a working
   scaffold. Starting over would discard the one thing that already runs.
2. **Build the Rust Pantheon top-down on the SDK.** Each shell surface in the table above is an SDK app. That makes the SDK real (the
   benchmark specs finally have shell-sized users) and shrinks Vala patch maintenance to zero over time.
3. **Treat the display stack as a product.** `mseries-display` owns EDID, KMS, hotplug and dock logic with the evidence-gated dock goal;
   `mseries-wm` owns the protocol and window management.
4. **Packages follow layers.** One PKGBUILD set per layer in the pacman repo, so a layer can be rebuilt, rolled back and promoted alone.
5. **Measure only at decision points**, as the owner asked: before replacing a piece (to confirm it is worth it) and after (to confirm it
   was). No standing benchmark programme.

## 4. Open items

- 5 packages did not map automatically: `elementary-sdk`, `energy-monitor`, `openssl-provider-legacy`, `ovmf` (Arch: `edk2-aarch64`),
  `shellcheck`. All are build-only or optional; none blocks the base.
- 7 packages are flagged `aur-or-ours` (`brave-browser`, `tether`, `blueferry-*`, `hfsprogs`, `chntpw`, `powerstat`, `zeitgeist`): AUR or
  our own PKGBUILD, decided when each is wanted.
- The classification rules are first-pass judgement; challenge any row in `packages.tsv`. The generator is deterministic, so fixes go in
  `build-inventory.py` and the file is regenerated.
- Pantheon Wayland session: Arch ships `pantheon-wayland`; whether it can be skipped entirely in favour of our session file is a Phase D question.

## 5. How to regenerate

```bash
python3 mseries/minimal-system/build-inventory.py /tmp/arch-db-cache . > mseries/minimal-system/packages.tsv
```

Needs network (downloads the Arch Linux ARM and Asahi Alarm sync databases) and the Ubuntu system the packages are installed on.
