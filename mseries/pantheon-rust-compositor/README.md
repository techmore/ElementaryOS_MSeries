# Mutter-minimal viable Rust for elementaryOS M-series

Working title: **Mutter-Minimal-Viable-Rust_elementaryos-mseries**. The goal is
a focused Rust compositor for the Pantheon experience on our M-series machines.
Mutter is the proven reference; porting Mutter itself or reproducing all of its
features is explicitly out of scope.

The requirements come from the actual desktop work recorded in this repo:
normal app/window behavior, the M1 Pro's full-height/notch-aware panel, dock
visibility and work-area handling, supported display changes, window snapping,
input, and a reliable Pantheon login/lock/recovery path. Existing apps should
keep providing panel, dock and settings UI through a narrow shell contract.
Anything beyond those needs is conditional on a named app or workflow. The
prioritized list and upstream feature radar are in
[`EXPERIENCE-REQUIREMENTS.md`](EXPERIENCE-REQUIREMENTS.md).
For a stack drawing comparing existing elementary OS, Omarchy on Asahi, and
the proposed Pantheon MVP—along with a tested-versus-open status table—see
[`ARCHITECTURE-AND-STATUS.md`](ARCHITECTURE-AND-STATUS.md).

On 2026-10-19 the installed experimental session completed its first native
M1 Pro login and scanned out an AR30 3024x1964 framebuffer. The owner reported
that startup felt slow; the first Rust session had no Wingpanel, bottom dock,
or wallpaper/background. A timed LightDM rollback returned to Gala and
restored the background. Separate systemd user services have since been staged
to launch Wingpanel and Dock after the compositor. A local ARM64 package build
now includes those units; they are not installed or runtime-qualified. This
proves the native display path and rollback, not a
complete Pantheon session or a performance/stability improvement.

The nested prototype now handles the existing half-snap chords (`Super+Left`
and `Super+Right`) and quarter-snap chords (`Super+Alt+U/I/J/K` plus the
existing Super+keypad aliases). It computes rectangles from the focused
window's output work area, sends an xdg configure, and reflows managed tiles
when panel/output work areas change. Starting a compositor move/resize or
maximizing the window ends its managed tile. `Super+Shift+Left/Right` moves a
window to the adjacent output while preserving its work-area offset (or tile
position). Shortcuts load at session startup from the existing Mutter half-tile,
Pantheon quarter-tile, and GNOME monitor-move GSettings keys; built-in defaults
apply if those schemas or keys are unavailable. Restart the session after
changing bindings. These keyboard paths are compile checked only: runtime
shortcut and multi-output behavior remain open. During a compositor move, the
40-logical-pixel output corners show a translucent quarter preview; releasing
snaps the window, and Escape cancels the snap. Fixed-size windows are excluded.
The drag preview and release path also need runtime qualification.

At startup, the keyboard now loads the user's XKB model, active XKB layout,
options, and repeat settings from GNOME GSettings. This applies the M-series
`ctrl:swap_lwin_lctl` Command/Ctrl mapping. The compositor polls settings
once per second and applies layout, option, and repeat changes live; this path
is build-checked but not runtime-qualified. The current source is US;
`mozc-jp` is installed but inactive. F5 dictation is an active IBus workflow
and inserts committed Unicode into focused fields. The Rust compositor's
nested GTK Wayland field now passed a Mozc `mozc-jp` commit using the private
test profile described below; the native field and F5 workflow remain open.

The prototype now starts Smithay's rootless XWayland window manager, maps X11
windows into the shared desktop space, routes move/resize, maximize,
fullscreen, minimize, restore, and activation requests, sends keyboard input to
focused X11 clients, and bridges clipboard and PRIMARY selection ownership and
transfers. Native startup exports the selected `DISPLAY` through D-Bus and
systemd activation environments; the `--run` client waits for XWayland
readiness. An isolated Xvfb smoke mapped an X11 Zenity window, accepted
keyboard input, and exposed the focused window (`zenity`, workspace 0) through
the live window-list D-Bus method. Clipboard/PRIMARY transfers, session
activation, and broader X11 window behavior remain unqualified. The package
depends on the `xwayland` executable.

Panel reservations and managed maximize/tile layouts are tracked per output
connector. Maximized/fullscreen windows and popup constraints use the window's
current output, and removing a panel releases its work area. Multi-output
placement and panel behavior remain runtime-unqualified.

New toplevels center and cascade in the focused window's work area; when there
is no focused toplevel, placement follows the pointer's output, then falls back
to the primary output. This launch placement compiles in both renderer builds
but has not been runtime-qualified.

The configured primary connector is retained from monitor profiles and
`ApplyMonitorsConfig`; native hotplug preserves it while connected, then falls
back to the internal panel or first available output. Native hotplug also keeps
the positions of outputs that remain connected and places newly discovered
outputs beyond the current layout. Fallback placement and hotplug behavior
remain runtime-unqualified.

The pinned Gala 8.6.2 audit found 79 Vala files directly using `Meta.*` across
24,534 lines of Gala core source, with Clutter/Cogl/Mtk dependencies. That
explains why swapping out Mutter underneath Gala is not a drop-in operation.
It does not mean all those APIs need to be ported: replace only the behavior
required by the M-series/Pantheon session, in independently qualified slices.

## Current prototype

[`rust/pantheon-compositor`](../../rust/pantheon-compositor/README.md) has an
opt-in nested Smithay/Winit backend for development and an explicit native DRM
backend for M-series qualification. It supports the Pantheon shell protocol,
window basics, monitor configuration and lock bridge. The installed opt-in
session completed a first native display scanout on the M1 Pro, while full
shell, input and recovery behavior still need qualification. The staged session
remains separate from Gala and is not selected by default.

