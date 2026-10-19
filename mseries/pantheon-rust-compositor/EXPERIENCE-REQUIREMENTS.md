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
| Input methods and dictation | Keep IBus composition and focus-bound F5 Unicode output working in focused Wayland fields; retain the configured `mozc-jp` source | [F5 app qualification](../dictation/F5-ENGLISH-ACCEPTANCE.md) records the active IBus output workflow; current sources include US XKB and IBus `mozc-jp` | Advertise text-input-v3 and a trusted input-method-v2 global, track keyboard/text focus and input-method popups; qualify actual IBus commits in installed GTK/Qt apps |
| Existing X11 clients | Launch rootless XWayland clients, keep keyboard focus, clipboard and PRIMARY selection exchange usable, and export the X display to session-activated apps | Current Pantheon session exposes `ibus-x11`, `ChatGPT`, and `mutter-x11-frames` as Xwayland clients | XWayland startup/window management and session `DISPLAY` propagation are implemented in the Rust prototype; keyboard, clipboard and PRIMARY selection paths compile but still need nested and on-device runtime qualification |
| M-series render-to-display bridge | Render ordinary client surfaces on the Asahi GPU and present them through the Apple display controller | Read-only M1 Pro inventory: Asahi `/dev/dri/card1` exposes `renderD128` but no KMS resources; Apple `/dev/dri/card2` owns the internal `eDP-1` output and has no EGL device | Make rendered buffers usable by Apple KMS, adding a copy/bridge path if direct import is insufficient; validate framebuffer creation and scanout, and handle presentation failure without leaving a live but unusable session |
| Window arrangement | Native half snapping and the four quarter positions; preserve work-area geometry as the dock appears or hides; move windows between displays | [`window-snapping`](../window-snapping/README.md), [`display-space`](../display-space/README.md) | Basic tiling and monitor movement only where this behavior belongs to the compositor; keep shortcut policy configurable and test window geometry against the current work area |
| Login-critical integration | Lock/unlock, logout, session restart and core settings must work before the session can be a swap-in | Gala owns the current display-server unit and failure path; lock screen/session integration is part of the current desktop | Implement the smallest protocol and service integration required by the installed Pantheon apps and session. Validate real lock/unlock and recovery before making it selectable by default |
| Desktop background | Show the configured elementary wallpaper behind windows on every output and reflect wallpaper/crop-setting changes in-session | Current `org.gnome.desktop.background` setting points to `elementaryos-default`; Gala renders the wallpaper as part of its compositor scene | Prototype loads local PNG/JPEG/WebP and polls the shared URI and crop setting every two seconds, reloading only on changes. Private dconf/Xvfb reload smoke passed; native output behavior still needs qualification |

## Conditional work, driven by an observed need

Add these only when an M-series workflow depends on them, and keep each as a
separate acceptance item: accessibility protocols/actions used by the owner's
setup; screencast/remote-desktop portal support for screen sharing;
touch/gestures if the selected hardware and workflow use them. The measured M1
Pro topology already requires cross-device buffer sharing for native display
output; additional GPU topologies remain conditional.
They are important capabilities in a general-purpose desktop, but their
presence in Mutter is not by itself a reason to reproduce them in the first
cut.

