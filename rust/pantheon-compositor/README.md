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

To exercise the Pantheon protocol against the nested socket, build both binaries
and start the compositor with its probe client:

```sh
cargo build -p pantheon-compositor --bins
cargo run -p pantheon-compositor -- --run target/debug/pantheon-shell-probe
```

The probe binds the shell and panel v2 interfaces, creates a Wayland surface,
and sends `get_panel`, anchor, size, hide-mode, and offset requests. It has
passed under Xvfb with Mesa llvmpipe. It does not attach a buffer or xdg role, so
it validates protocol dispatch rather than panel rendering or Wingpanel/Dock
integration.

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

The session bus also exposes the small `org.gnome.Shell` accelerator API used
by Wingpanel and its sound indicator. Accelerator registrations are matched
through the compositor's active XKB state and reported with
`AcceleratorActivated`; `ShowOSD` is currently a no-op, and lock-screen action
modes are not implemented.

The code is based on Smithay's `smallvil` learning compositor at pinned commit
`023b78b1c5a05ca512767cacc07efca55fae8be4`; see `SMITHAY-LICENSE.txt`. Keep the
upstream revision pinned until an explicit upgrade is reviewed. The Pantheon
protocol XML is based on elementary/Gala commit `f0791434` (LGPL-2.1-or-later)
with the repository's v2 `set_offset` extension; see `THIRD-PARTY.md`.
Local `cargo check -p pantheon-compositor --bin pantheon-shell-probe` and
`cargo build -p pantheon-compositor --bins` pass. The compositor stayed alive
for the 12-second Xvfb integration smoke and the probe completed its protocol
requests. Installed Wingpanel 8.0.4 also connected in an isolated D-Bus/Xvfb
run forced to Wayland. Its client trace confirms it bound the shell global,
sent `get_panel`, `set_anchor(top)`, and `set_hide_mode(never)`, then allocated
and attached shared-memory buffers. Wingpanel requires
`org.gnome.Mutter.DisplayConfig`; the compositor now serves the read-only
`GetCurrentState` query it calls, with the current nested output and logical
layout mode, and emits `MonitorsChanged` when the output resizes. The isolated
Wingpanel run no longer reports missing DisplayConfig or Shell keybinding
services. Pressing `Super+N` in the nested window produced the registered
`AcceleratorActivated` signal. The sound indicator's media-key registrations
also completed without its prior D-Bus error; physical media-key activation has
not been checked. This is evidence of panel compatibility at the
protocol/rendering path, not full session qualification. Applying monitor
modes, Dock behavior and M-series DRM/KMS remain unqualified.
