# Asahi Alarm audit (Phase A of [ARCH-REBASE-PLAN.md](ARCH-REBASE-PLAN.md)), 2026-10-23

Question: is Asahi Alarm (the Arch Linux ARM distribution for Apple Silicon behind
`asahi-alarm.org`, the installer this repo already uses) healthy enough to be the base?
**Answer: yes, with two named risks.** Read-only audit by Claude on 2026-10-23 using the public
site, the `asahi-alarm` GitHub organisation (via `gh api`), and the Arch Linux ARM mirror. Nothing
was installed or changed. Numbers are as fetched that day; they will drift.

## Verdict

| Question | Finding |
|---|---|
| Alive? | **Yes.** `PKGBUILDs` was pushed on 2026-10-22; 18 commits in October so far, 48 in September, 13 to 48 a month all year |
| Who maintains it? | Two people do nearly all of it (below). An automated "Automated update" bot adds the rest |
| Where is the package repo? | A single GitHub Release: `https://github.com/asahi-alarm/asahi-alarm/releases/download/$arch` (tag `aarch64`, 84 assets) |
| Current vs Asahi upstream? | **Tracks it closely**: kernel `7.2.12` published 2026-10-22, the same version as the upstream `v7.2.12` tag; every other package in lockstep with Fedora's Asahi Remix except the ones listed under "Behind" |
| Release cadence? | Kernel bumped about every two to four weeks (about two dozen kernel bump or spec commits since March) |
| Problems? | Bus factor of two, a single-host repo, no declared licence, and our own docs contain a wrong assumption (see "Correction") |

## Evidence

### Site and installer

- `https://asahi-alarm.org/` served 2026-10-23 (Apache; files last modified 2026-09-21). It describes Asahi Alarm
  as "an Arch Linux ARM distribution for Apple Silicon macs" built "on top of the Asahi Linux project".
- Installer `latest` = `v0.9.2`. `installer_data.json` lists six images: Minimal, Minimal (BTRFS), Desktop,
  Desktop (BTRFS), UEFI-only and tethered boot. Desktop images offer KDE Plasma, GNOME, XFCE, MATE, LXQt and
  **Hyprland** through Calamares. The BTRFS variants use subvolumes `@` and `@home`.
- The bootstrap script is MIT-licensed, reports to `stats.asahilinux.org` with tag `alarm-prod`, and needs
  macOS 13.5 or later.
- Hosting is a hobby service: the page asks for donations "to pay the web hosting".

### Maintainers (from `asahi-alarm/PKGBUILDs`)

| Person | All-time commits | 2026 commits | Role |
|---|---:|---:|---|
| Matthias Kurz (`mkurz`) | 379 | 136 | Kernel, Rust, m1n1, muvm, Mesa bumps; most October work |
| Jos Dehaes (`joske`) | 340 | 35 | Installer and builder; named in the installer script |
| `marcan` | 243 | 0 | Appears to be imported upstream history, not recent work **[inference]** |
| GitHub Action bot | 269 | 115 | "Automated update" of spec/index files |
| Others | under 25 each | 8 | Occasional contributions |

Organisation created 2024-11-14, 253 followers, 11 public repositories. Community channel: Matrix
`#asahi-alarm:matrix.org`. Six open issues on `PKGBUILDs`, four on `asahi-alarm`.

### Repositories and what they do

| Repo | Last push | Purpose |
|---|---|---|
| `PKGBUILDs` | 2026-10-22 | All package recipes (kernel, m1n1, U-Boot, Mesa pieces, speakersafetyd, tiny-dfr, firmware tools, audio, FEX, muvm, widevine, calamares), `versions.txt`, `build.sh`, `release.sh` |
| `asahi-alarm` | 2026-09-21 | The website, the bootstrap script, manual install doc, and the **release that is the pacman repo** |
| `asahi-alarm-builder` | 2026-09-21 | Reference image builder; `mirrorlist.asahi-alarm`; pacman setup scripts |
| `asahi-alarm-installer` | 2026-09-19 | The Asahi Alarm installer, by Jos Dehaes |
| `asahi-alarm-keyring` | 2024-12-16 | Package signing keyring |
| `asahi-calamares-configs`, `asahi-scripts`, `asahi-installer-data`, `docker-pkgbuild`, `RootFS` | 2026 | Supporting pieces |

### How the repo is consumed

The builder adds a repository section `[asahi-alarm]` **above** `[core]` in `/etc/pacman.conf`, including a mirrorlist
whose only server is the GitHub Release URL above, then runs `pacman-key --init` and `--populate`. The release holds the
database (`asahi-alarm.db`, `.files`, each with a `.sig`) and the packages. The database was regenerated on 2026-10-22.
The base system is stock Arch Linux ARM: its `core.db` on `os.archlinuxarm.org` was modified 2026-10-22.

### Package versions against upstream

`PKGBUILDs/versions.txt` compares Asahi Alarm with Fedora Asahi Remix F44, which is the Asahi team's own flagship and the
best available proxy for "Asahi upstream". Fedora figures are as that file lists them.

