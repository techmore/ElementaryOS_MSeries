# Rust Mutter for Pantheon

This branch starts the work toward a Rust compositor for the elementary OS
Pantheon stack. The target is a session-level replacement for Gala/Mutter that
can be enabled and rolled back as one package. It is not a dock-firmware fix.

## Current boundary

Gala is both Pantheon's window manager and the Wayland display server. In the
current Gala 8.6.2 source it is compiled against `libmutter-14` through
`libmutter-18`, and directly uses Mutter's `Meta` types, Clutter actors, Cogl,
and Mtk geometry. Its Wayland session unit starts `gala` as the display server
and treats a failure as a session failure. Replacing `gala` with an unrelated
compositor would therefore break the session even if ordinary Wayland clients
could still render.

The first milestone is a Rust compositor that can run nested and prove its
Wayland client, rendering, focus, input, and output contracts without taking
over the user's desktop. After that, move Pantheon window-management and shell
behavior behind Wayland protocols or a small, versioned Pantheon control
protocol. Do not promise a drop-in replacement until Gala's Mutter/Clutter
dependencies have been removed or an explicitly maintained compatibility
layer covers every API Gala uses.

## Delivery gates

1. **Nested compositor:** Rust process starts as a nested Wayland client, serves
   a second Wayland display, presents a client, and exits without changing
   the host session. The first prototype now lives in
   [`rust/pantheon-compositor`](../../rust/pantheon-compositor/README.md). It is
   based on Smithay's smallvil at pinned revision
   `023b78b1c5a05ca512767cacc07efca55fae8be4`. It has not been built or
   hardware-qualified yet.
2. **Pantheon shell contract:** enumerate Gala and Pantheon consumers, then
   implement window activation, close/minimize/maximize, workspaces, placement,
   panel/dock reservations, shell hotkeys, lock-screen handoff, and session
   lifecycle. Define only the compatibility protocols actually required by
   this stack.
3. **Desktop hardware and input:** DRM/KMS outputs, multi-monitor changes,
   libinput, keyboard layouts, accessibility, IBus/input-method protocols,
   screencast/remote-desktop portals, clipboard, drag-and-drop, and Xwayland.
   Exercise these on supported M-series hardware before changing the default.
4. **Parallel session qualification:** start the new compositor from an
   opt-in session entry with the existing Gala session intact as rollback.
   Qualify login/logout, apps, panel, dock, settings, lock/unlock, suspend/resume,
   hotplug, screen sharing, accessibility, input methods, and crash recovery.
5. **Swap-in:** only after the compatibility matrix is green, package a
   reversible session change and collect owner acceptance on hardware. Keep
   Gala available until the new session has passed that acceptance.

## Hardware blocker separation

The WD22TB4 HDMI goal is tracked in
[`../fairydust/usb4/PRIMARY-GOAL.md`](../fairydust/usb4/PRIMARY-GOAL.md). Its
current G3 gate is DCP link training. A Rust compositor may eventually need to
handle output hotplug and modesets correctly, but it cannot make firmware train
a link that the kernel/DCP path has not trained. Track compositor output
qualification separately from G3 through G5.

## Source audit

The initial interface audit used the repository's pinned Gala source at
`elementary/gala` commit `f0791434` (Gala 8.6.2). Its build requires Mutter 46
through 50 (`libmutter-14` through `libmutter-18`) and corresponding Mutter
Clutter/Cogl/Mtk libraries. Gala's `WindowManager` implementation subclasses
`Meta.Plugin`, manages `Meta.Window`/`Meta.Workspace`, and builds its shell UI
from Clutter actors. Its Wayland desktop entry starts `gala --wayland
--display-server`; the systemd user unit also owns display-server startup and
session-failure handling.

This branch has not changed the active desktop, kernel, bootloader, or audio
stack. Nothing here claims a running or hardware-qualified replacement yet.
