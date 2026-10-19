# Mutter-minimal viable Rust: M-series experience requirements

This is the working name for a **minimal viable Rust compositor for elementaryOS
on M-series Macs**. Mutter is a source of proven behavior and implementation
ideas. The deliverable is a Pantheon session that supports the workflows we
actually use, not a Rust port of Mutter or a feature-for-feature clone of Gala.

Requirements below come from the M-series handoff and implemented desktop work
in this repository. Priority means needed for a useful first Pantheon session;
it does not imply that the current prototype supports it.

## Experience-derived scope

| Priority | User-visible need | Evidence in this repository | Compositor work |
| --- | --- | --- | --- |
| First usable session | Launch and stop the session predictably; run ordinary Wayland apps; focus, raise, move, resize, maximize, minimize, close and fullscreen windows; recover from a compositor exit | Current Gala session unit and window-management source; app use across the M-series handoff | Own the Wayland display, seat, xdg-shell lifecycle, visible initial placement and focus, stacking, basic window state, startup readiness and orderly failure/restart behavior |
| M-series panel and dock | Preserve panel and dock placement, keep windows out of visible dock space, return that space when the dock hides, support full-height/notch layout and monitor/scale changes | [`display-space`](../display-space/README.md), including 3024×1964 full-height panel, dock work area and hide/reveal behavior | Implement the existing Pantheon panel/dock shell protocol (or a small maintained successor) and usable-area/work-area updates. Leave panel rendering and dock UI in their existing apps |
| Display and input | Use the built-in panel at the configured scale; survive internal display changes and connected-display hotplug when the kernel exposes a usable output; keyboard, pointer, shortcuts and Command/Ctrl mapping | [`display-profiles`](../display-profiles/README.md), [`window-snapping`](../window-snapping/README.md), handoff display/input fixes | Output enumeration, mode/layout application and rollback; keyboard/pointer events; map absolute pointer coordinates to the complete logical desktop; xkb layouts and shortcut routing. Keep dock video link training in kernel/DCP scope |
| M-series render-to-display bridge | Render ordinary client surfaces on the Asahi GPU and present them through the Apple display controller | Read-only M1 Pro inventory: Asahi `/dev/dri/card1` exposes `renderD128` but no KMS resources; Apple `/dev/dri/card2` owns connected `eDP-1` and `DP-2` and has no EGL device | For this measured topology, import/share rendered buffers across the two DRM devices, allocate scanout buffers on the display controller, and handle import/presentation failure without losing the session |
| Window arrangement | Native half snapping and the four quarter positions; preserve work-area geometry as the dock appears or hides; move windows between displays | [`window-snapping`](../window-snapping/README.md), [`display-space`](../display-space/README.md) | Basic tiling and monitor movement only where this behavior belongs to the compositor; keep shortcut policy configurable and test window geometry against the current work area |
| Login-critical integration | Lock/unlock, logout, session restart and core settings must work before the session can be a swap-in | Gala owns the current display-server unit and failure path; lock screen/session integration is part of the current desktop | Implement the smallest protocol and service integration required by the installed Pantheon apps and session. Validate real lock/unlock and recovery before making it selectable by default |

## Conditional work, driven by an observed need

Add these only when an M-series workflow depends on them, and keep each as a
separate acceptance item: Xwayland for a required X11 app; IBus/input-method
support for the installed input method; accessibility protocols/actions used by
the owner's setup; screencast/remote-desktop portal support for screen sharing;
touch/gestures if the selected hardware and workflow use them. The measured M1
Pro topology already requires cross-device buffer sharing for native display
output; additional GPU topologies remain conditional.
They are important capabilities in a general-purpose desktop, but their
presence in Mutter is not by itself a reason to reproduce them in the first
cut.

Keep notification UI, app launchers, panel/dock rendering, settings surfaces,
wallpaper and other shell UI in their existing Pantheon components unless a
documented requirement shows they cannot work through the compositor contract.

## Explicitly separate workstreams

- **WD22TB4 HDMI picture:** the tracked G3 blocker is Apple DCP/kernel link
  training ([primary goal](../fairydust/usb4/PRIMARY-GOAL.md)). The compositor
  cannot create a display output the kernel does not expose. Qualify hotplug and
  modesetting only after the output exists in DRM.
