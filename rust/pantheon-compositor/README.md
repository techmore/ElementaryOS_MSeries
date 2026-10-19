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
currently active desktop. On 2026-10-19 the opt-in LightDM session reached a
real M1 Pro scanout: Apple DRM plane 0 had an active 3024x1964 AR30 framebuffer
allocated by `pantheon-compositor`, and the owner confirmed the desktop was
visible and usable. This is first-login evidence, not daily-use qualification;
the top panel and bottom dock were absent, startup felt slow, and performance,
crash recovery and external-monitor behavior remain open.
Fatal DRM event/frame-completion errors end the process with a failure status;
three consecutive native render failures do likewise. In the experimental
session service this allows systemd's bounded restart and shutdown policy to
run. These failure paths have only been compile-checked, not induced on the
active display.

The experimental systemd user service uses `--notify-systemd` to send `READY=1` to
`NOTIFY_SOCKET` after the Wayland listener and selected backend initialize. On
the native path, that includes renderer and connected-output initialization.
The flag fails startup if systemd did not provide the notification socket. No
service unit or login-session entry is installed by the compositor build.
The separate Pantheon login-session payload is maintained in
[`../../mseries/pantheon-rust-compositor/session/`](../../mseries/pantheon-rust-compositor/session/README.md).
Its `PANTHEON_WAYLAND_DISPLAY` environment override selects a fixed socket for
the session service; without it the compositor chooses an available socket.
The ARM64 package has been installed on the M1 Pro, and LightDM lists the
separate **Pantheon (Rust compositor, experimental)** session. It reached
native scanout on the M1 Pro, but still lacks a complete shell: Wingpanel and
the bottom dock did not start. Gala remains the rollback session.

To exercise the Pantheon protocol against the nested socket, build both binaries
and start the compositor with its probe client:

```sh
cargo build -p pantheon-compositor --bins
cargo run -p pantheon-compositor -- --run target/debug/pantheon-shell-probe
```

The probe binds the shell and panel v2 interfaces, creates a Wayland surface,
and sends `get_panel`, anchor, size, hide-mode, and offset requests. The probe
passes under Xvfb with Mesa llvmpipe and a private runtime directory. The
compositor caches the connecting process identity before global advertisement
so the IBus-only input-method filter does not re-enter the Wayland backend while
it holds its dispatch lock. It also uses Smithay's `XWaylandClientData` for the
XWayland client's compositor state. The probe does not attach a buffer or xdg
role, so it validates protocol dispatch rather than panel rendering or
Wingpanel/Dock integration.

## Current limits

This is an early compositor implementation, not a Mutter port or a Pantheon
replacement yet. The target is only the
M-series/Pantheon behavior documented in
[`../../mseries/pantheon-rust-compositor/EXPERIENCE-REQUIREMENTS.md`](../../mseries/pantheon-rust-compositor/EXPERIENCE-REQUIREMENTS.md).
The compositor reads `org.gnome.desktop.background` at startup, loads a local
PNG/JPEG/WebP wallpaper and renders it behind app surfaces; `picture-options=zoom`
uses a centered crop. A private Xvfb screenshot showed the configured
elementary wallpaper behind a GTK Zenity window. The compositor now checks the
shared settings every two seconds, reloads only when the wallpaper URI or crop
mode changes, and requests an output redraw. The update path is build-checked;
live changes and native image rendering still need runtime qualification.
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

The Dock's existing hide modes now drive compositor visibility: maximize and
overlap modes hide while their condition is true, `always` starts hidden, and
pointer motion at the panel's output edge reveals it. Hiding releases the
panel's work area; revealing it restores that area and reconfigures managed
windows. The active host Dock setting is `overlapping-window`. A nested Xvfb
run of Dock 8.3.3 bound the shell protocol, requested anchor and hide mode, and
attached shared-memory buffers. The compositor now exposes the Gala
`DesktopIntegration` D-Bus contract used by Dock, including a live window list
and focus requests; a temporary Wayland window appeared in `GetWindows`, and
`FocusWindow` routed back to the compositor. The compositor tracks windows
across workspaces, switches visible windows, and supports Dock requests to
create the dynamic workspace, move windows, reorder workspaces and focus a
window across workspaces. An isolated Xvfb run with a temporary Wayland client
exercised creation, movement, switching and focus. Gala's multitasking view is
not implemented. Stock Dock also logged its existing
workspace-startup race during the nested smoke, so full Dock behavior remains
unqualified. Hiding is immediate; blur and multi-output Dock behavior remain
open. The
compositor implements Smithay's `ext-session-lock-v1`: it blanks each output
until its lock surface is ready, confines input to the locker, and restores the
prior keyboard focus on unlock. It exports the observed
`org.gnome.ScreenSaver` API and launches `gtklock` on `Lock`/`SetActive(true)`;
set `PANTHEON_LOCK_COMMAND` to select another executable. The locker and
D-Bus/session path still need runtime qualification. Widget, extended-behavior
and greeter protocol requests are accepted but currently have no behavior.