### Readiness decision (2026-10-19)

This branch is **not ready to replace Gala for daily Pantheon use**. On
2026-10-19, an isolated five-minute LightDM login completed and produced the
first native scanout on the M1 Pro: plane 0 used the compositor's AR30
framebuffer at 3024x1964. The owner confirmed the desktop was usable but slow
to appear. Wingpanel, Dock and wallpaper were missing in that first run.
The timed rollback returned to Gala and restored the background. This qualifies
native startup, internal-panel scanout and automatic rollback only; native
keyboard/pointer workflows, complete shell integration, external displays,
wallpaper after the new renderer, lock/unlock and compositor-failure recovery remain open.

In private Xvfb, the release binary launched a GTK Wayland Zenity field;
synthetic key events reached it, and IBus/Mozc committed `konnichiha` as
`こんにちは` using `mozc-jp` with Hiragana enabled in a private profile. This
qualifies one nested input-method-v2/text-input-v3 workflow, not host source
switching, F5 dictation or native input. XWayland also passed an isolated X11
Zenity window and keyboard smoke; clipboard/PRIMARY remain unqualified.
Installed Wingpanel binds the shell protocol and submits SHM panel buffers in
private Xvfb, but the Rust session did not launch it. Keep Gala selected while
the shell launcher is qualified and the new wallpaper renderer is tested on
native output.

The compositor now exposes Dock's `org.pantheon.gala.DesktopIntegration`
D-Bus interface. Window enumeration, app IDs, focus state, workspace listing,
activation and reorder, dynamic workspace creation, window movement, and
cross-workspace focus are implemented. An isolated Xvfb run with a temporary
Wayland client exercised workspace creation, movement, switching and focus.
Overview remains unsupported.
The nested stock Dock 8.3.3 smoke bound the panel protocol and attached buffers,
but also logged its known asynchronous workspace-initialization critical, so
Dock interaction is still not qualified end to end.

The ARM64 package from commit `83a663c` is saved at
`/home/sdolbec/Documents/Codex/2026-10-18/i-no/work/artifacts/pantheon-workspace-release/pantheon-rust-compositor_0.1.0+git83a663c_arm64.deb`
(SHA-256 `f34220be364417e92c4dab2aa8b9c3c29b5b1cfc9427c710318b42634684634a`).
Its package contents, dependencies and shared-library links were inspected;
it was installed with `gnome-session` and `gtklock` on 2026-10-19 and selected
once through LightDM. The compositor source is unchanged from `83a663c`; the
later commits in this branch update the DRM probe and documentation. The nested
runtime evidence below used the earlier package
from commit `619ca5c`, saved at
`/home/sdolbec/Documents/Codex/2026-10-18/i-no/work/artifacts/pantheon-workspace-release/pantheon-rust-compositor_0.1.0+git619ca5c_arm64.deb`
(SHA-256 `aee4c9af0d12c1a2bddbfd45dcd5a79e71afe8c8adc28d9ff46e7cf204d0ea13`).
The earlier package was not installed. Its release binary started in private Xvfb,
reported XWayland ready, and served a Zenity window through `GetWindows` with
`app-id=zenity`, focus true and the initial two-workspace count. This qualifies
the nested release path for continued development testing only. It does not
qualify visible rendering, native DRM scanout, the full Pantheon shell or a
login session. A second isolated run started Wingpanel against the same release
binary: it sent `get_panel`, top anchor and `never` hide-mode requests, and
allocated SHM buffers without a keyboard assertion. The compositor's
`org.gnome.Mutter.DisplayConfig.GetCurrentState` returned the nested 1280×800
output. Both runs used private D-Bus/Xvfb and a private GSettings fixture; the
active Wingpanel session was not restarted. These checks do not qualify native
DRM scanout, physical keyboard input, the Dock, or a complete login session.

The next gate is to nested-qualify the staged Wingpanel and Dock startup against
`/etc/xdg/io.elementary.desktop.wm.shell`, and qualify the new wallpaper renderer
on native output. Then qualify shell rendering, Dock launcher/window switching,
GTK/Qt clients and real F5 dictation. Package those changes before another
native login. Keep the measured startup, resource, latency, power and
crash/recovery comparison against Gala open; one successful login does not
establish the migration as faster, lighter or more reliable.

The staged systemd service now retries an unexpected compositor failure with
a two-second delay, capped at three starts per minute. After that limit, its
`OnFailure` action requests the GNOME session shutdown target rather than
looping indefinitely. Native DRM event-source and frame-completion errors now
stop the compositor with a failure status; three consecutive render failures
do the same. This connects unrecoverable display failures to the service's
restart path instead of leaving a running but unusable session. The restart,
shutdown and hardware-failure paths have not been exercised in an isolated
login.

`build-deb.sh` builds an arm64 release binary with `native-drm` and packages it
with the separate experimental session files. It derives shared-library
dependencies and requires `gnome-session` and `gtklock`. Build it locally with
`OUTDIR=/path/to/output mseries/pantheon-rust-compositor/build-deb.sh`. The
current package above includes the XWayland runtime dependency and is for
isolated qualification; the build script does not install it. The nested IBus
path is qualified for one GTK/Mozc configuration; native IBus behavior and any
display takeover remain unqualified.

## Dock HDMI boundary

The WD22TB4 HDMI goal remains in
[`../fairydust/usb4/PRIMARY-GOAL.md`](../fairydust/usb4/PRIMARY-GOAL.md). The
G3 gate is DCP/kernel link training; a compositor cannot fix an output the
kernel has not exposed. Keep compositor modeset/hotplug qualification separate.

No change here qualifies an M-series session or hardware. Gala remains the
production session and rollback until the scoped experience passes on-device
acceptance.
