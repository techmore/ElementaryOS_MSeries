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

Panel reservations and managed maximize/tile layouts are tracked per output
connector. Maximized/fullscreen windows and popup constraints use the window's
current output, and removing a panel releases its work area. Multi-output
placement and panel behavior remain runtime-unqualified.

New toplevels center and cascade in the focused window's work area; when there
is no focused toplevel, placement follows the pointer's output, then falls back
to the primary output. This launch placement compiles in both renderer builds
but has not been runtime-qualified.

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

## Dock HDMI boundary

The WD22TB4 HDMI goal remains in
[`../fairydust/usb4/PRIMARY-GOAL.md`](../fairydust/usb4/PRIMARY-GOAL.md). The
G3 gate is DCP/kernel link training; a compositor cannot fix an output the
kernel has not exposed. Keep compositor modeset/hotplug qualification separate.

No change here qualifies an M-series session or hardware. Gala remains the
production session and rollback until the scoped experience passes on-device
acceptance.