On the current host, the configured sources are US XKB and IBus `mozc-jp`, with
US selected. The nested release binary has now passed a GTK Wayland field
commit using `mozc-jp`: romaji `konnichiha` produced `こんにちは`. The test
used a private Mozc profile with `active_on_launch: True` because the documented
default is direct Latin input; it did not change host settings. This qualifies
the compositor's nested IBus/text-input path, not host source switching,
physical keyboard input or the F5 dictation workflow. See the
[Mozc IBus configuration](https://github.com/google/mozc/blob/master/docs/configurations.md#activate-mozc-on-launch)
for the input-mode setting.

The 2026-10-19 user-settings snapshot has the screen reader, screen magnifier,
and accessibility keyboard features disabled. Toolkit accessibility is enabled
for app-field metadata used by the F5 workflow; that app-side AT-SPI use does
not itself require compositor accessibility protocols. GNOME Remote Desktop
RDP and VNC are both disabled, so remote screen sharing remains conditional.

Keep notification UI, app launchers, panel/dock rendering, settings surfaces,
and other shell UI in their existing Pantheon components unless a documented
requirement shows they cannot work through the compositor contract. Gala
currently owns wallpaper rendering in its compositor scene, so the Rust
prototype needs its own background renderer while the existing settings UI
continues to select the image.

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

## Reliability and performance gates

The migration target includes a measurable quality improvement: faster startup
and interaction, lower steady-state CPU/memory/GPU and power use, and fewer
crashes than Gala on the same M-series hardware. Do not claim those gains from
feature coverage or a single successful login. Capture a Gala baseline and a
Rust result under the same display mode and workloads: cold login-to-usable
time; idle and representative-workload CPU, resident memory, GPU activity and
battery/power draw; frame/input latency where measurable; and crash-free
session duration plus restart/recovery outcomes. Keep dated results and the
workload/environment with each run. Set numerical pass thresholds from the
baseline before calling the migration better or ready for daily use. Track
startup and runtime faults with journal excerpts and crash signatures so
regressions can be tied to a specific branch revision.

The nested prototype serves the Pantheon shell protocol v2, places a panel from
its anchor/size/offset, and honors hide modes by tracking maximized/focused or
overlapping windows. Pointer motion at the output edge reveals hidden panels;
work-area reservations are released while hidden and restored while visible,
with managed windows reconfigured on transitions. Hiding currently moves the
panel immediately without an animation. The active host Dock setting is
`overlapping-window`. In an isolated Xvfb session, the stock Dock rendered at
the bottom. Hide/reveal passed in two private profiles: `overlapping-focused`
and `overlapping-window` (matching the host's saved value). With a maximized
GTK window, the Dock hid; bottom-edge pointer motion revealed it over that
window; closing the window restored it. This validates the behavior in nested
Winit, not on native DRM. The existing local wrapper is held at
`sleep infinity` by the user's disabled marker; each test invoked
`/usr/bin/io.elementary.dock` directly without changing that marker. The
compositor updates already-maximized windows when work areas change.
The last local `cargo check`
and `cargo build` pass. Its protocol probe completed under Xvfb over a nested
Wayland socket. Installed Wingpanel 8.0.4 also connected in an isolated nested
Wayland session and rendered SHM buffers. The prototype serves the
`org.gnome.Mutter.DisplayConfig.GetCurrentState` query Wingpanel uses, and
Wingpanel completes that call. Native `GetCurrentState` lists connector modes
reported by DRM and marks current/preferred modes. `ApplyMonitorsConfig` now
validates serials, connector assignments, mode IDs, scale and transform. It
supports disabling and re-enabling native outputs: disabled connectors remain
in the monitor inventory without a logical placement, the KMS output is
released/recreated, and method 2 persists enabled state alongside each
monitor's mode and layout. Existing seven-field profiles default to enabled.
The native backend keeps existing outputs live while it stages the requested
set. It can reassign a CRTC to a new connector through a DRM surface connector
and mode commit, including on a single-CRTC device, when the encoder supports
that route. It retires outputs outside the requested set only after all
requested outputs are active. If connector activation or modesetting fails, it
attempts to restore the previous enabled set, modes and layout. This path
builds but still needs failure-injection and hardware qualification.
Native mode changes use Smithay's shared output manager with rollback;
temporary layout, scale and transform changes update Wayland outputs. Mirroring,
unsupported properties and nested Winit monitor-set changes remain rejected.
Both default and native DRM builds compile; disable/re-enable, reconnect and
mode-rollback behavior remain unqualified at runtime on the active M-series
display. The compositor advertises
`wp_fractional_scale_v1` and `wp_viewporter`, setting each window surface's
preferred scale from its first mapped output. Runtime checks for moving a
surface between differently scaled outputs remain open. The compositor now
serves `xdg-activation-v1`, requiring a recent token associated with this seat
and using it to raise/focus mapped windows outside a locked session. App-launch
activation remains runtime-unverified. `xdg_toplevel.set_minimized` now hides and
retains a window, and a later valid activation request restores it. Minimize /
restore behavior remains runtime-unverified. It also
implements the `org.gnome.Shell`
accelerator registration and activation path: pressing the registered
`Super+N` chord emits `AcceleratorActivated` in the nested run. Wingpanel and
Dock have nested visual smoke coverage, including Dock hide/reveal in the
private `overlapping-focused` mode. The host's configured hide mode, native
Dock behavior and physical media-key activation remain unqualified. The first
M1 Pro scanout passed in an isolated native login, but one scanout is not full
session or hardware qualification.

The compositor now implements Smithay's `ext-session-lock-v1` protocol and the
observed `org.gnome.ScreenSaver` action interface. Lock requests suppress
application rendering, clear active grabs, route input to the lock surface,
and confirm the lock only after each mapped output presents a cleared frame.
`Lock` starts a configured locker (default `gtklock`). The source tree does not
install the locker; the experimental ARM64 package includes the Ubuntu
`gtklock` dependency, but lock/unlock has not been exercised. Authentication,
runtime input/visual checks, full native session behavior and crash recovery
remain open acceptance items.
