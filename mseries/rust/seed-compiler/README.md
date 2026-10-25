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
```

Next parity gates: feature-aware end-to-end generation, archive precedence and
conflict semantics, differential comparison against Germinate/apt, metapackage
map generation, and reproducible Debian control outputs for both arm64 and
amd64. Unit tests only validate the implemented candidate behavior; Germinate
or apt parity has not been demonstrated.
