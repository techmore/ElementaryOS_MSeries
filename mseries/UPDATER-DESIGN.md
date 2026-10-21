# Customer update mechanism: design and first slice

Status: first slice implemented in `mseries/update/` (2026-10-21). Nothing is published,
enabled by default or verified on real hardware yet; see "What is not verified". Related
issues: [#50](https://github.com/techmore/ElementaryOS_MSeries/issues/50) (atomic delivery,
rollback), [#52](https://github.com/techmore/ElementaryOS_MSeries/issues/52) (binary .deb
repo built once in CI), [#47](https://github.com/techmore/ElementaryOS_MSeries/issues/47)
(slow serial installs). Prior art in the tree: `mseries/atomic-app.py` (per-app generation
store for upstream bundles such as Signal), `mseries/debs/build.sh` and
`.github/workflows/mseries-debs.yml` (the .deb producer).

## Problem

Customers update by `git checkout` plus a per-component `deploy-*.sh`. That compiles or copies
into live paths, needs the toolchain and a checkout, has no signature check, and an interrupted
run leaves a mixed set of files. Routine updates must also never restart Wingpanel, the dock
or the compositor mid-session (AGENTS.md).

## Scope: what the updater manages

Packages we build and sign ourselves, installed through dpkg: the `mseries-*` packages
(`mseries-wingpanel-network`, `mseries-quick-settings`, `mseries-wingpanel-datetime` today)
and optionally `pantheon-rust-compositor` (see `mseries/pantheon-rust-compositor/build-deb.sh`).
It updates only packages that are already installed and offered by the M-series repository.
It never touches the kernel, bootloader, initramfs, audio stack or the base Ubuntu/elementary
packages; those stay with apt and are a separate decision (#50 says the same). Upstream
bundles (Signal, CodexBar, Brave) keep their own installers and `atomic-app.py` for now.

## Design

| Concern | Decision |
| --- | --- |
| Source | A signed apt repository (`InRelease`, key pinned by a keyring file) read through a **private** source list and lists directory. System `apt upgrade` never sees it, and refreshing it never refreshes the rest of the system. |
| Channels | Two apt suites in the same repository: `stable` (default; moves only on a release) and `dev` (every merge to `dev`). `mseries-update channel dev` rewrites the private source. Dev versions carry `~dev<date>.<sha>` so the matching stable build always sorts above them and a switch back never needs a downgrade. The updater never installs a version lower than the installed one. |
| Staging | `stage` refreshes metadata, plans the install with `apt-get --simulate`, downloads each exact `.deb`, records SHA-256 for each, and also stores a copy of the **currently installed** version of every affected package (the rollback set). It installs nothing. If a rollback copy cannot be obtained the update is refused. A dependency the repository cannot satisfy fails at staging, so the updater never pulls in new third-party packages. |
| Apply | One `dpkg -i` of the whole set. Before it, a write-ahead journal (`restore` = exact old versions) is fsynced; staged files are re-hashed. Any failure (dpkg error, wrong version afterwards, `dpkg --verify` problems, unresolved `.so` libraries, a failing script in `health.d/`) converges back to the journalled versions and records the target versions as skipped so they are not retried automatically. dpkg itself is not transactional, so "atomic" here means: **the machine ends on the old complete set or the new complete set, restored from the journal even after power loss**. |
| When it applies | At the next boot, by `mseries-update-boot.service`, ordered before `display-manager.service`. No session exists, so no running Wingpanel, dock or compositor is disturbed. `apply --now` exists but must be spelled out; dpkg replaces files by rename so a running session keeps its old copies until next login. No maintainer script or unit restarts anything. |
| Pre-flight | Stage: free space on the state filesystem, update server reachable, dpkg database clean (`dpkg --audit`), no apt/dpkg running, not on a metered connection (automatic runs only). Apply: free space on state and `/usr` (3x the update size plus `min_free_mb`), AC or battery above `min_battery_percent`, dpkg database clean, staged hashes intact, rollback copies present. Transient reasons (battery, apt busy) **defer** to the next boot; the rest block with an error. |
| Health and automatic rollback | After install: version check, `dpkg --verify`, `ldd` on shipped plugins, optional executable checks in `/etc/mseries-update/health.d/`. After login: `mseries-update-confirm.service` waits (default 10 min) for the configured session processes (default `io.elementary.wingpanel`) and then marks the set known-good. If the set is not confirmed after `max_unconfirmed_boots` (default 2) restarts, the next boot rolls back before the login screen. This is systemd-boot "automatic boot assessment" applied to packages. |
| Crash safety | State is replaced atomically (temp file, fsync, rename). A journal found at boot means a crash or timeout during a transaction: the boot unit restores the journalled versions first and records `recovered`. Rollback itself is idempotent and retried on every boot until the machine matches a known-good set; if it cannot (a missing copy), the unit fails loudly, exit code 3, state `rollback-failed`. |
| Opt-in | Installing the `mseries-update` package enables nothing and configures no source. The owner runs `mseries-update init --uri ... --keyring ...`, then `systemctl enable mseries-update-boot.service mseries-update-confirm.service`. The daily check timer is separate and `auto_stage` defaults to off, so by default nothing downloads without a command. |
| CLI | `check`, `stage`, `apply --now`, `rollback`, `confirm`, `status [--json]`, `log`, `channel [stable|dev]`, `init`, `config`. Mutating commands need root. Exit codes: 0 ok, 1 failed, 3 rollback failed, 75 another update running. |
| Logging | `/var/log/mseries-update.log` (one line per decision, with ids) plus the journal; `state.json` keeps the last 30 outcomes. |
| UI | **Slice:** `status --json` is the stable contract (schema 1). **Proposed next:** a "Software Updates" pane in Switchboard (or a Wingpanel indicator, consistent with `install-touchid-settings.sh` and RepoBar Settings) that reads that JSON, offers *Check*, *Install at next restart*, *Roll back*, and a channel switch behind an Advanced toggle, and calls the CLI through a polkit action (`org.techmore.mseries.update`) so no sudo prompt is needed in a terminal. The pane contains no update logic of its own. |
| Fleet use | The CLI is non-interactive and `status --json` is machine readable, so any fleet tool can drive it: `ssh host sudo mseries-update stage`, an Ansible play, or an osquery/Fleet query over `status --json`. Prefer agentless tools (SSH loop, Ansible) over agent-based ones such as Salt (a master plus a resident minion on every machine), which is too much moving machinery for a handful of desktops. Only add one when there are enough customer machines to need it. |

## Files

```
mseries/update/mseries-update.py   the updater (installs as /usr/sbin/mseries-update)
mseries/update/systemd/            boot (apply/recover), confirm, optional auto-check service and timer
mseries/update/install.sh          development install (customers get the mseries-update .deb)
mseries/update/test_*.py           fake-repo fault injection, real apt/dpkg in a scratch root, packaging
/var/lib/mseries-update/           state.json, store/ (rollback copies), staged/, apt lists, pending-confirm
/etc/mseries-update/               mseries-update.conf, sources.list.d/mseries.sources, health.d/
```

## Verified in CI-grade tests (no hardware)

- Fake repository and package database: update, no-op, skipped (rolled-back) versions, no
  downgrade offers, unmanaged packages untouched, a new repo dependency delivered and removed on
  rollback, one dpkg run per set.
- Fault injection: unsigned or unreachable repository, failed download, missing rollback copy,
  low disk, no network, busy dpkg, half-configured dpkg, tampered staged file, a package failing
  midway through the set, failed `dpkg --verify`, failed health script, battery low (defer),
  concurrent run, power loss mid-install, a rollback that itself fails and is retried at the next
  boot, an update that never reaches a healthy login, unreadable state.
- The real `apt-get`/`apt-cache`/`dpkg`/`dpkg-query` against a local `file:` repository and a scratch
  dpkg root: refresh, candidate parsing, planning, exact downloads, install, downgrade rollback, a real
  failing `postinst`, and a real `SIGKILL` of both updater and dpkg mid-install followed by recovery.

## What is not verified (needs the real machine, key and repository)

- Nothing has run on an M1/M2 desktop, under systemd, with LightDM, as root with apt's `_apt`
  sandbox, or on a real HTTPS signed repository. The boot ordering, the 300 s unit timeout and
  the confirm unit have only been checked by reading the unit files.
- No signed repository exists. `Signed-By` keyring handling, `InRelease` verification failure behaviour
  and key rotation are untested beyond apt's own behaviour.
- The first `mseries-update` package and the `dev`/`stable` suites are not published; `mseries-debs.yml`
  still publishes one suite and fails closed without `MSERIES_APT_KEY`.
- Panel UI, polkit action, battery reading on the real `macsmc` supply, metered-connection detection through
  NetworkManager on a tethered phone, and behaviour when the confirm unit runs on a Rust-compositor session.
- Packages that already have a Debian-style `Pre-Depends`/`Conflicts` change between versions are not
  covered; the updater will report dpkg's error and roll back.
- Roll back does not undo data migrations. Packages in scope today are plugins with no user data.
- Factory-image boot with the updater is unverified; this is not a statement about the unbuilt image.

## Decisions for the owner

1. **Hosting of the apt repository.** Recommend GitHub Pages on the existing `gh-pages` branch
   (what `mseries-debs.yml` already assembles): free, HTTPS, and `apt-ftparchive` output is static.
   Alternatives: the SER8 (own the bandwidth, but a single point of failure), or Cloudflare R2/S3 later.
2. **Signing key custody.** Recommend a dedicated repository key, kept offline (hardware token or an
   encrypted offline backup), with only a **signing subkey** in the `MSERIES_APT_KEY` Actions secret,
   a one-year expiry and a documented rotation (ship the new keyring in a package signed by the old key).
   Do not reuse a personal key. The keyring file is delivered in the `mseries-update` package and in the image.
3. **Which components ship first.** Recommend the three Wingpanel plugin debs only (`network`,
   `quick-settings`, `datetime`): proven in CI (`test-divert.sh`), small, no data, and a bad one is
   recoverable. Add the Rust compositor as a second step: it is still experimental, not the default
   session, and its recovery path (LightDM session choice) should be part of the health check first.
4. **Default for `auto_stage`.** Recommend off for the first customers (explicit "Install at restart"),
   on after a few clean releases.

## Roadmap after this slice

1. Publish: split `mseries-debs.yml` publish into `dev` (on merge) and `stable` (on release) suites with
   version rules above; build `mseries-update` in the same run (done in `build.sh`).
2. Wire `enhance-firstboot.sh` `run_module` to install the signed debs first (#52) and seed the update source.
3. Polkit action plus a Switchboard pane or Wingpanel entry reading `status --json`.
4. Extend the health check with a compositor/dock probe and add the Rust compositor package.
5. A fleet runbook (SSH loop or Ansible) once there is more than the owner's machines.

## Reproducibility and Nix or Arch

The owner asked whether a Nix or Arch base would give more reproducible builds. Short answers, kept
out of this change on purpose because it is a base-distribution decision (#50 separates it from app delivery):

- **Nix** has the best model for exactly what is asked: declarative, content-addressed, atomic
  *generations* and a reproducible build graph. Its profile switch is a real atomic symlink flip of the
  whole closure, which is what this slice approximates with a journal over dpkg. What it costs here:
  aarch64 binary-cache coverage for Pantheon and the Asahi graphics stack, a very different packaging
  workflow for the Vala/Meson plugins and the Rust compositor, and Switchboard/Wingpanel/portal
  integration on a non-FHS system. A realistic path is **Nix for the build side first** (flake that
  builds the plugin debs and the compositor reproducibly in CI, with `mseries-debs.yml` consuming it),
  then evaluate a NixOS or home-manager spin per #50's backend table with measurements.
- **Arch** (Asahi/Arch Linux ARM) is faster to track upstream and has `pacman` hooks and simple PKGBUILDs,
  but it is rolling and not reproducible by itself, and it would replace the elementary base rather than
  complement it.
- This updater is designed so none of that is wasted: everything package-manager specific is the
  `Backend` class; the state machine, journal, confirmation and rollback logic, CLI and `status --json`
  contract are backend-neutral. A Nix backend would map "set" to a profile generation and "converge"
  to `nix profile rollback`.
