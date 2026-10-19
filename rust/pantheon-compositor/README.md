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
and drag-and-drop. It now advertises the existing Pantheon desktop-shell
protocol v2: panel surfaces can set their anchor, size, hide mode and offset;
the compositor places those surfaces and uses exclusive panel geometry for
xdg-toplevel maximize requests. The Dock's M-series offset request is therefore
available to protocol-v2 clients. When panel commits change the exclusive work
area, already maximized windows are reconfigured to its new bounds; unchanged
panel repaints do not issue redundant configures.

This is only the first shell integration slice. Autohide/overlap tracking,
animated hiding, blur, overview behavior, multi-output work-area updates for
already maximized windows, and session/lock integration are not complete. Widget,
extended-behavior and greeter protocol requests are accepted but currently have
no behavior. Touch input, DRM/KMS, libinput device management, multi-monitor
configuration, accessibility, IBus, Xwayland, screen-sharing portals and
production crash recovery also remain unimplemented.

The code is based on Smithay's `smallvil` learning compositor at pinned commit
`023b78b1c5a05ca512767cacc07efca55fae8be4`; see `SMITHAY-LICENSE.txt`. Keep the
upstream revision pinned until an explicit upgrade is reviewed. The Pantheon
protocol XML is based on elementary/Gala commit `f0791434` (LGPL-2.1-or-later)
with the repository's v2 `set_offset` extension; see `THIRD-PARTY.md`.
`cargo check -p pantheon-compositor` passes on the local build host. The nested
event loop stayed up in an 8-second Xvfb smoke run; no Wayland client connected.
Wingpanel/Dock behavior and M-series hardware remain unqualified.
