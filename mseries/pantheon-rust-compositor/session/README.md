# Experimental Pantheon Rust Wayland session

This tree contains an opt-in GNOME session definition for the Rust compositor.
It uses the installed `gnome-session@SESSION.target` contract: GNOME hides the
required compositor component from its own launcher, and a session target
drop-in requires the dedicated compositor target. That target starts a
`Type=notify` service and therefore waits for the compositor's `READY=1`
notification before session initialization continues. This follows the
[GNOME session systemd documentation](https://gnome.pages.gitlab.gnome.org/gnome-session/re01.html)
and the matching Pantheon units installed on this machine.

The LightDM entry uses `pantheon-rust-session`, which waits for any queued stop
job on `gnome-session-pre.target` to finish before starting GNOME. This avoids
the systemd transaction conflict observed when a new login overlapped teardown
of the prior session. The wait is bounded at 30 seconds and fails the login
entry with a diagnostic if teardown remains stuck. This handoff fix is staged
but still needs native login qualification.

The session is named **Pantheon (Rust compositor, experimental)** and uses the
separate `pantheon-rust-wayland` session ID. The existing
`pantheon-wayland` entry and Gala units are not modified. The service binds
`wayland-0`, publishes that value to the systemd user manager after readiness,
and clears the display variables and fixed socket when it stops.
`PANTHEON_WAYLAND_DISPLAY` selects the explicit socket; without that variable
the nested development backend continues to allocate an automatic socket, and
the native backend can also use automatic allocation for manual development
launches. After readiness, `dbus-update-activation-environment --systemd`
publishes `WAYLAND_DISPLAY` to both D-Bus and the user manager, then the service
queues `xdg-desktop-portal.service` asynchronously. This addresses a native
handoff where early portal activation was skipped while the display variable
was unset. Package `0.1.0+git02447cb` passed one native ordering qualification:
the portal service and its configured providers started within about one second
of compositor readiness, without the previous 120-second activation timeout.
The GNOME portal backend still warns that Mutter's private `ServiceChannel` is
unavailable; dialogs and screen sharing are not qualified.

The experimental service retries an unexpected compositor failure, with a
two-second delay and a limit of three starts within one minute. Once the limit
is reached, its existing `OnFailure=gnome-session-shutdown.target` path ends
the failed experimental session instead of restarting indefinitely. A normal
session stop is not restarted. These recovery settings are staged only and
have not been exercised in a live GNOME session.

The directory layout mirrors install paths below `usr/`. A distro package can
stage the payload under its package root and install it with the compositor
binary at `/usr/bin/pantheon-compositor`; the repository's
`../build-deb.sh` creates that arm64 package. On 2026-10-19 package
`0.1.0+git8023955` completed a native M1 Pro login and initialized the 3024×1964
internal output. The compositor loaded the configured wallpaper and the
Wingpanel service ran; the Dock service honored the existing user opt-out
marker. The owner reported slow startup, and native panel appearance was not
visually confirmed. The five-minute LightDM rollback returned to Gala. Portal
clients timed out after activation was skipped before `WAYLAND_DISPLAY` was
published, and native IBus portal activation failed. A subsequent
`0.1.0+git02447cb` login fixed that activation ordering; portal services and
IBus started, and the user reported the session felt responsive. Its first
DRM page-flip attempt returned `Device or resource busy` but the session stayed
active. Native IBus text commit, GNOME portal functions, panel appearance,
lock/logout, crash recovery and external displays remain unqualified. Keep Gala
as the rollback session while these gates are addressed.

The default desktop shell entries in `/etc/xdg/io.elementary.desktop.wm.shell`
name `io.elementary.wingpanel` and `io.elementary.dock`. The experimental
session now stages separate systemd user services for these clients, ordered
after compositor readiness and Wingpanel-before-Dock. A local ARM64 package
build includes the new units, and package `0.1.0+git8c784dc` was installed for
a second native qualification attempt. LightDM requested the Rust session,
but GNOME systemd rejected its target while the prior session was stopping;
subsequent autologin fell back to Ubuntu without starting the Rust compositor.
The temporary session-selection settings were restored and Gala is active.
The first native package had no wallpaper; compositor-side wallpaper
rendering has since been implemented and visually smoke-tested in nested Xvfb,
and installed ARM64 package `0.1.0+git8c784dc` includes it, along with the live
wallpaper settings watcher and Dock opt-out guard. The package still has not
qualified its wallpaper or shell on native output. The installed five-minute
rollback was exercised and returned LightDM to Gala.

The session carries forward the installed Pantheon settings-daemon, keyring,
Orca and elementary settings-daemon targets. It intentionally does not promise
that those services or the compositor are fully compatible; this is an
experimental selection for staged qualification, with Gala still available
as rollback.

The compositor's `org.gnome.ScreenSaver.Lock` bridge launches `gtklock` by
default and passes it the session's Wayland socket. A distro package for this
session must include an `ext-session-lock-v1` client with PAM authentication
(the Ubuntu `gtklock` package provides this protocol client); the source tree
does not install it. `PANTHEON_LOCK_COMMAND` can select another installed
client. Authentication, D-Bus activation and session lock/unlock have not yet
been runtime-qualified. The compositor advertises fractional-scale and
viewporter globals, but rendering quality and moving windows between outputs
with different scales still need nested-session qualification.

## Shell client renderer (2026-10-19)

The compositor advertises `wl_shm` but not `linux-dmabuf`. In the native
2026-10-19 login Wingpanel ran but looped on `VK_ERROR_SURFACE_LOST_KHR`
(GTK4's Vulkan renderer) and used about 2.5 CPU-minutes in 5 minutes with a
2.3 GB peak, which matches the "panel not visible, startup slow" reports. The
Dock did not start only because the owner's `user-disabled` marker was set.
In a private nested Xvfb run of the release compositor the default renderer
reproduced the Vulkan warnings and `GSK_RENDERER=gl` did not. Both shell
units now set `GSK_RENDERER=gl`. `../test-session-units.sh` statically checks
the ordering, restart and renderer settings. Native visibility after this
change is NOT yet verified; the proper long-term fix is `linux-dmabuf` in the
compositor. No native session was started for this change.
