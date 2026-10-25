# Rust ISO assembly

`assemble-iso.sh` is the compatibility entry point; it delegates the image
assembly workflow to this Rust program. The Rust implementation prepares the
APT disc metadata, copies the generated `iso_root`, applies release and
architecture substitutions, and invokes the pinned elementary xorriso
container to build the live filesystem and installer ISO.

The program expects the same `mkosi.output` layout produced by the Justfile
image recipes, `systemd-analyze`, `rsync`, `gzip`, `sudo`, and `podman`. Profile
and squashfs compression level remain configurable through `PROFILE` and
`SQUASHFS_LEVEL`. The image build still relies on the upstream xorriso
container's shell commands internally.

This candidate has not yet passed a full Linux image build or end-to-end parity
review. The local macOS development host does not provide the required Linux
image toolchain.
