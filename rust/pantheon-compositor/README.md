# pantheon-compositor

First development harness for the Mutter-minimal viable Rust effort: an
opt-in, nested Wayland compositor prototype using Smithay's Winit backend. It
runs in a window on an existing Wayland or X11 session and serves its own
Wayland socket. It does not open DRM/KMS, become a login session, or replace
Gala.

## Run

From the repository's `rust/` directory, with Smithay's native build dependencies
installed:

```sh
cargo run -p pantheon-compositor -- --run weston-terminal
```

Replace `weston-terminal` with a Wayland client installed on the development
system. With no `--run` argument, the nested compositor starts without launching
a client. `WAYLAND_DISPLAY` is changed only inside the compositor process after
the host Winit backend has initialized; the requested child uses the nested
socket. The active session's services and configuration are not touched.

## Current limits

This is a nested proof of rendering and basic interactive Wayland surfaces, not
a Mutter port or a Pantheon replacement yet. The target is only the
M-series/Pantheon behavior documented in
[`../../mseries/pantheon-rust-compositor/EXPERIENCE-REQUIREMENTS.md`](../../mseries/pantheon-rust-compositor/EXPERIENCE-REQUIREMENTS.md).
It currently has one nested output,
basic keyboard/pointer handling, xdg-shell windows, move/resize grabs, clipboard
and drag-and-drop. Touch input is not implemented. DRM/KMS, libinput device
management, multi-monitor configuration, accessibility, IBus, Xwayland, screen
sharing/remote-desktop portals, lock screen integration, Pantheon panel/dock
protocols, and production crash recovery are not implemented here.

The code is based on Smithay's `smallvil` learning compositor at pinned commit
`023b78b1c5a05ca512767cacc07efca55fae8be4`; see `SMITHAY-LICENSE.txt`. Keep the
upstream revision pinned until an explicit upgrade is reviewed. `cargo check
-p pantheon-compositor` passes on the development host; the runtime path has not
yet been exercised in a nested display or on M-series hardware.
