# Atomic app activation

This dependency-locked Rust CLI implements the staged-release store used by the
opt-in Signal ARM64 installer. It keeps releases and generation records, takes
a per-app `flock`, validates release symlinks and entrypoints, syncs staged data,
and atomically replaces the selected generation. Status, launch, rollback, and
the post-activation directory-sync warning keep the Python CLI's interface.

`mseries/atomic-app.py` is retained as a behavioral reference. The integration
suite exercises both CLIs against the same release, rollback, path-safety,
concurrency, and launch scenarios. The Rust binary is built into the Apple
Silicon factory overlay at `/usr/libexec/mseries/atomic-app`; the Signal
installer copies that binary into the user's libexec directory before enabling
the opt-in generation selector.
