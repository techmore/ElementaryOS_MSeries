# pantheon-compositor

Mutter-minimal Rust compositor for the M-series/Pantheon experience. The
default backend is a nested Wayland compositor using Smithay's Winit backend;
an explicit, feature-gated native backend is also wired for M-series DRM/KMS,
libseat and libinput startup. This is still an early development harness, not
a drop-in Gala replacement or a qualified login session.

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

The native backend is selected explicitly and requires native dependencies:

```sh
cargo run -p pantheon-compositor --features native-drm -- --backend native
```

Native startup acquires the active libseat session and initializes a DRM/KMS
output. It takes over the display device, so do not launch it inside the
currently active desktop. It is not yet runtime-qualified on M-series hardware.

The experimental systemd user service uses `--notify-systemd` to send `READY=1` to
`NOTIFY_SOCKET` after the Wayland listener and selected backend initialize. On
the native path, that includes renderer and connected-output initialization.
The flag fails startup if systemd did not provide the notification socket. No
service unit or login-session entry is installed by the compositor build.
The separate Pantheon login-session payload is maintained in
[`../../mseries/pantheon-rust-compositor/session/`](../../mseries/pantheon-rust-compositor/session/README.md).
Its `PANTHEON_WAYLAND_DISPLAY` environment override selects a fixed socket for
the session service; without it the compositor chooses an available socket.
The payload has not been installed or runtime-qualified.

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

This is an early compositor implementation, not a Mutter port or a Pantheon
replacement yet. The target is only the
M-series/Pantheon behavior documented in
[`../../mseries/pantheon-rust-compositor/EXPERIENCE-REQUIREMENTS.md`](../../mseries/pantheon-rust-compositor/EXPERIENCE-REQUIREMENTS.md).
It currently has one nested output,
basic keyboard/pointer handling, xdg-shell windows and popup grabs, move/resize
grabs, clipboard, drag-and-drop and a compositor-rendered pointer. Client-set
cursor surfaces are rendered over windows on nested and native outputs; named
cursor requests currently use a built-in arrow fallback, not the installed
elementary cursor theme. On the first non-empty toplevel commit,
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
animated hiding, blur, overview behavior and multi-output work-area updates for
already maximized windows are not complete. The compositor now implements
Smithay's `ext-session-lock-v1`: it blanks each output until its lock surface is
ready, confines input to the locker, and restores the prior keyboard focus on
unlock. A Pantheon locker/authentication UI and session action wiring are not
provided, and the protocol has not yet been runtime-qualified. Widget,
extended-behavior and greeter protocol requests are accepted but currently have
no behavior. Touch input, multi-monitor configuration, accessibility, IBus,
Xwayland, screen-sharing portals and production crash recovery also remain
unimplemented.

`native-drm` enables Smithay's DRM, GBM, libinput, udev, libseat, EGL, and
multi-GPU dependencies. The executable defaults to nested Winit; only
`--backend native` starts the native session. That path initializes a hardware
EGL/GBM renderer and a separate connected KMS output, publishes it as a
Wayland output, assigns libinput to the active seat, and registers redraw,
vblank, and session pause/resume sources with calloop. It initializes all
connected outputs with compatible CRTCs on the selected KMS device, puts eDP
first, and places other outputs to its right. It polls connector state while
the session is active, adds newly connected outputs, removes disconnected
outputs, updates Wayland/DisplayConfig state, and moves windows back onto a
remaining display when needed. This path is compile-checked only; physical
hotplug, mode changes, user-configured arrangement, session-shell integration,
and M-series scanout/input behavior remain unqualified. Default and
feature-enabled `cargo check --bins` and `cargo build --bins` pass locally;
builds do not initialize or take over a native session.

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
bounds. If all outputs are disconnected, relative motion is ignored until a
display returns instead of panicking on empty bounds. This allows the existing
xdg move/resize grab implementations to receive physical pointer motion.
Multi-output bounds, pointer constraints, and hardware input remain
unqualified.

Xdg popup requests now resolve their root to a managed toplevel and install
Smithay's popup keyboard and pointer grabs, including the serial checks needed
to preserve valid nested grabs. Popup interaction has only been build-checked;
it has not yet been exercised with a real application menu.

The session bus also exposes the small `org.gnome.Shell` accelerator API used
by Wingpanel and its sound indicator. Accelerator registrations are matched
through the compositor's active XKB state and reported with
`AcceleratorActivated`; `ShowOSD` is currently a no-op, and lock-screen action
modes are not implemented. This is distinct from the compositor's
`ext-session-lock-v1` protocol, which now accepts a locker client but still
needs session-service wiring and runtime qualification.

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
