# Release pipeline: one workflow, two signed apt suites

Status: implemented 2026-10-21 in `.github/workflows/mseries-debs.yml`, `mseries/debs/build.sh` and
`mseries/release/`. **Nothing is published**: the signing key does not exist yet, so publishing fails
closed. Design of what consumes this: [UPDATER-DESIGN.md](UPDATER-DESIGN.md). Issue
[#52](https://github.com/techmore/ElementaryOS_MSeries/issues/52).

## What runs when

| Event | Channel | Builds and tests | Publishes |
| --- | --- | --- | --- |
| push to `dev` (a merged PR) | `dev` | yes | `dev` suite |
| push to `main` (merging a release PR `dev` → `main`, or a hotfix) | `stable` | yes | `stable` suite |
| pull request (including the release PR itself) | `stable` if it targets `main`, else `dev` | yes | never; no secrets |
| manual run, `publish` ticked | by the branch (`dev` or `main`; others refuse) | yes | that suite |

The release PR runs the build against the *stable* version numbers it will publish, so a version-rule
break shows up before the merge. The suite is published when the PR merges, not while it is open: a
publish from a pull-request event would sign unreviewed code. One run builds and tests once, then one
job signs and commits only its own suite; the other suite's files are left byte-identical
(`test-assemble.sh` proves this).

Packages in both suites today: `mseries-wingpanel-network`, `mseries-quick-settings`,
`mseries-wingpanel-datetime`, `mseries-update` (owner decision: plugins and updater first).
`pantheon-rust-compositor` is built by the `compositor` job and uploaded as a workflow artifact only; it joins
the suites once the health check covers its recovery path (LightDM session choice).

`claude-pantheon-rs` (Claude for elementary OS, the native T3 client, with its Wingpanel indicator) is built by the
`claude-pantheon-rs` job of the same workflow with `rust/claude-pantheon-rs/build-deb.sh` and uploaded as an artifact
only, on every push to dev/main and on PRs touching `rust/**`; `validate-mseries.yml` builds and tests it on PRs touching
`rust/claude-pantheon-rs/**`. It joins the suites once it has an installed-and-launched check like the plugins.

## Version rules

`stable` is `<upstream gate>-0mseries<N>` (for example `1.4.0-0mseries3`); `dev` appends
`~dev<commit time UTC, YYYYMMDDHHMMSS>.<7-char sha>`.

- In dpkg's order `~` sorts before everything, even the end of the string, so every dev build is lower than the stable build of the same revision; a switch from
  `dev` back to `stable` never needs a downgrade. Bumping the packaging `REVISION` makes the next dev build
  sort above the previous stable one.
- **Deviation from the first design text:** the stamp is the commit *time*, not the date. With a date, two merges on the
  same day would order by sha, and the updater never installs a lower version, so a later build with a
  smaller sha would be skipped. The time is the commit's, not the build's, so rebuilding a commit gives the same version.
- The workflow fails if a dev version lacks the stamp or a stable version carries a `~`.

## Layout of the repository

```
apt/mseries-archive-keyring.{gpg,asc}     public key (comparison only, not a trust anchor)
apt/pool/{dev,stable}/*.deb               dev keeps the newest 8 versions per package; stable keeps all
apt/dists/{dev,stable}/InRelease          clear-signed; also Release + Release.gpg
apt/dists/{dev,stable}/main/binary-arm64/Packages{,.gz}
```

Source line (what `mseries-update init` writes): `Suites: stable` or `dev`, `Components: main`.
The script rebuilds the index of its own suite from the pool each time, signs it, then verifies `InRelease`,
`Release.gpg` and every pool file's SHA-256 against the index with the exported public key before the job commits anything.

## Open: where the `gh-pages` branch is served

Owner decision: host on GitHub Pages / `gh-pages`. The branch does not exist yet (the first publish creates it)
and, more important, the repository's Pages source is **`dev:/docs`** (`gh api repos/techmore/ElementaryOS_MSeries/pages`:
`build_type: legacy`, `source: dev /docs`, set 2026-10-21 for the public site), and a repository has one Pages source.
So `https://techmore.github.io/ElementaryOS_MSeries/apt` will not serve this tree. Options for the owner:

1. Serve the tree from `https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/gh-pages/apt`. Works with no setting
   changes, static, HTTPS; GitHub does not promise it as a package CDN and rate-limits heavy use. Fine for the owner's machines.
2. Change Pages to "GitHub Actions" and deploy `docs/` plus `apt/` together. One site, one URL, but it replaces the
   website's publishing path the owner chose.
3. A separate small repository (for example `techmore/mseries-apt`) whose own Pages serve the tree; needs a cross-repository
   token in CI.

