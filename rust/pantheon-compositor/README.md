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
basic keyboard/pointer handling, xdg-shell windows and popup grabs, move/resize
grabs, clipboard and drag-and-drop. On the first non-empty toplevel commit,
windows are centered and cascaded on the first output, activated, and given
keyboard focus; when the focused toplevel is destroyed, focus moves to the
topmost remaining app window. Toplevel destruction removes placement tracking.
Absolute
pointer input maps to the complete logical output bounds. These behaviors have
compile checks but no new runtime qualification. It now advertises the existing Pantheon desktop-shell
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

`native-drm` is an opt-in Cargo feature that stages Smithay's DRM, GBM,
libinput, udev, libseat, EGL, and multi-GPU dependencies. The current executable
still starts through Winit. Behind this feature, `native.rs` can initialize a
hardware EGL/GBM renderer on a libseat GPU and register it with Smithay's
multi-GPU manager. It is not yet called by the executable and does not open a
KMS output, allocate scanout buffers, or drive native input. Default and
feature-enabled `cargo check` and `cargo build` pass locally after installing
the host `libseat-dev` package; none of those commands initializes a native
session.

With `native-drm` enabled, `pantheon-drm-probe` safely enumerates EGL devices
without acquiring DRM master or changing display modes. On the current M-series
host it finds EGL rendering on `/dev/dri/card1` (`/dev/dri/renderD128`, Asahi)
but KMS resource queries there return `Operation not supported`. The Apple
display-controller `/dev/dri/card2` owns KMS: `eDP-1` is connected at
3024×1964@120 Hz and `DP-2` is connected with 3840×2160@30 Hz and 1920×1080@60
Hz modes; `HDMI-A-1` is disconnected. Card2 has no EGL device. The native backend
therefore needs Smithay's multi-GPU render/import path from Asahi to Apple KMS;
single-node setup is not enough. This probe reads connector state and modes but
does not force a connector reprobe or test modesetting.

Relative pointer motion now updates Wayland pointer focus and dispatches motion
through active compositor grabs; coordinates are clamped to the mapped output
bounds. This allows the existing xdg move/resize grab implementations to receive
physical pointer motion. Multi-output bounds, pointer constraints, and hardware
input remain unqualified.

Xdg popup requests now resolve their root to a managed toplevel and install
Smithay's popup keyboard and pointer grabs, including the serial checks needed
to preserve valid nested grabs. Popup interaction has only been build-checked;
it has not yet been exercised with a real application menu.

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
`GetCurrentState` query it calls, with every tracked output's current mode,
logical position, scale, and primary status. Output add/update/remove changes
increment the state serial and emit `MonitorsChanged`. The service remains
read-only and does not apply monitor modes or layouts. The isolated
Wingpanel run no longer reports missing DisplayConfig or Shell keybinding
services. Pressing `Super+N` in the nested window produced the registered
`AcceleratorActivated` signal. The sound indicator's media-key registrations
also completed without its prior D-Bus error; physical media-key activation has
not been checked. This is evidence of panel compatibility at the
protocol/rendering path, not full session qualification. Applying monitor
modes, Dock behavior and M-series DRM/KMS remain unqualified.