Rootless XWayland startup, X11 window management, keyboard routing, session
`DISPLAY` propagation, clipboard and PRIMARY selection bridging are implemented.
A private Xvfb smoke mapped an X11 Zenity window, typed `wayland input 42` into
it, and observed its focused `zenity` entry on workspace 0 through the live
window-list D-Bus method. Clipboard/PRIMARY transfer, activation from the
desktop session, and other X11 workflows remain unqualified. Native multi-output
enumeration and hotplug reconciliation exist; configuration rejects output
disabling, mirroring, unsupported monitor properties and nested mode changes.
Monitor modeset/rollback and hotplug remain unqualified on hardware. Smithay's
text-input-v3 and input-method-v2 globals are now wired for the trusted IBus
daemon, including input-method popup tracking. A private Xvfb test with the
release binary and a GTK Wayland Zenity field committed `konnichiha` as
`こんにちは` through IBus/Mozc `mozc-jp` after enabling Hiragana mode in the
private profile. Host source switching, the F5 workflow and native keyboard
input remain unqualified. Accessibility protocol
support, screen-sharing portals, touch input and production crash recovery
remain unimplemented or unqualified; add them only when an observed Pantheon
workflow requires them.

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
without acquiring DRM master or changing display modes. In the 2026-10-19
snapshot it finds EGL rendering on `/dev/dri/card1` (`/dev/dri/renderD128`,
Asahi) but KMS resource queries there return `Operation not supported`. The
Apple display-controller `/dev/dri/card2` owns KMS and the connected internal
`eDP-1` at 3024×1964@120 Hz; external connectors are currently disconnected.
Card2 has no EGL device. The probe allocates render/scanout GBM buffers on
Asahi at the internal panel's preferred 3024×1964 size and imports them into
Apple GBM. It registers each imported buffer with `ADDFB2` and immediately
removes the unassigned framebuffer. Imports succeeded for AB30, AR30, AB24 and
AR24; framebuffer creation succeeded for AR30, AB24 and AR24, while AB30 was
rejected with `EINVAL`. Native output formats now prefer the three formats
accepted by Apple KMS and omit AB30. This qualifies cross-device import and
framebuffer registration at the preferred panel size. It does not prove plane
acceptance, atomic modesetting, or visible scanout. The probe does not acquire
DRM master, attach a framebuffer to a plane, force a connector reprobe, or
change modes. A follow-up read-only plane query found AR30, AB24 and AR24 in
the advertised format lists of all three Apple KMS planes; the query returned
no current CRTC or framebuffer assignment. This confirms format advertisement
only, not plane routing or acceptance by a real modeset.

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
`AcceleratorActivated`. `ShowOSD` now renders a short brightness or volume
indicator, including the requested output connector and normalized level when
provided. It uses compositor-drawn icons and a meter; text labels and the full
Pantheon OSD styling are not implemented. Lock-screen action modes remain
unimplemented. Separately, the observed `org.gnome.ScreenSaver` interface
launches the configured session locker; its action and authentication path
still need runtime qualification.

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
`org.gnome.Mutter.DisplayConfig`; the compositor serves its `GetCurrentState`
query with every tracked output's current mode, logical position, scale, and
primary status. A 2026-10-19 rerun with `GSK_RENDERER=cairo` and the host's
input-source settings copied into a private GSettings keyfile showed Wingpanel
binding the shell global, sending `get_panel`, anchor and hide-mode requests,
receiving the compositor keymap and keyboard focus, and attaching 69 shared-
memory buffers without a critical assertion. A run with empty input-source
settings had emitted an `io.elementary.panel.keyboard` assertion; that result
was caused by the incomplete test fixture. Panel keyboard interaction still
needs direct input qualification. Native outputs list connector modes
reported by DRM and mark active/preferred entries; the nested backend reports
its actual Winit size.
`ApplyMonitorsConfig` validates serials, connector assignments, mode IDs, scale
and transform. Native DRM mode changes use Smithay's shared output manager and
roll back earlier changes if a later mode fails. Temporary layout, scale and
transform changes update the Wayland outputs. Method 2 saves a per-user profile
at `$XDG_CONFIG_HOME/pantheon-rust-compositor/monitors.conf` (or
`~/.config/pantheon-rust-compositor/monitors.conf`); native startup restores
saved modes and layout. Native output disable/re-enable is implemented by
removing/recreating the KMS output, and disabled connectors stay in the monitor
inventory without a logical placement. Existing seven-field profiles remain
enabled by default; new profiles store an enabled flag. During a native
transition the backend keeps existing outputs live while staging the requested
set. It can reassign a CRTC to a different connector and mode in one DRM surface
commit, including on a single-CRTC device when that encoder route is supported.
It retires outputs outside the requested set after all requested outputs are
active, and attempts to restore the prior set, modes and layout if activation
or modesetting fails. This path compiles but still needs hardware and failure
qualification. Mirroring, unsupported properties and nested Winit monitor-set
changes are rejected. Output and
configuration updates increment the serial and emit `MonitorsChanged`. Default
and native DRM builds compile, but no native session or live monitor change has
been run from this development session. Disable/re-enable, reconnect and
combined mode/layout rollback remain runtime-unqualified. The compositor also
advertises `wp_fractional_scale_v1`
and `wp_viewporter`, setting window surfaces' preferred scale from their first
mapped output and refreshing preferences during rendering and after monitor
configuration changes. Cross-output moves and fractional rendering quality
still need an isolated client/runtime check. The compositor implements
`xdg-activation-v1`: it accepts recent tokens tied to the compositor seat,
consumes tokens on use, and raises/focuses mapped target windows unless the
session is locked. `xdg_toplevel.set_minimized` unmaps and retains windows; a later
valid activation request restores them at their previous location. Activation
and minimize/restore flows still need an isolated client check.
The isolated
Wingpanel run no longer reports missing DisplayConfig or Shell keybinding
services. Pressing `Super+N` in the nested window produced the registered
`AcceleratorActivated` signal. The sound indicator's media-key registrations
also completed without its prior D-Bus error; physical media-key activation has
not been checked. This is evidence of panel compatibility at the
protocol/rendering path, not full session qualification. Monitor configuration
runtime, Dock behavior and M-series DRM/KMS remain unqualified.
