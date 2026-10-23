# M-Series desktop notification popups

Original implementation, GPL-3.0-or-later; see LICENSE. No upstream daemon code
was imported. Entry point: `notifications.py`; runtime siblings: `model.py`,
`popup.py`, `focus.py`, `history.py`, `center.py`. Parent installer/service integration is maintained outside this folder.

Apple-style upper-right popup stack using the native GTK theme: up to three
360×72 logical-pixel cards (20% shorter than the previous 90-pixel cards), newest at top, 16-pixel workarea inset and
12-pixel gaps. A smaller workarea reduces capacity/size. Primary monitor
workarea is used, falling back to monitor zero. Monitor/workarea changes reflow
cards. Scoped CSS uses the dock-taskbar.patch gray, rgb(163,168,174), with dark
foreground in both light and dark sessions. A compact app/close header sits
above the single-line summary/preview and up to three actions at the right;
long text and button labels ellipsize, with full action labels in tooltips.
No global theme settings are changed. RGBA visual, transparent draw clearing,
and an X Shape/input shape fallback produce an actual rounded silhouette,
including on an uncomposited X11 display. Reentrant renders are serialized
to avoid duplicate construction. Known `reply`/`inline-reply` aliases with the
same Reply label produce one explicit button, preferring `reply`; other action
keys/labels are retained under the existing three-action bound.

GTK3 is an intentional X11 compatibility exception: its popup windows are
unmanaged/override-redirect and can be positioned today, without restarting or
changing the custom compositor. GTK4/Wayland does not provide this placement
without compositor support. Set `GDK_BACKEND=x11`; a non-X11 display fails before
bus ownership. Native Wayland placement is unsupported. Xwayland placement
still depends on the compositor's interpretation of X11 coordinates/workarea.

## Launch and ownership

Runtime dependencies (Debian names): `python3`, `python3-gi`, `python3-dbus`,
`python3-cairo`, `python3-gi-cairo`, `gir1.2-gtk-3.0` (including GdkX11 introspection), GTK3 and an X11 display.
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
client's responsibility. Toast clicks use app-supplied actions; the center can
open an existing validated desktop entry for expired generic notifications.
There is no activation-token minting. A scoped M-Series focus bridge handles explicit Open/Reply clicks for
BlueFerry GTK: the desktop-entry hint must match its known client ID and the
notification's D-Bus sender must own the BlueFerry backend name. After normal
action delivery, it asynchronously calls the compositor's DesktopIntegration
FocusWindow only when exactly one existing window has that exact app ID. It
never launches a program or executes a hint. Other clients retain their normal
activation behavior. No window is raised merely because a notice appears.

No messages are sent. Notification read controls do not write phone read state;
opening a conversation may mark it read through BlueFerry’s normal behavior. Actions close with reason 4
(undefined), so they are not misrepresented as deliberate dismissals to clients
that use reason 2 for mark-read. Close button uses 2; expiry uses 1; same-sender
CloseNotification uses 3; capacity eviction/DND uses 4. Replacements are limited
to the original unique D-Bus sender and reset expiry without a closed signal.

All content is memory-only. App/title/body are capped at 80/160/1024 characters;
control and bidi formatting characters are removed. Labels use plain GTK text,
never markup or hyperlinks. At most three non-default actions (plus default)
are retained from at most 16 input pairs. Action identifiers stay exact and are
capped at 128 characters; display labels at 48. At most three notices/timers are
retained as visible popups. A separate center retains at most 100 memory-only
notification records until this service exits; no history is written to disk. Expiry defaults to 8 seconds,
positive timeouts cap at 120 seconds; timeout zero stays until user/client close
or eviction. Critical urgency and other hints are currently ignored. No icon,
image data/path, executable argv, arbitrary file or URL is opened from input.
D-Bus still decodes an incoming message before these model limits apply.

DND reads `io.elementary.notifications::do-not-disturb` if installed. Turning it
on clears visible cards; suppressed requests have no popup timers, but remain
in bounded notification history for later review.
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

Expected 1280×800 geometry, newest first: `(904,16,360,72)`,
`(904,100,360,72)`, `(904,184,360,72)`. Private AT-SPI missing-service warnings
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

Compact private smoke also checks 72-pixel actual allocation for long text and
three actions, full body accessibility naming, duplicate Reply aliases, forced
synchronous render reentry, and backdrop-visible rounded corners.