- **Mutter parity:** there is no goal to implement every Mutter API, effect,
  hardware path or private Gala integration. Gala's broad Meta/Clutter usage is
  a migration constraint; it is not the product requirements list.
- **Other hardware:** don't add generic multi-GPU, virtual-display or unusual
  cursor paths until a supported M-series setup or user-visible workflow needs
  them.

## Upstream feature radar

Use Mutter releases and merge requests as a source of ideas and regression
knowledge. For example, [Mutter !5205](https://gitlab.gnome.org/GNOME/mutter/-/merge_requests/5205)
adds a Night Light color-transform path for hardware such as Apple DCP that has
CTM but no gamma LUT. The current M-series handoff reports that this machine's
exposed path did not advertise CTM, so this is a conditional candidate rather
than a compositor v1 requirement. Cursor-overlay and secondary-GPU damage fixes
are similarly conditional on those output paths being used. Recheck upstream
before adopting a fix; do not treat every upstream change as a porting task.

The initial public tag check found Mutter 51.1 as the newest stable tag and no
52 beta tag. This is a dated observation, not a promise about current upstream;
check the [Mutter tag list](https://gitlab.gnome.org/GNOME/mutter/-/tags) before
planning against a release.

## Build-up plan

1. Keep the Smithay prototype nested and opt-in. Turn it into a clean minimal
   Wayland session with basic window behavior and usable diagnostics.
2. Inventory the installed Pantheon clients' actual protocols and session
   expectations. Add the narrow panel/dock protocol, work areas, outputs and
   input behaviors required by the evidence above.
3. Run the session beside the existing Gala session as a reversible opt-in.
   Qualify login, ordinary apps, panel/dock, monitor changes, snapping,
   lock/unlock and crash recovery on the M1 Pro.
4. Add conditional capabilities only against named apps/workflows and explicit
   acceptance checks. Keep Gala available as rollback until owner acceptance.

The nested prototype serves the Pantheon shell protocol v2, places a panel from
its anchor/size/offset, reserves exclusive panel geometry, and updates already
maximized windows when that work area changes. The last local `cargo check`
and `cargo build` pass. Its protocol probe completed under Xvfb over a nested
Wayland socket. Installed Wingpanel 8.0.4 also connected in an isolated nested
Wayland session and rendered SHM buffers. The prototype serves the
`org.gnome.Mutter.DisplayConfig.GetCurrentState` query Wingpanel uses, and
Wingpanel completes that call. Native `GetCurrentState` lists connector modes
reported by DRM and marks current/preferred modes. `ApplyMonitorsConfig` now
validates serials, output assignments, mode IDs, scale and transform. Native
mode changes use Smithay's shared output manager with rollback; temporary
layout, scale and transform changes update Wayland outputs. Method 2 saves a
per-user profile and native startup restores saved modes and layout. Disabling
outputs, mirroring, unsupported properties and nested Winit mode changes are
rejected. Both default and native DRM builds compile; runtime changes on the
active M-series display remain unqualified. The compositor advertises
`wp_fractional_scale_v1` and `wp_viewporter`, setting each window surface's
preferred scale from its first mapped output. Runtime checks for moving a
surface between differently scaled outputs remain open. The compositor now
serves `xdg-activation-v1`, requiring a recent token associated with this seat
and using it to raise/focus mapped windows outside a locked session. App-launch
activation remains runtime-unverified. It also
implements the `org.gnome.Shell`
accelerator registration and activation path: pressing the registered
`Super+N` chord emits `AcceleratorActivated` in the nested run. Dock integration,
physical media-key activation and M-series hardware remain unqualified; this
is not full session or hardware qualification.

The compositor now implements Smithay's `ext-session-lock-v1` protocol and the
observed `org.gnome.ScreenSaver` action interface. Lock requests suppress
application rendering, clear active grabs, route input to the lock surface,
and confirm the lock only after each mapped output presents a cleared frame.
`Lock` starts a configured locker (default `gtklock`), but that package is not
installed by this source tree and no locker has been connected. Authentication,
runtime input/visual checks, native login and crash recovery remain open
acceptance items.