Nothing in the scripts depends on the answer; only the `--uri` given to `mseries-update init`.

## Key custody

[release/KEY-RUNBOOK.md](release/KEY-RUNBOOK.md). Offline primary, one-year signing subkey in `MSERIES_APT_KEY`, public
keyring committed at `mseries/release/mseries-archive-keyring.gpg` and shipped in the `mseries-update` deb (the build says in
`BUILD-PROVENANCE.txt` whether it was included). Without the secret an automatic run annotates a warning and publishes
nothing; a manual publish run fails.

## Reproducibility and Nix: measurements (2026-10-21, aarch64, this M-series machine)

Question: would a Nix flake make the plugin debs and the compositor reproducible in CI? Measured, in order of what was cheap:

| Measurement | Result |
| --- | --- |
| Same commit, same machine, `build.sh` before this change, two runs (datetime plugin) | the `.deb` **differed** (`1734b67b…` vs `36c13d21…`): file mtimes in the archive |
| Same, after setting `SOURCE_DATE_EPOCH` to the commit time (this change) | `.deb` **identical** (`c4d5d87a…` twice); the `libdatetime.so` inside was identical in both cases (`b09e8342…`), also with a random `mktemp` build directory |
| `mseries-update` deb, two runs, new script | identical (`c79ca8c3…`) |
| Build time, datetime plugin from pinned source | about 6 s after the dependencies are installed |
| nixpkgs 25.11 versions of the inputs vs what the debs build against here | wingpanel 8.0.3 (here `libwingpanel-9-dev` 8.0.4+r814), granite7 7.7.0 (here 7.8.1), gtk4 4.20.3 (here 4.22.4) |
| nixpkgs unstable (`02c087f3`) | wingpanel 8.0.4, granite7 7.8.1, gtk4 4.22.4: numerically equal to what is installed here |
| `vmTools.debDistros` on aarch64-linux (builds inside a pinned Debian/Ubuntu image) | only `i386` and `x86_64` images (`ubuntu2604x86_64` exists, no aarch64) |
| elementary daily PPA while measuring | HTTP 503 (the outage that failed PR #429's first build); `snapshot.ubuntu.com` answered 200 but covers the Ubuntu archive, not PPAs |

What this supports, and what it does not:

- The non-determinism that existed was packaging metadata, now fixed with no new tooling. Build output was already
  stable on one machine. That does **not** show it is stable across machines or across time.
- The real source of drift is the *inputs* the debs compile against: the elementary daily PPA headers and Ubuntu libraries,
  which move and which cannot be snapshotted. A Nix build pins its inputs but builds against nixpkgs' copies, linked into `/nix/store`,
  not against the Ubuntu runtime the deb is installed onto; the plugin must load into the Ubuntu-built Wingpanel. So a
  flake can pin source, Vala and Meson, but it does not by itself produce a deb that is correct for this system, and the
  pinned-image route (`vmTools`) has no aarch64 image.
- **Not measured:** a Nix build of the compositor (a git dependency on Smithay needs fixed-output hashes), the cache cost of
  Nix on the arm64 runner, and a patchelf/rewrite route. None of those were attempted, so nothing is claimed about them.
- Recommendation: do not add a flake now. It would be a second build path to keep in step with the first, for a benefit
  that the measurements show is limited to toolchain pinning. Revisit when the factory image (#50) gets a Nix or
  Arch backend decision: then the flake would be the *delivery* of the system, not an alternative way to build these debs.
  Cheaper steps that were taken instead: deterministic archives (done), PPA retry in CI (done), pinned source commits (already),
  and recording the exact base package versions in `BUILD-PROVENANCE.txt` (already). Next candidate: record the PPA package
  versions used by each build next to the debs, so a drift is visible when two builds of one commit differ.

Compositor deb (`build-deb.sh`, cold target directory, 10 cores, this machine): 116 s wall for `cargo build --release --features native-drm`; the runner will differ.

## Not verified

- The workflow's new steps have not run in CI: the elementary daily PPA returned 503 while this was built. The scripts they
  call (`mseries/validate.sh --only debs`, `mseries/release/test-assemble.sh`, the build) were run here; the workflow YAML parses.
- Nothing has been signed with a real key or published; the first `gh-pages` creation, the push retry and the
  `AUTH_HEADER` handling in the publish job are untested until a key exists.
- `apt-get update` against a `file:` copy of both suites passes in a container; no machine has run
  `mseries-update init` against a hosted `https` repository, and the serving question above is open.
- The compositor job's apt dependency list builds the deb in a clean `ubuntu:26.04` arm64 container (about 2 min); it has not run on the GitHub runner or with its cargo cache.
- The dev retention (8 versions) is a guess; a client that last staged a pruned version can still roll back from its local store.
