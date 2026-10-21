# Elementary seed compiler (Rust migration candidate)

This independent crate begins the Rust replacement for the seed-reading part of
`elementary/metapackages`. It parses Germinate `STRUCTURE` inheritance and seed
records, including feature declarations, package/source entries, recommendations,
blacklists, snaps, and architecture qualifiers. Its library composes explicitly
provided included collections and resolves profile inheritance, architecture
filters, and seed-level blacklists. An independently authored archive layer now
parses Debian `Packages` control stanzas and relationships, expands source names
to binaries, and computes a basic architecture-aware closure for Depends,
Pre-Depends, and optionally Recommends. The CLI exposes these seed and archive
operations separately. It does not yet apply Germinate features to package
resolution, combine all inputs in one generator run, resolve archive priorities
and conflicts like apt, select snap revisions, or generate `.deb` metapackages.

The upstream `elementary/seeds` and `elementary/platform` revisions are recorded
in `../elementary-build-inputs.json`. Their licenses are unverified, so no
upstream seed data is copied into this crate. Parsing behavior is based on the
public Germinate format documentation; this is not yet an equivalence claim
against Germinate's implementation.

```sh
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- inspect-seed FILE arm64
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- inspect-structure STRUCTURE elementary.resolute desktop platform.resolute=/path/to/platform/STRUCTURE
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- resolve-seed /path/to/seeds/STRUCTURE elementary.resolute desktop arm64 platform.resolute=/path/to/platform
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- expand-source Packages arm64 elementary-desktop
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- resolve-packages Packages arm64 elementary-desktop
```

Next parity gates: feature-aware end-to-end generation, archive precedence and
conflict semantics, differential comparison against Germinate/apt, metapackage
map generation, and reproducible Debian control outputs for both arm64 and
amd64. Unit tests only validate the implemented candidate behavior; Germinate
or apt parity has not been demonstrated.
