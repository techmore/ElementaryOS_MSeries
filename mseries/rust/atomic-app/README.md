# Atomic app activation

This dependency-locked Rust CLI implements the generic staged-release store
specified in `mseries/ATOMIC-APP-DEPLOYMENT.md`. It keeps releases and generation records, takes
a per-app `flock`, validates release symlinks and entrypoints, syncs staged data,
and atomically replaces the selected generation. Status, launch, rollback, and
the post-activation directory-sync warning keep the Python CLI's interface.

`mseries/atomic-app.py` is retained as a behavioral reference. The integration
suite exercises both CLIs against the same release, rollback, path-safety,
concurrency, and launch scenarios. The Rust binary is built into the Apple
Silicon factory overlay at `/usr/libexec/mseries/atomic-app`. Signal's installers
remain as supplied by `dev` while the owner-deferred Signal/Messages build-out
is incomplete; see `mseries/MESSAGING-STATUS.md`. This candidate does not change
that app's acceptance or deployment status.
