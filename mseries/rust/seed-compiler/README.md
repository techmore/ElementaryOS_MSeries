# Elementary seed compiler (Rust migration candidate)

This independent crate begins the Rust replacement for the seed-reading part of
`elementary/metapackages`. It parses Germinate `STRUCTURE` inheritance and seed
records, including feature declarations, package/source entries, recommendations,
blacklists, snaps, and architecture qualifiers. Its library composes explicitly
provided included collections and resolves profile inheritance, architecture
filters, and seed-level blacklists. The CLI is currently an audit tool; it does
not resolve Debian package metadata, follow package dependencies, expand source
packages, or generate `.deb` metapackages.

The upstream `elementary/seeds` and `elementary/platform` revisions are recorded
in `../elementary-build-inputs.json`. Their licenses are unverified, so no
upstream seed data is copied into this crate. Parsing behavior is based on the
public Germinate format documentation; this is not yet an equivalence claim
against Germinate's implementation.

```sh
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- inspect-seed FILE arm64
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- inspect-structure STRUCTURE elementary.resolute desktop platform.resolute=/path/to/platform/STRUCTURE
cargo run --manifest-path mseries/rust/seed-compiler/Cargo.toml -- resolve-seed /path/to/seeds/STRUCTURE elementary.resolute desktop arm64 platform.resolute=/path/to/platform
```

Next parity gates: differential comparison against Germinate, archive
`Packages` parsing, architecture-aware dependency closure, metapackage-map
generation, and reproducible Debian control outputs for both arm64 and amd64.
