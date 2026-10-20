# ISO volume label

This crate exposes `volume_label` as a library for image assembly and retains a
small CLI for direct parity comparison. It normalizes the profile and
architecture to the same uppercase ASCII letters, digits, and underscores as
the previous shell helper, then limits the ISO 9660 volume ID to 32 bytes.

`mseries/iso-label.sh` and its existing fixture remain as the differential
reference while the Rust caller is in use. `test-parity.py` compares both
implementations across ordinary, truncation, filtering, newline, and empty-input
cases. This crate is dependency-free and remains independent of other Rust
projects.
