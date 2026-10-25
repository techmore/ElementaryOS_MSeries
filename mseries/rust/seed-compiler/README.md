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
command applies seed package/source blocklists to explicit roots, then expands
archive relationships unchanged. A blocked package can therefore appear again
as a dependency, and the resolver does not silently choose another alternative
to work around a broken package relationship. `follow-recommends` in STRUCTURE
or the selected seed enables recommendation closure; the selected seed's
`no-follow-recommends` overrides that default, and the CLI flag can force it on.
Archive Recommends and parenthesized seed recommendations are emitted as
separate package sets. Build-dependency feature flags, archive priorities and
conflicts like apt, snap revision selection, and `.deb` metapackage generation
remain unimplemented.

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
other build substitutions. This implements one build stage; map/list generation,
complete Debian control generation, and `.deb` assembly are still open.

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
The macOS host passes Rust unit/build checks; the Linux comparison has not run
at this checkpoint and does not establish seed expansion or full package parity.

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
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- metapackage-substvars /path/to/metapackages arm64 elementary-desktop
```

Next parity gates: feature-aware end-to-end generation, archive precedence and
conflict semantics, differential comparison against Germinate/apt, metapackage
map generation, and reproducible Debian control outputs for both arm64 and
amd64. Unit tests only validate the implemented candidate behavior; Germinate
or apt parity has not been demonstrated.
