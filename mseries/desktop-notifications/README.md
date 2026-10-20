# M-Series desktop notification popups

Original implementation, GPL-3.0-or-later; see LICENSE. No upstream daemon code
was imported. Entry point: `notifications.py`; runtime siblings: `model.py`,
`popup.py`. Parent installer/service integration is maintained outside this folder.

Windows-style bottom-right popup stack using the native GTK theme: up to three
360×180 logical-pixel cards, newest at bottom, 16-pixel workarea inset and
12-pixel gaps. A smaller workarea reduces capacity/size. Primary monitor
workarea is used, falling back to monitor zero. Monitor/workarea changes reflow
cards. Scoped theme CSS provides border/rounding and title weight.

GTK3 is an intentional X11 compatibility exception: its popup windows are
unmanaged/override-redirect and can be positioned today, without restarting or
changing the custom compositor. GTK4/Wayland does not provide this placement
without compositor support. Set `GDK_BACKEND=x11`; a non-X11 display fails before
bus ownership. Native Wayland placement is unsupported. Xwayland placement
still depends on the compositor's interpretation of X11 coordinates/workarea.

## Launch and ownership

Runtime dependencies (Debian names): `python3`, `python3-gi`, `python3-dbus`,
`gir1.2-gtk-3.0` (including GdkX11 introspection), GTK3 and an X11 display.
No pip packages. Run only after review:

```sh
GDK_BACKEND=x11 /usr/bin/python3 /path/to/notifications.py
```

No automatic activation, install, service modification or compositor change is
performed by this source. Default launch refuses an existing
`org.freedesktop.Notifications` owner and never queues. `--replace` explicitly
requests replacement only when the existing owner allows it. This server does
not allow itself to be replaced implicitly. Parent should stop the previous
notification daemon through its own reversible service procedure before launch.

## Protocol and safety boundaries

Implements Notify, CloseNotification, GetCapabilities, GetServerInformation,
ActionInvoked and NotificationClosed at `/org/freedesktop/Notifications`.
Capabilities are `actions` and `body`, not markup, inline reply, persistence,
images or sound. Clicking the title/body emits the supplied `default` action;
buttons (including Reply) emit their exact supplied identifiers. No action is
invented when absent. Opening applications and composing replies are the
client's responsibility. There is no desktop-file fallback or activation-token
minting; strict focus-stealing prevention may prevent a client raising a window.

No messages are sent or marked read by this daemon. Actions close with reason 4
(undefined), so they are not misrepresented as deliberate dismissals to clients
that use reason 2 for mark-read. Close button uses 2; expiry uses 1; same-sender
CloseNotification uses 3; capacity eviction/DND uses 4. Replacements are limited
to the original unique D-Bus sender and reset expiry without a closed signal.

All content is memory-only. App/title/body are capped at 80/160/1024 characters;
control and bidi formatting characters are removed. Labels use plain GTK text,
never markup or hyperlinks. At most three non-default actions (plus default)
are retained from at most 16 input pairs. Action identifiers stay exact and are
capped at 128 characters; display labels at 48. At most three notices/timers are
retained, no queue/history/notification center. Expiry defaults to 8 seconds,
positive timeouts cap at 120 seconds; timeout zero stays until user/client close
or eviction. Critical urgency and other hints are currently ignored. No icon,
image data/path, executable argv, arbitrary file or URL is opened from input.
D-Bus still decodes an incoming message before these model limits apply.

DND reads `io.elementary.notifications::do-not-disturb` if installed. Turning it
on clears visible cards; suppressed requests retain no content or timers.
Per-app elementary preferences are not implemented. Popup windows decline focus
and do not focus on map; passive pointer interaction is the supported flow.
Full keyboard/screen-reader qualification and enlarged-font/small-monitor visual
qualification remain open. Strings are English; localization is not implemented.

## Isolated checks

Ordinary tests mock dispatch and bus-name calls, never own any notification
service, and never initialize GTK or access private data:

```sh
cd mseries/desktop-notifications
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_notifications
```

Explicit smoke dependencies: `xvfb`, `xauth`, `xdotool`, `dbus-run-session`.
`test_private_smoke.py` creates its own Xvfb and private bus using test-bus.conf
(no service activation directories), temporary HOME/XDG paths and memory-only
GSettings. It checks actual window geometry, unchanged X focus, a real pointer
Reply click, default activation, replacement, close, expiry and DND using only
synthetic fixture content. It never runs the real desktop service. Optional PNG:

```sh
MSERIES_SMOKE_SCREENSHOT="$PWD/test-private-light.png" python3 test_private_smoke.py
GTK_THEME=Adwaita:dark MSERIES_SMOKE_DARK=1 \
  MSERIES_SMOKE_SCREENSHOT="$PWD/test-private-dark.png" python3 test_private_smoke.py
```

Expected 1280×800 geometry, newest first: `(904,604,360,180)`,
`(904,412,360,180)`, `(904,220,360,180)`. Private AT-SPI missing-service warnings
are expected because the test bus has no activation directories. These checks
are not qualification on the running custom compositor or physical monitors.

## Installed desktop integration

From the repository root, run `bash mseries/install-desktop-notifications.sh` to
stage user-local runtime files and the service; use `--activate` to enable/start
this service. It does not restart Wingpanel or the compositor. Runtime code is
under `~/.local/share/mseries/desktop-notifications`; the user unit is
`mseries-desktop-notifications.service`. Remove/disable only that unit to undo
the integration. Another notification server must be stopped before activation.

`blueferry-reply.patch` retains the separate BlueFerry client-side Reply action
change (upstream https://github.com/erikwb/blueferry, GPL-2.0-or-later). It is not
applied automatically by this installer. The current desktop uses its existing
version-matched backend overlay; inspect/rebase that overlay on package updates.
The daemon supports action buttons supplied by any app, but does not invent a
Reply action for applications which do not provide one.
