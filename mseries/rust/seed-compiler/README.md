# Elementary seed compiler (Rust migration candidate)

This independent crate begins the Rust replacement for the seed-reading part of
`elementary/metapackages`. It parses Germinate `STRUCTURE` inheritance and seed
records, including feature declarations, package/source entries, recommendations,
blacklists, snaps, and architecture qualifiers. Its library composes explicitly
provided included collections and resolves profile inheritance, architecture
filters, and seed-level blacklists. An independently authored archive layer now
parses Debian `Packages` control stanzas and relationships, expands source names
to binaries, and computes a basic architecture-aware closure for Depends,
Pre-Depends, and optionally Recommends. The integrated `resolve-seed-packages`
command preserves each contributing seed's blocklist and Recommends scope.
A `!` exclusion applies to that seed and its inherited ancestors. Blocklisted
packages and sources are omitted from roots and transitive dependencies; an
allowed alternative may be chosen. If all available alternatives are blocked,
the dependency is omitted, so the resulting set may be uninstallable. Apt does
not know these exclusions and can still install a blocked dependency later.
A normal seed named `blocklist` has no automatic global effect; Germinate's
vestigial global source-blocklist report is not implemented.

`follow-recommends` in STRUCTURE supplies the default. Each contributing seed's
`follow-recommends` or `no-follow-recommends` overrides it (the positive flag wins
if both are supplied), and the CLI flag forces it on. Archive Recommends and
parenthesized seed recommendations are emitted in separate streams, with a
required package removed from the recommendation stream. Build-dependency
features, complete provider/alternative selection, archive conflicts like apt,
snap revision selection, and general Debian package support remain open.

`generate-metapackage-lists SOURCE-DIR STRUCTURE COLLECTION INDEX-DIR NEW-OUTPUT-DIR`
implements the map/list build stage in Rust. `SOURCE-DIR` supplies `update.cfg`
and `debian/control`. `INDEX-DIR` supplies `Packages-ARCH`, `Sources-ARCH` and
`debootstrap-ARCH` for every configured architecture; the latter is the frozen
whitespace-separated package set from debootstrap. The command accepts
`--dist=NAME` and the same included-collection arguments as seed resolution.
It reads config defaults/interpolation, output selection and explicit maps,
then applies case-insensitive `Task-Seeds`/`Task-Metapackage` headers, architecture
availability, declared source Binary membership, ancestor deduplication, essential
Depends filtering, and the
minimal/debootstrap intersection. It preserves known seed alternatives, expands
explicit source/virtual seeds, and writes a fresh `metapackage-map` plus sorted
`SEED-ARCH` and `SEED-recommends-ARCH` files. Existing output directories are
rejected and all logical input validation finishes before output creation.

This stage follows explicit seed planting, rather than dependency closure:
archive Depends/Recommends and seed blocklist weeding are not expanded into
these files. It retains the reference updater's distinction between excluding
essential Depends and retaining essential Recommends. Source recommendation
entries also follow the reference's planted classification. Remote acquisition,
live debootstrap selection/version tracking, changelog/delta maintenance and
qualification on pinned real inputs remain open. The new
`test-list-parity.py` runs the pinned updater's unchanged map/list code against
local synthetic archives, freezing only debootstrap's package-set/version
boundary. Linux [run 40236407482](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/40236407482)
on `ff754d3c` passed 56 byte-for-byte map/list file comparisons across four
configurations. The same run passed all candidate crate checks, including 26
seed-compiler tests, and repeated the existing eight substvars and 22 profile
package-set comparisons.

`metapackage-substvars DIRECTORY ARCHITECTURE PACKAGE` supplies the next build
stage in Rust. It reads the supplied `metapackage-map`, selects that package's
`SEED-ARCHITECTURE` and `SEED-recommends-ARCHITECTURE` files, and writes a fresh
fragment containing `germinate:Depends` and `germinate:Recommends`. Relationships
are sorted and deduplicated, with one relationship per input line; empty lists
omit the variable. Unmapped packages
produce an empty fragment. Use the binary package architecture (`all` for an
architecture-independent package). The command validates both lists before
printing, rejects ambiguous maps and unsafe file names, and does not merge an
existing substvars file. Supply its fragment to `dpkg-gencontrol` along with
other build substitutions. The native package builder below consumes these same fragments.