## Shell-aware upper-right placement

Popups start 16 logical pixels below the usable top edge and 16 from the right,
newest first, then stack downward with 12-pixel gaps. The separate notification
center bell stays in the bottom-right dock; this popup code does not move it.

`workarea.py` measures known `io.elementary.wingpanel` (top) and
`io.elementary.dock` (bottom) first showing frames after enumerating application
names. No private application trees/content are inspected. App identity defines
the edge: the dock's bogus Wayland y=0 never makes it a top bar. Width must match
the primary monitor within 5% (minimum 16 pixels). Heights clip to 256 pixels
and half the monitor height. A nonmatching, hidden or absent bar adds no inset.
GDK reservations are respected without double subtraction: each resulting edge
is the more restrictive of the workarea edge and its measured shell boundary.
The bottom dock limits available stack capacity, not the stack's top anchor.

The parent installer can scope `MSERIES_NOTIFICATION_TOP_INSET=124` and
`MSERIES_NOTIFICATION_DOCK_INSET=72` to the current live service based on its
observed shell geometry. Those values protect the first popup while the
asynchronous measurement runs; each unavailable edge retains its own fallback,
while a successful observation replaces it and confirmed absence clears it.
Unset fallbacks are zero, as in stock private Xvfb: first popup y=16. A 124-pixel
top-panel fixture gives y=140. For the supplied 2419×1571 full workarea and
124/72 shell heights, usable area is (0,124,2419,1375) and first card is
(2043,140,360,72). No shell coordinates are guessed from unrelated windows.

Optional dependency: `gir1.2-atspi-2.0`. One metadata worker/child maximum uses
150 ms AT-SPI call/startup timeouts, a 400 ms traversal budget and an 800 ms
process deadline. GTK never waits on accessibility RPCs. Cache refresh is
demand-driven, at most once per 15 seconds, and invalidates on monitor changes;
stale results are rejected. Completion reflows only changed insets, with no
polling timer or render-refresh loop. No accessible names or contents are logged.
An already displayed popup may keep its cached location until the next
notification/render after the cache interval. Arbitrary shell orientation and
secondary/non-primary-width bar attribution remain unsupported.

Pure tests: `python3 -m unittest -v test_workarea`. They cover top/bottom partial
and already-reserved areas, absence, unrelated apps, bogus y=0, clipping,
asynchronous fallback/cache bounds and stale results. Private smoke checks
upper-right y=16, injected Wingpanel y=140, unchanged gray rounded 72-pixel
cards, pointer actions and focus. No live probe is required for these fixtures.

## Taskbar bell and notification history

The native GTK4/Granite taskbar bell sits beside the clock. Click it to review
recent notifications, Open, or Reply. Right-click for Mark all as read and Do Not
Disturb. Unread count and DND state come from the service; failures remain visible
and unknown service state is not displayed as an empty inbox. Mark all as read
changes only local notification records and clears toasts with reason 4, so it
does not ask BlueFerry to mark phone messages read. DND uses elementary’s saved
`io.elementary.notifications::do-not-disturb` preference.

The custom user-session API is exported under bus name
`org.freedesktop.Notifications`, path `/org/techmore/MSeries/Notifications`,
interface `org.techmore.MSeries.Notifications1`: GetStatus, ListNotifications,
MarkAllRead, SetDoNotDisturb, OpenNotification, InvokeAction, and the content-free
Changed signal. History is capped at 100 entries; the taskbar requests at most
50. It begins with alerts received after service startup and resets at restart.

Expired BlueFerry notifications preserve only the validated opaque message
handle supplied by the actual backend owner. Clicking a historical entry uses
a fixed installed BlueFerry helper with that handle, never the notification’s
executable argv. Other expired entries can open a validated installed desktop
ID when supplied. Opening is user initiated; no message-send action is exposed.

The complete canonical dock build includes TaskbarNotifications alongside
TaskbarRow, StartMenu, TaskbarCodexBar and AppResolver. A widget-only private
D-Bus/display probe lives in `../dock-taskbar/notifications-probe/run.sh`, covering
unavailable service, history, Open/Reply, local read controls and rejected DND
saves. The private popup smoke also checks the actual center API’s history,
MarkAllRead and DND behavior on a memory GSettings backend.
