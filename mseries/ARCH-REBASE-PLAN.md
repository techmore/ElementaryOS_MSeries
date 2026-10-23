# Decision and plan: rebase the platform on Arch Linux (Asahi Alarm)

Status: **owner decision 2026-10-22; plan only, nothing implemented.** Supersedes the Ubuntu 26.04 /
elementary OS 9 base assumed by [PLATFORM-PLAN.md](PLATFORM-PLAN.md) (the repo split, the SDK and the
benchmark are unchanged by it). Written by Claude. Facts from web searches are cited; everything
else was read from this repository. **[inference]** marks my judgement.

## 1. Decision

The base becomes **Arch Linux ARM with the Asahi overlay** (what the installer calls Asahi Alarm), not
an Ubuntu root with elementary packages. The Arch side already exists on the owner's machine as the
boot host ([KERNEL-FLOW.md](KERNEL-FLOW.md)); the rebase makes it the only root.

Not decided here (see §7): how much of Pantheon survives the move.

## 2. Why this is easier to maintain, and what it costs

"Front-loaded work, easier afterwards" is **mostly true, with four caveats**.

### What gets simpler for good

| Today (Ubuntu root on an Arch boot host) | After |
|---|---|
| Two roots. The kernel and modules are installed by Arch and **copied** into `@elementary` by a pacman hook; firmware too ([KERNEL-FLOW.md](KERNEL-FLOW.md)) | One root. `pacman` installs the kernel, modules, firmware and initramfs; no sync hook |
| `install-boot-isolation.sh` stops Ubuntu's `initramfs-tools`, `grub` and kernel packages from clobbering the ESP (apt pins, dpkg diversions, no-op stubs) | Not needed; there is no second package manager to fight |
| Aurora/Fairydust kernel work is native Arch PKGBUILD and gets **converted to Debian payload packages**; `PORT-MAP.md` records "Arch's PKGBUILD/AUR packaging is not adopted" | Ship the PKGBUILD as it is |
| A **private patched libmutter** is built from Ubuntu source and swapped in for Gala because Ubuntu's mutter lacked a fix ([RUST-UPSTREAM-MAINTENANCE.md](RUST-UPSTREAM-MAINTENANCE.md)) | Build mutter/Gala from source in our own PKGBUILDs at the revision we choose |
| Mesa Asahi, m1n1, U-Boot, `speakersafetyd`, firmware, `tiny-dfr` come from Asahi, then get ported | They come from the Asahi overlay **if it is still maintained** (see caveat 4). In 2023 Asahi described an overlay on Arch Linux ARM carrying its integration scripts, bootloader parts, userspace support and forked kernel and Mesa ([Asahi, 2023](https://asahilinux.org/2023/08/fedora-asahi-remix/)) |
| Hardware fixes from omarchy-mac are re-translated to Ubuntu/mkosi ([PORT-MAP.md](PORT-MAP.md)) | Often usable as they are (their packages target Arch) |
| Rust, SDK, compositor: all new work, no distro dependency | Same, but compositor and apps build from `PKGBUILD`s against current libraries |

Net: removes a layer of translation and the most fragile hacks (dual root, boot isolation, private libmutter).

### Caveat 1: rolling release moves the breakage to you

Arch updates fast, so you get new Mesa and kernels sooner and break sooner. Without a gate you hit the
same class of bug that [PANTHEON-CRASH-2026-10-18.md](PANTHEON-CRASH-2026-10-18.md) documents, just more
often. Mitigation: our own repo with **dev and stable suites** (the design from [RELEASE-PIPELINE.md](RELEASE-PIPELINE.md)),
promotion only after an automated install-and-launch test, pinned snapshots, and no partial upgrades.

### Caveat 2: Arch Linux ARM is a small, separate project

Arch Linux ARM is an independent port of Arch, not Arch itself. Its site says new upstream releases reach
the supported ARM architectures within hours ([about](https://archlinuxarm.org/about)); the only maintenance
discussions I found are from 2022 to 2023 and include concern about a stale aarch64 kernel package
([forum](https://archlinuxarm.org/forum/viewtopic.php?p=70474)). I found **no 2026 status**. **[inference]**
Treat it as a dependency with bus-factor risk: mirror what we depend on, keep the Asahi overlay's kernel
and Mesa as the only ones we run, and re-check project health quarterly.

### Caveat 4: the Asahi overlay for Arch is not the official flagship

The same 2023 post announces **Fedora Asahi Remix as Asahi's flagship distribution**; Arch is no longer where
the Asahi team's own packaging effort goes. "Asahi Alarm" (asahi-alarm.org, the installer this repo already uses)
appears to be a separate continuation. **I could not confirm who maintains it, how current its kernel/Mesa/m1n1
packages are, or its package repo address** (searches returned nothing for it). This is the biggest unknown in
the plan, and it decides whether the base is "pull from the overlay" or "we rebuild the overlay from Asahi's
public sources ourselves", a much larger Phase B. **Phase A therefore starts by auditing Asahi Alarm** (maintainers,
repo, package versions against Asahi's upstream, release cadence) before anything else is estimated.

### Caveat 3: Pantheon on Arch is community-maintained

The Arch Wiki says Pantheon and elementary's curated apps come from a `pantheon` package group, with
many more (third-party apps, development builds) in the AUR, and that `pantheon-session` pulls in Gala,
Wingpanel and the applications menu ([Arch Wiki: Pantheon](https://wiki.archlinux.org/title/Pantheon)).
The AUR `gala-git` page I saw was last updated 2024-09-29 ([AUR](https://aur.archlinux.org/packages/gala-git?O=10)).
So if Pantheon stays, **we** carry its PKGBUILDs and patches. That is the cost of keeping it, and the
argument for the SDK/compositor path replacing it over time.

### What is lost

The apt pipeline just built is for the old base: the signed `dev`/`stable` apt suites,
`mseries/debs/build.sh`, `mseries-debs.yml`, `mkosi.images/`, and the apt-specific parts of
[UPDATER-DESIGN.md](UPDATER-DESIGN.md). The *design* carries (two channels, signed index, promotion
rules, version ordering, key custody, fail closed); the *implementation* is redone as pacman repos.

## 3. What carries over unchanged

All Rust (`msdk`, compositor, apps), the kernel patch series and qualification tooling, the SDK and benchmark,
the Vala patches (rebuilt in PKGBUILDs), the Updates **UI**, the website, and the hardware evidence ledgers.
The Updates app is already separated from the backend: `mseries-update-core` defines the only commands a
UI may request, so the front end survives and the backend swaps from apt to pacman.

## 4. Target architecture

```
Asahi Alarm base (Arch Linux ARM + Asahi overlay: kernel, m1n1, U-Boot, firmware, Mesa, speakersafetyd)
  └─ mseries-pkgs (our signed pacman repo: dev / stable)
        kernel pins (mseries-kernel) · display (mseries-display) · compositor (mseries-wm)
        SDK runtime + apps (mseries-sdk, apps) · Pantheon pieces we keep (see §7) · Vala patches
  └─ one root, one package manager, one updater backend (pacman)
```

Repo split from PLATFORM-PLAN stays. `ElementaryOS_MSeries` keeps its name for now (renaming is a separate,
cosmetic decision) and becomes the integration repo that builds the image and the package repo from a pin manifest.

## 5. Phases

Order is chosen so the owner's working machine is touched last. The existing Ubuntu root is **kept, never
deleted**, as the fallback until a full release has passed ([EDGE-AND-RUST-PLAN.md](EDGE-AND-RUST-PLAN.md) rule).
Bootloader, kernel and audio changes on the owner's machine stay owner-initiated ([AGENTS.md](../AGENTS.md)).

| Phase | Work | Exit criterion |
|---|---|---|
| **A Audit and inventory** | Audit Asahi Alarm (caveat 4). List every package and file the Ubuntu image installs (mkosi package lists, install scripts, patches); mark each: Arch official, Asahi overlay, AUR, ours, or drop | An audit note on Asahi Alarm's health and a table in this repo with one row per item and an owner |
| **B Package** | PKGBUILDs for everything marked "ours" (compositor, apps, plugins, Vala-patched Gala/Wingpanel, kernel); build in a clean aarch64 chroot | Every item builds reproducibly in CI |
| **C Repo and CI** | Signed pacman repo with `dev` and `stable`; promotion by an install-and-launch test in a container or VM; same key policy as [release/KEY-RUNBOOK.md](release/KEY-RUNBOOK.md) | A package goes from PR to `dev` suite with no manual step |
| **D Image and installer** | `pacstrap`-based root builder replacing the Ubuntu bootstrap in `elementary-mac-setup`/`transform/`; keep the Asahi Alarm installer, LUKS and unlock-screen work | A fresh root boots in a VM and on a spare partition |
| **E Updater backend** | `mseries-update` drives pacman (`-Syu` against our repo only, never partial); channels = repos; atomic snapshot (btrfs) before each update | The Updates app updates and rolls back on the spare partition |
| **F Cutover** | Owner moves the daily machine when a full week on the spare passes; old root stays as fallback | Owner's go-ahead; fallback boot tested |

Phases A to C do not need the owner's hardware and can run on the CI aarch64 builder and SER8 containers,
never on the laptop's daily root.

## 6. Retired by the rebase (kept in git, not deleted)

`mkosi.images/*`, `mseries/debs/`, the apt parts of `mseries-debs.yml`, `install-boot-isolation.sh`, the kernel-sync
pacman hook and `elementary-grow.sh --sync-kernel`, `install-gala-mutter-fix.sh`, and the Ubuntu-specific install scripts.
They stay on a `legacy/ubuntu-base` branch until Phase F has passed.

## 7. Decisions for the owner

1. **Pantheon scope.** (a) Keep Pantheon (Gala, Wingpanel, Dock, Files, Settings) from the `pantheon` group plus our PKGBUILDs
   as the shell for now, and replace pieces with SDK apps and `mseries-wm` over time. (b) Drop Pantheon on day one and ship only
   our compositor and SDK shell surfaces. **My lean: (a),** because (b) puts the compositor, panel, dock and settings on the critical
   path at the same time as the base swap. This plan assumes (a).
2. **Overlay fallback.** If the Asahi Alarm audit shows it is stale, do we rebuild kernel/m1n1/U-Boot/Mesa packages from Asahi's public sources ourselves, or reconsider the base?
3. **Where Arch packages build.** A GitHub arm64 runner, SER8, or a dedicated builder. SER8's architecture was not checked.
4. **Branding.** Keep "elementary OS" in names while Pantheon stays, or rename once it is replaced.
5. **Spare partition** for Phase D/E trials: size and where.

## 8. Risks

| Risk | Mitigation |
|---|---|
| A rolling update breaks the daily machine | Own repo with promotion gate; btrfs snapshot before each update; fallback root kept |
| Arch Linux ARM stalls | Mirror deps; track project health; Asahi overlay kernel/Mesa are the only ones run |
| Keeping Pantheon on Arch costs more than expected | Time-box Phase A/B for Pantheon; (b) remains available because the SDK and compositor are distro-independent |
| Pipeline rework delays the SDK | The SDK and benchmark do not depend on the base; run them in parallel |
| Dock/DCP and suspend work gets disrupted | Kernel work continues on its own repo and receipts; no hardware change rides along with the rebase |