The file and substitution contract is referenced from Elementary metapackages
commit `6e6466507f7f5b32e73594c5e727a49f0be58d0f` and Germinate 2.49's
`dh_germinate_metapackage` documentation. Both references declare GPL version 2
or later. No upstream implementation or seed text is vendored into this crate.
The source archive's verified SHA-256 is recorded in
`../elementary-build-inputs.json`.

On Linux with `debhelper` and `dpkg-dev`, run the reference comparison:

```sh
python3 mseries/rust/seed-compiler/test-metapackage-parity.py mseries/rust/seed-compiler/target/release/elementary-seed-compiler
```

It downloads and verifies the pinned Germinate archive, runs its unmodified
helper with real Debhelper, and compares eight amd64/arm64 cases, including
`Architecture: all`, unmapped packages, duplicate relationships, alternatives,
and recommendation-only lists. The Rust candidate workflow runs this check.
Linux run [40234661042](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/40234661042)
on `8445173e` passed all eight comparisons with Debhelper 13.31ubuntu1.
The corrected resolver revision `28eec704` repeated these successfully in
[run 40235036913](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/40235036913). This
receipt covers the substvars stage, not full seed expansion or package parity.

`test-seed-parity.py` adds 22 synthetic profile package-set comparisons against
the same unmodified Germinate release using system Python and `python3-apt`.
It checks both architectures, blocklisted dependencies/alternatives/providers,
inner and outer inheritance scope, recommendation roots, and per-seed features.
Run 40235036913 passed all 22 comparisons on `28eec704`. It compares the union
of runtime package membership; reason output, installability and full solver behavior are
separate gates.

The upstream `elementary/seeds` and `elementary/platform` revisions are recorded
in `../elementary-build-inputs.json`. Their licenses are unverified, so no
upstream seed data is copied into this crate. Parsing behavior is based on the
public Germinate format documentation; this is not yet an equivalence claim
against Germinate's implementation.

```sh
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- inspect-seed FILE arm64
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- inspect-structure STRUCTURE elementary.resolute desktop platform.resolute=/path/to/platform/STRUCTURE
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- resolve-seed /path/to/seeds/STRUCTURE elementary.resolute desktop arm64 platform.resolute=/path/to/platform
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- resolve-seed-packages /path/to/seeds/STRUCTURE elementary.resolute desktop arm64 Packages platform.resolute=/path/to/platform
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- expand-source Packages arm64 elementary-desktop
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- resolve-packages Packages arm64 elementary-desktop
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- generate-metapackage-lists /path/to/metapackages /path/to/seeds/STRUCTURE elementary.resolute /path/to/indices /path/to/new-output platform.resolute=/path/to/platform
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- metapackage-substvars /path/to/metapackages arm64 elementary-desktop
```

Next parity gates: fresh real-source/archive list generation,
feature-aware end-to-end generation, archive precedence/conflict semantics, and
complete Germinate/apt solver comparisons. Synthetic stage receipts do not
establish whole-project or image/runtime parity.


`build-metapackages SOURCE-DIR LIST-DIR HOST-ARCH NEW-OUTPUT-DIR` builds the
metadata-only Elementary metapackages directly in Rust. It selects amd64/arm64
or `all` binaries, renders control substitutions and relationships, installs
copyright/changelog documentation, and writes reproducible Debian 2.0 packages
with ustar/gzip members and md5sums. It invokes no host packaging/archive tools
and never runs `debian/rules`. An explicit `--epoch=SECONDS` takes precedence over
`SOURCE_DATE_EPOCH`, then the first changelog date. `--full-changelog` and
`DEB_BUILD_OPTIONS=notrimdch` disable the Debhelper 13.31 default trimming policy.
The output directory must be new; all logical validation/building completes
before it is created.

