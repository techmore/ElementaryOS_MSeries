# GUI stack comparison and development status

This page shows where the compositor sits in the desktop stack, how the
M-series prototype differs from the current Pantheon stack, and what the
native development session has proved so far. It is a working architecture
map, not a claim of feature parity.

## Existing elementary OS / Pantheon on M-series

Gala supplies Pantheon's window manager and compositor integration on top of
libmutter. Mutter provides the Wayland display-server work and delegates
device-level display support to Linux KMS/input drivers. Applications and
shell surfaces are Wayland clients; X11 applications use XWayland. On this
M1 Pro, rendering and display scanout use different DRM devices.

```mermaid
flowchart TD
  Apps[GTK / Qt / other Wayland apps]
  XApps[X11 apps]
  Shell[Pantheon shell clients\nWingpanel + Dock + background]
  Xwayland[XWayland]
  Gala[Gala + libmutter\nPantheon window manager, shell integration\n+ Wayland compositor]
  KMS[Linux DRM / KMS + libinput]
  Asahi[Asahi GPU\ncard1 / renderD128\nrendering]
  Apple[Apple display controller\ncard2 / KMS]
  DCP[DCP firmware / kernel driver]
  Panel[Built-in display / external display path]

  Apps -->|Wayland| Gala
  XApps --> Xwayland --> Gala
  Shell -->|Wayland + Pantheon shell protocols| Gala
  Gala -->|input + display requests| KMS
  Gala -->|render buffers / DMA-BUF| Asahi
  Asahi -->|imported scanout buffer| Apple
  KMS --> Apple --> DCP --> Panel
```

The diagram is simplified: Gala is built against libmutter and uses its
compositor APIs, so replacing Mutter under Gala is not a binary-compatible
swap. Our Rust prototype keeps the existing shell applications as clients and
implements the small set of compositor and shell-facing contracts it needs.
The M-series graphics path is also layered: the compositor cannot replace
missing kernel or firmware display support. The Asahi M1 feature matrix lists
both GPU and DCP support in `linux-asahi`.

## Omarchy running on Asahi

Omarchy is an Arch-based desktop setup built around Hyprland and Quickshell.
Its manual describes running it on Asahi Alarm on M1/M2 as a community
workaround that takes effort; this is a different shell and workflow from
Pantheon, not a Pantheon compositor port.

```mermaid
flowchart TD
  Apps[Wayland apps]
  XApps[X11 apps]
  Shell[Omarchy shell / widgets\nQuickshell]
  Xwayland[XWayland]
  Hyprland[Hyprland\nWayland compositor + tiling WM]
  Arch[Arch userspace\nAsahi Alarm base]
  Kernel[Asahi Linux kernel\nDRM / input drivers]
  GPU[Asahi GPU]
  DCP[DCP firmware / kernel driver]
  Displays[Built-in / supported external displays]

  Apps -->|Wayland| Hyprland
  XApps --> Xwayland --> Hyprland
  Shell -->|Wayland clients| Hyprland
  Hyprland --> Arch --> Kernel
  Kernel --> GPU
  Kernel --> DCP --> Displays
```

## Proposed minimal viable Pantheon compositor for M-series

Keep the Pantheon apps, shell clients, and settings services. Replace the
Gala/libmutter compositor layer with a Rust/Smithay process that speaks
Wayland, implements the Pantheon shell protocol and required GNOME session
bridges, and uses the existing Asahi rendering and Apple KMS path. Session
management starts the compositor before Wingpanel and Dock. Wallpaper,
lock-screen UI, accessibility, sharing, and other services remain separate
desktop components; the compositor must provide the protocols and hooks their
required workflows need.

```mermaid
flowchart TD
  Apps[Existing Pantheon / GTK / Qt apps]
  XApps[X11 apps]
  Shell[Existing Pantheon shell clients\nWingpanel + Dock]
  Settings[Existing desktop background settings\nwallpaper URI + picture options]
  Services[GNOME / Pantheon session services\nsettings, IBus, accessibility, sharing, lock UI]
  Xwayland[XWayland]
  Session[GNOME session + systemd user units]
  Rust[Minimal viable Rust compositor\nSmithay + Wayland + Pantheon shell / Mutter-compatible bridges]
  Render[Asahi GPU renderer\ncard1 / renderD128]
  Scanout[Apple DRM / KMS\ncard2]
  DCP[DCP firmware / kernel driver]
  Displays[Built-in / external displays]

  Apps -->|Wayland| Rust
  XApps --> Xwayland --> Rust
  Shell -->|Wayland + Pantheon shell protocol| Rust
  Settings -->|GSettings read at startup| Rust
  Services <-->|required compositor bridges| Rust
  Session -->|start compositor, then shell clients| Rust
  Session --> Shell
  Rust -->|render buffers / DMA-BUF| Render
  Render -->|imported scanout buffer| Scanout
  Rust -->|modesetting / input via kernel| Scanout
  Scanout --> DCP --> Displays
```

