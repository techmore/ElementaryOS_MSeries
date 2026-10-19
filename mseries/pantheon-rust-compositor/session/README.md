# Experimental Pantheon Rust Wayland session

This tree contains an opt-in GNOME session definition for the Rust compositor.
It uses the installed `gnome-session@SESSION.target` contract: GNOME hides the
required compositor component from its own launcher, and a session target
drop-in requires the dedicated compositor target. That target starts a
`Type=notify` service and therefore waits for the compositor's `READY=1`
notification before session initialization continues. This follows the
[GNOME session systemd documentation](https://gnome.pages.gitlab.gnome.org/gnome-session/re01.html)
and the matching Pantheon units installed on this machine.

The session is named **Pantheon (Rust compositor, experimental)** and uses the
separate `pantheon-rust-wayland` session ID. The existing
`pantheon-wayland` entry and Gala units are not modified. The service binds
`wayland-0`, publishes that value to the systemd user manager after readiness,
and clears the manager value when it stops. `PANTHEON_WAYLAND_DISPLAY` selects
the explicit socket; without that variable the nested development backend
continues to allocate an automatic socket, and the native backend can also use
automatic allocation for manual development launches.

The experimental service retries an unexpected compositor failure, with a
two-second delay and a limit of three starts within one minute. Once the limit
is reached, its existing `OnFailure=gnome-session-shutdown.target` path ends
the failed experimental session instead of restarting indefinitely. A normal
session stop is not restarted. These recovery settings are staged only and
have not been exercised in a live GNOME session.

The directory layout mirrors install paths below `usr/`. A distro package can
stage the payload under its package root and install it with the compositor
binary at `/usr/bin/pantheon-compositor`; the repository's
`../build-deb.sh` creates that arm64 package. Do not add these files to
the active host session until the native backend, login, app startup, lock,
logout and recovery have been qualified on a separate session. Native DRM
startup takes over the display device and has not been runtime-qualified on
this machine.

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