This supports the pinned Elementary source's minimal `dh --with germinate`
layout. It rejects custom rules, payload/maintainer-script packaging files,
unknown binary fields/substitutions and binary-only changelog entries rather
than silently losing behavior. It is not a general replacement for dpkg or
Debhelper. Compression uses locked pure-Rust `flate2`; `chrono` parses source
dates and `md-5` provides the Debian payload checksums. No upstream packaging
implementation is copied into this crate. Format/behavior references:
[deb(5)](https://manpages.debian.org/trixie/dpkg-dev/deb.5.en.html),
[dpkg-gencontrol(1)](https://manpages.debian.org/trixie/dpkg-dev/dpkg-gencontrol.1.en.html),
[deb-substvars(5)](https://manpages.debian.org/trixie/dpkg-dev/deb-substvars.5.en.html),
and Debhelper 13.31's installed documentation/changelog policy.

Local checks pass 29 crate tests, strict Clippy/release build and 40 package
archive/checksum/date/reproducibility checks. `test-deb-parity.py` adds Linux
comparisons with actual `dpkg-gencontrol`, `dpkg-deb`, Debhelper documentation
helpers and the pinned Germinate helper. Its 40 packages span both hosts,
native/non-native and epoch versions, trimmed/full changelogs, `all`/wildcard
architecture selection, multiline descriptions, relationship reduction and
long ustar paths. Linux [run 40238235136](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/40238235136)
on `ccff41c52ef002927bf782ff14ae9c4f8c39419b` passed all 40 comparisons using
dpkg 1.23.7ubuntu1 and Debhelper 13.31ubuntu1, alongside all existing candidate
checks. This qualifies the tested synthetic metadata/documentation semantics.
Byte equality with Debian compression, fresh real-source/archive list generation
and complete OS build parity remain unqualified.

```sh
python3 mseries/rust/seed-compiler/test-deb-parity.py mseries/rust/seed-compiler/target/release/elementary-seed-compiler
```


`test-upstream-deb-parity.py` now downloads the SHA-256-pinned Elementary
metapackages source at `6e6466507f7f5b32e73594c5e727a49f0be58d0f` and builds
its eight version 1.582 packages for amd64/arm64 with trimmed/full changelogs.
Local native-only checks pass all 32 cases. The Linux comparison runs the
unchanged `debian/rules` clean/binary targets (including compat level 7) with
checksum-pinned Germinate 2.49's helpers and sequence module in an isolated tool
path. It uses fakeroot for the reference binary build. This comparison is
now qualified by Linux [run 40238779709](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/40238779709)
on `317c69eb08baf7e34c8fa0d14fbc8e00370bc268`. It compares control file membership,
metadata, decompressed installed
documentation and checksums, and verifies reproducible native rebuilds. Each
package's Installed-Size is checked on its own compressed bytes at the actual
control-generation stage; different compression can legitimately change that
number. Source/list text remains temporary. CI retains a hash-only JSON receipt
for 30 days, with source/package identities and native/reference archive digests.
The verified fingerprints are retained permanently in
[`elementary-1.582-parity.json`](elementary-1.582-parity.json). All 32 native
archive hashes match separate macOS arm64 builds. Full-changelog packages report
55 KiB installed size in Rust versus 54 KiB in the reference because compression
bytes differ; each native value independently matches dpkg's accounting on that
payload. Installed documents match exactly after decompression.

```sh
python3 mseries/rust/seed-compiler/test-upstream-deb-parity.py mseries/rust/seed-compiler/target/release/elementary-seed-compiler --report /tmp/elementary-package-receipt.json
```

This qualifies the checked-in upstream map/list-to-package stage. Regenerating
those lists from live archives/seeds, PPA membership/installability, arbitrary
Debian packaging and OS image/runtime admission remain separate gates.