**Current implementation detail:** the session file starts the compositor;
new user units are staged to start Wingpanel and Dock after it. `After=` orders
process startup but does not yet wait for the panel to map or prove the
`wait-for-n-panels=1` shell-launcher contract. The units are included in a local
ARM64 package build but are not installed or runtime-qualified. The compositor
now loads the configured local wallpaper at startup and renders it behind
windows, honoring the `zoom` crop mode; live wallpaper changes still require a
session restart. Refreshed package `0.1.0+gitb486d56` includes the wallpaper
renderer and shell units; it has not been installed or qualified on native
output. In the nested Winit backend, the default transform is set to compensate
for the framebuffer orientation observed under Xvfb; this produced an upright
wallpaper and top Wingpanel in a fresh nested run. It does not alter the native
DRM output transform.

**Development shell smoke:** the current release build rendered installed
Wingpanel 8.0.4 across the top and the stock `/usr/bin/io.elementary.dock`
along the bottom, over the wallpaper, in an isolated Xvfb session. Its Wayland
trace shows the Dock binding the Pantheon panel protocol, requesting the bottom
anchor and submitting shared-memory buffers. The normal local Dock command is
a wrapper; its existing user-disabled marker makes it run `sleep infinity`, so
the earlier “Dock process alive” check was a false positive. The marker remains
untouched, and the visual test launched the stock executable directly only
inside the private session. Hide/reveal also passed in private profiles using
both `overlapping-focused` and `overlapping-window` (the user's saved value): a
maximized GTK window hid the Dock, bottom-edge pointer motion revealed it over
the window, and closing the window restored it. The user's live configuration
was not modified. Native-session appearance remains unqualified. No Gala
session was replaced.

## What is complete and what has been tested

| Area | Evidence | State |
| --- | --- | --- |
| Rust compositor and opt-in session package | Smithay prototype; nested Winit and native DRM backends; local ARM64 package `0.1.0+gitb486d56` includes wallpaper and staged shell startup units; compositor remains separate from the default Gala session | Builds; not installed; shell service runtime not yet qualified |
| Native display path | Experimental LightDM login reached the M1 Pro internal display; kernel DRM state showed compositor-owned AR30 framebuffer at 3024×1964 | Native internal-panel scanout passed once |
| Session recovery | Five-minute LightDM rollback returned to Gala; Wingpanel and background came back | Automatic rollback passed once |
| XWayland | Private Xvfb Zenity window mapped and accepted synthetic keyboard input; exposed through window-list D-Bus | Isolated smoke passed |
| Nested text input | Private GTK Wayland field accepted an IBus/Mozc Japanese commit | Isolated smoke passed; native input remains unqualified |
| Pantheon panel protocol | Wingpanel connected in private nested Wayland, requested a top panel, attached shared-memory buffers and rendered upright after the nested Winit transform correction | Nested visual smoke passed; panel absent from native session |
| Pantheon shell clients | Current release rendered Wingpanel at top and stock Dock at bottom in isolated Xvfb. Hide/reveal passed with both private `overlapping-focused` and `overlapping-window` profiles; the latter matches the host's saved value | Nested visual and hide/reveal smoke passed; native appearance remains open. The local Dock wrapper remains intentionally disabled by the existing user marker |
| Desktop wallpaper | Loaded the configured 5000×2813 elementary wallpaper and captured it behind a GTK Zenity window in isolated Xvfb; fresh nested shell run showed wallpaper upright | Nested visual smoke passed; native output and live setting changes remain open |
| Native full desktop | In the first Rust login, the owner observed slow startup, no top panel, no bottom dock, and no colored background. After returning to the regular desktop, a background was visible, but the active session was uncertain | Incomplete; wallpaper rendering landed afterward and has not been qualified on native output |
| Native keyboard, pointer, external display, lock/unlock, sharing, accessibility, crash recovery | No end-to-end qualification in the native session | Open |
| Performance, power, reliability | No matched Gala/Rust measurements or crash-free soak yet | Open; do not claim faster or more reliable yet |

The current login observation is useful development evidence, not a daily-use
readiness result. Continue testing in the isolated experimental session while
Gala remains the working fallback. The next development gate is to exercise
basic shell interaction and startup timing in the nested session, then qualify
startup and the wallpaper path on native output before another native login.
The existing user-disabled Dock marker should remain in effect
unless the user explicitly chooses to re-enable Dock in the desktop session.
After that, measure the same startup, idle and representative workloads under
Gala and Rust, and record crashes and recovery behavior.

## References

- [Gala upstream README](https://github.com/elementary/gala/blob/main/README.md)
- [Mutter upstream README](https://github.com/GNOME/mutter/blob/main/README.md)
- [Omarchy manual](https://omarchy.org/manual/)
- [Omarchy on Asahi manual](https://omarchy.org/manual/omarchy-on/)
- [Asahi Linux M1 feature support](https://github.com/AsahiLinux/docs/blob/main/docs/platform/feature-support/m1.md)