| Package | Fedora Asahi (F44) | Asahi Alarm | Note |
|---|---|---|---|
| `linux-asahi` | 7.2.12-400 | **7.2.12.asahi1** (published 2026-10-22) | `versions.txt` itself still says 7.1.13, so the file is stale; the published asset is current. Upstream `AsahiLinux/linux` tag `v7.2.12` exists |
| `m1n1` | 1.9.9 | 1.9.9 | Bumped 2026-10-21 |
| `uboot-asahi` | 2026.07-101 | 2026.07.asahi2 | Published 2026-09-09 |
| `speakersafetyd` | 2.0.1 | 2.0.1 | Same |
| `tiny-dfr` | 0.3.7-3 | 0.3.7-1 | Same version |
| `asahi-audio` | 4.1 | 4.1 | Same |
| `alsa-ucm-conf-asahi` | 10-1 | 10-1 | Same |
| `FEX-Emu` | 2604 | 2604 | Same |
| `muvm` | not listed | 0.7.0 | Bumped 2026-10-13 |
| `mesa` | not listed | 26.2.3 pieces (published 2026-09-18) | Only dummy and FEX overlay packages were seen in the release assets; **where the Asahi Mesa driver itself ships was not confirmed** |
| `bankstown` | 1.1.0-3 | 1.1.0-2 | Behind by a packaging revision |
| `calamares` | 3.3.14 | 3.4.2 | Ahead |
| Extras Fedora lacks | n/a | `asahi-bless`, `asahi-btsync`, `asahi-wifisync`, `widevine`, `steam`, `startup-disk` | Value-adds (Widevine is the one [BRAVE-WIDEVINE.md](BRAVE-WIDEVINE.md) already notes) |

Not audited: the actual contents of the kernel config against our Aurora kernel, and whether the Asahi GPU driver ships in the
kernel package as expected. Both belong to Phase B.

## Correction: the Arch root is already gone on this machine

[ARCH-REBASE-PLAN.md](ARCH-REBASE-PLAN.md) said the Arch side "already exists on the owner's machine as the boot host".
That was taken from [KERNEL-FLOW.md](KERNEL-FLOW.md) and is **out of date**:

- [docs/RECOVERY-SYSTEM-AUDIT-2026-10-14.md](../docs/RECOVERY-SYSTEM-AUDIT-2026-10-14.md) records the machine as reinstalled with
  only `@elementary` and `@elementary-home`, and says the older Arch `@` and `@home` roots are "already gone".
- Today's mounts agree: `/` is `@elementary`, `/home` is `@elementary-home`; there is no `/etc/pacman.conf`.
- The running kernel (`7.2.11-elementary-aurora72-wip3`) is a hand-built image copied into `/boot` beside older ones;
  `/boot` still holds `vmlinuz-linux-asahi` and `initramfs-linux-asahi.img` from the original install (2026-10-14).

So the "pacman hook syncs the kernel into `@elementary`" flow no longer runs, and the dual-root cost is already partly
paid. The rebase is still worth it (§2 of the plan), but it is a **fresh Arch root**, not a promotion of an existing one,
and the fallback is the current Ubuntu root. The plan has been edited to say so.

## Risks and what to do about them

| Risk | Severity | Mitigation |
|---|---|---|
| **Bus factor of two.** Two people produce nearly all recent work | High | Mirror the repo and sources; pin by version; keep the ability to rebuild the kernel/m1n1/U-Boot packages from their PKGBUILDs ourselves (they are public); contribute upstream so we are a third maintainer; re-audit quarterly |
| **Single host.** The package repo is one GitHub Release in one organisation | High | Mirror to our own pacman repo (the plan already has one); our images must never depend on the release URL at install or update time |
| **No licence detected** on `PKGBUILDs` and `asahi-alarm` (GitHub reports none). The bootstrap script header says MIT | Medium | Ask the maintainers to add licence files before we redistribute their recipes or binaries; until then use them as upstream references and build our own packages from Asahi's own licensed sources |
| **Hobby service.** Hosting funded by donations | Medium | Same as above: depend on a mirror we control |
| **Stale `versions.txt`.** Comparison file lags the real repo | Low | Compare from the published database, not that file |
| **Mesa location unconfirmed** | Medium | Resolve first in Phase B by installing into a scratch chroot and reading `pacman -Qi mesa` |
| **Closeness to Fedora Asahi** is a proxy for upstream, not proof | Low | Spot-check against `AsahiLinux/linux` tags (done for the kernel) |

## What this changes in the plan

1. Caveat 4 of the rebase plan resolves to: **Asahi Alarm is healthy and current; the risk is its size, not its staleness.**
2. Phase B gains two tasks: mirror the repo into our own, and resolve the Mesa question.
3. Add a decision: contact the maintainers (licence, collaboration, upstreaming our Aurora patches), which is the owner's to send.
4. The fallback if Alarm stops: rebuild its ~30 PKGBUILDs ourselves. They are small and public; the kernel is the only large one.

## Method and gaps

Read: the site HTML, `installer-bootstrap.sh`, `installer_data.json`, `latest`; via `gh api` the org, repos, commits since 2026-01-01,
contributors, `versions.txt`, `mirrorlist.asahi-alarm`, `00-pacman.sh`, and the `aarch64` release assets; the Arch Linux ARM `core.db`
header. **Not done:** installing from the repo, verifying signatures against the keyring, reading licence files in individual PKGBUILDs,
or contacting anyone.
