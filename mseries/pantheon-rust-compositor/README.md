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
and inserts committed Unicode into focused fields; the Rust compositor now
advertises Smithay text-input-v3/input-method-v2 for that path, but still needs
qualification with the running IBus daemon and a native Wayland field.

The prototype now starts Smithay's rootless XWayland window manager, maps X11
windows into the shared desktop space, routes move/resize, maximize,
fullscreen, minimize, restore, and activation requests, sends keyboard input to
focused X11 clients, and bridges clipboard and PRIMARY selection ownership and
transfers. Native startup exports the selected `DISPLAY` through D-Bus and
systemd activation environments; the `--run` client waits for XWayland
readiness. XWayland keyboard, clipboard, PRIMARY selection, session activation,
and X11 window behavior compile but still need runtime qualification. The
package depends on the `xwayland` executable.

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
backend for M-series qualification. It supports the Pantheon shell contract,
window basics, monitor configuration and lock bridge, but native display,
session, input and recovery behavior still need on-device qualification. The
staged login-session files are separate from the active Gala session and are
not installed or selected by default.

The staged systemd service now retries an unexpected compositor failure with
a two-second delay, capped at three starts per minute. After that limit, its
`OnFailure` action requests the GNOME session shutdown target rather than
looping indefinitely. This is configuration only; a crash/restart has not been
exercised in an isolated login.

`build-deb.sh` builds an arm64 release binary with `native-drm` and packages it
with the separate experimental session files. It derives shared-library
dependencies and requires `gnome-session` and `gtklock`. Build it locally with
`OUTDIR=/path/to/output mseries/pantheon-rust-compositor/build-deb.sh`. The
The locally built arm64 package from commit `7b1b46b` is saved at
`/home/sdolbec/Documents/Codex/2026-10-18/i-no/work/artifacts/pantheon-ibus-release/pantheon-rust-compositor_0.1.0+git7b1b46b_arm64.deb`
(SHA-256 `031b409e6c367487bc97adba375a865c79cb691bd48ea8f8b7e9b4255d3dd885`).
It includes the XWayland runtime dependency and is for isolated qualification;
the build script does not install it. The package contents and dependency
metadata were inspected after building. The IBus Wayland path has not yet been
runtime-qualified, and no display takeover was run.

## Dock HDMI boundary

The WD22TB4 HDMI goal remains in
[`../fairydust/usb4/PRIMARY-GOAL.md`](../fairydust/usb4/PRIMARY-GOAL.md). The
G3 gate is DCP/kernel link training; a compositor cannot fix an output the
kernel has not exposed. Keep compositor modeset/hotplug qualification separate.

No change here qualifies an M-series session or hardware. Gala remains the
production session and rollback until the scoped experience passes on-device
acceptance.
