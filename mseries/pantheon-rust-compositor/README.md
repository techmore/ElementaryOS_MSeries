# Mutter-minimal viable Rust for elementaryOS M-series

## October 29 server-side frames for X11 windows

X11 apps that ask the window manager for decorations (WiFiman Desktop, xterm,
plain GTK 3 windows on X11) now get a title bar drawn by the compositor
(`src/decorations.rs`): drag to move, resize from the edges within the app's
size hints, the `button-layout` buttons, double-click to maximize. Header-bar
(client-decorated) X11 windows and every Wayland window are unchanged.
[`ssd-probe/run.sh`](ssd-probe/run.sh) checks it on a private nested display.

## October 20 window recovery and focus audit

The window-snapping update supports XWayland halves/quarters and left/right
edge drag zones as well as native Wayland. A separate explicitly launched
[window recovery chooser](../window-recovery/README.md) restores minimized apps
without the dock. The [focus audit](FOCUS-AUDIT-2026-10-20.md) records panel first-
buffer focus, repeated dock activation, native launcher bypass and opt-out fixes.
The private dock has been rebuilt; the live dock remains disabled. Compositor
updates take effect at a fresh login, with no forced logout or panel restart.


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
For a stack drawing comparing existing elementary OS, Omarchy on Asahi, and
the proposed Pantheon MVP—along with a tested-versus-open status table—see
[`ARCHITECTURE-AND-STATUS.md`](ARCHITECTURE-AND-STATUS.md).
For a visual comparison of Gala/Mutter and the Rust/Smithay migration stages,
startup timing, CPU, memory, and power evidence, open the standalone
[`migration dashboard`](dashboard.html).
For matched CPU/RSS sampling, use
[`collect-session-metrics.sh`](collect-session-metrics.sh) and the
[`pidstat` thread sampler](collect-session-thread-profile.sh); capture the
same workload in both sessions before drawing performance conclusions.

On 2026-10-19 the installed experimental session completed its first native
M1 Pro login and scanned out an AR30 3024x1964 framebuffer. The owner reported
that startup felt slow; the first Rust session had no Wingpanel, bottom dock,
or wallpaper/background. A timed LightDM rollback returned to Gala and
restored the background. Separate systemd user services have since been staged
to launch Wingpanel and Dock after the compositor. Installed ARM64 package
`0.1.0+git8c784dc` includes those units. Its attempted second LightDM launch
did not reach the compositor: GNOME systemd reported a target transaction
conflict while the previous session was stopping, then LightDM fell back to
Ubuntu. The temporary LightDM, `.dmrc`, and AccountsService selections were
restored, and Gala is active. Package `0.1.0+git8c784dc` also includes the
wallpaper renderer, live wallpaper settings watcher, and Dock opt-out guard; it
is installed but not qualified on native output. Package SHA-256:
`a83d4709064bc447ecd24909a4d9a0830d5f168ee20b62e468e23557e5257329`.
The experimental LightDM entry now waits up to 30 seconds for the previous
`gnome-session-pre.target` stop job to clear before starting GNOME. This
addresses the observed transaction conflict. Local ARM64 package
`0.1.0+gite920d2e` includes the wrapper; its executable mode was verified in
the built package. Native login qualification is still open.
This proves the native display path and rollback, not a
complete Pantheon session or a performance/stability improvement.

Snapping (phase 0 of the [next-generation plan](NEXT-GEN-INVESTIGATION-2026-10-21.md#2-snapping-and-adding-more-apps-to-a-snap)):
every window has one placement (`Floating`, `Tiled`, `Maximized{prior}`,
`Fullscreen{prior}`) keyed by `Window::id()` in `src/placement.rs`, which holds the
pure, unit-tested geometry. `Super+Left/Right` snap halves and toggle (the same or
opposite side restores the pre-snap rect; quarters slide or grow), `Super+Up`
maximizes and remembers a tile, `Super+Down` steps back (maximized → tile →
floating). Quarter chords (`Super+Alt+U/I/J/K`, Super+keypad) toggle too.
`Super+Shift+Left/Right` moves a window, its tile or its maximize to the adjacent
output. Dragging a snapped or maximized window more than 8 px restores its
floating size with the grabbed title-bar point under the pointer; the 40 px edge
zones preview what the window will actually get (minimum size included), Escape
cancels, and release recomputes the zone for the current work area. Wayland
windows move only after the client acks the new size (400 ms fallback), tiles
send `Tiled*` states for their work-area edges, a client larger than its zone
stays snapped and grows inward from the screen edge, and snapped X11 windows
that resize themselves are told their rect again. The window's output is the
one its geometry overlaps most, not a random one. Bindings load at session
start (`org.techmore.mseries.snapping` `maximize`/`restore` plus the Mutter and
GNOME keys, with built-in defaults). Phase 1: snapping a half next to an
empty half opens **Snap Assist**, live scaled thumbnails of the other windows on
that output and workspace in the empty half (arrows/Tab, Return or click to
choose, Escape or any other key to dismiss; clients are not resized). Choosing
one, or snapping beside a window already on the other half, forms a two-member
**snap group** (`src/snap_group.rs`, a `SnapNode` split tree): members raise
together, dragging their shared edge resizes both (clamped to minimum sizes),
maximize/restore keeps the group, and un-snapping, closing or moving a member
returns the other to its half. Nested regression:
[snap-tests](snap-tests/README.md). Multi-output, X11 and native input remain
owner acceptance.

At startup, the keyboard now loads the user's XKB model, active XKB layout,
options, and repeat settings from GNOME GSettings. This applies the M-series
`ctrl:swap_lwin_lctl` and `ctrl:swap_rwin_rctl` Command/Ctrl mappings. The compositor
polls settings once per second and applies layout, option, and repeat changes live; this path
is build-checked but not runtime-qualified. The current source is US;
`mozc-jp` is installed but inactive. F5 dictation is an active IBus workflow
and inserts committed Unicode into focused fields. The Rust compositor's
nested GTK Wayland field now passed a Mozc `mozc-jp` commit using the private
test profile described below; the native field and F5 workflow remain open.

The prototype now starts Smithay's rootless XWayland window manager, maps X11
windows into the shared desktop space, routes move/resize, maximize,
fullscreen, minimize, restore, and activation requests, sends keyboard input to
focused X11 clients, and bridges clipboard and PRIMARY selection ownership and
transfers. Native startup exports the selected `DISPLAY` through D-Bus and
systemd activation environments; the `--run` client waits for XWayland
readiness. An isolated Xvfb smoke mapped an X11 Zenity window, accepted
keyboard input, and exposed the focused window (`zenity`, workspace 0) through
the live window-list D-Bus method. Clipboard/PRIMARY transfers, session
activation, and broader X11 window behavior remain unqualified. The package
depends on the `xwayland` executable.

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
backend for M-series qualification. It supports the Pantheon shell protocol,
window basics, monitor configuration and lock bridge. The installed opt-in
session completed a first native display scanout on the M1 Pro, while full
shell, input and recovery behavior still need qualification. The staged session
remains separate from Gala and is not selected by default.

### Readiness decision (2026-10-19)

This branch is **not ready to replace Gala for daily Pantheon use**. On
2026-10-19, an isolated five-minute LightDM login completed and produced the
first native scanout on the M1 Pro: plane 0 used the compositor's AR30
framebuffer at 3024x1964. The owner confirmed the desktop was usable but slow
to appear. Wingpanel, Dock and wallpaper were missing in that first run.
The timed rollback returned to Gala and restored the background. This qualifies
native startup, internal-panel scanout and automatic rollback only; native
keyboard/pointer workflows, complete shell integration, external displays,
wallpaper after the new renderer, lock/unlock and compositor-failure recovery remain open.

A later qualification using package `0.1.0+git02447cb` confirmed that
compositor readiness now publishes the Wayland display before portal startup:
the portal service and providers came up within about one second, and IBus
started without the previous 120-second activation timeout. The user reported
the session felt responsive. This run still logged one initial DRM page-flip
`Device or resource busy` error and a missing Mutter `ServiceChannel` warning
from the GNOME portal backend. It does not qualify portal dialogs, screen
sharing, native text commits, or a performance/power improvement over Gala.

The instrumented `0.1.0+git7a0ac92` login reached the first committed
Wingpanel buffer about 2.2 seconds after the Rust session manager started
(about 1.7 seconds after the compositor service started). The owner described
this run's overall opening time as really good, then noted the wallpaper-to-
Wingpanel gap still felt slow. The journal shows wallpaper load at +0.11 s,
Wingpanel service start at +0.51 s, first panel surface request at +1.61 s,
and first buffer at +2.22 s, relative to session-manager start. This is about
2.11 s from wallpaper load to first panel buffer; the journal milestone is not
a direct measure of visible pixels or first interactive use. The five-minute
rollback completed successfully at 12:26 EDT and returned LightDM to Gala.
The Wingpanel user unit is ordered immediately after compositor readiness;
about 1.10 s of the observed gap is after its process starts and before its
first surface request. The cause of that interval remains unidentified.
The owner also reported that
window corners look inconsistent and unwanted. This is now a visual
acceptance issue; affected apps and window states still need examples. The
3024×1964 panel mode looked too zoomed out. A later Rust-only 2× run retained
the high-resolution mode; the owner now prefers 1.25×, which is staged for the
next login and remains unqualified. These owner reports
are tracked in [`EXPERIENCE-REQUIREMENTS.md`](EXPERIENCE-REQUIREMENTS.md) and
the [migration dashboard](dashboard.html).

In a later isolated login on 2026-10-19, the staged 2× Rust display scale
preserved the 3024×1964@120 Hz mode. Wallpaper loaded +0.14 s after session
manager start; Wingpanel requested its first panel surface at +1.60 s and
committed its first buffer at +2.25 s. A 45-second post-login desktop sample
measured median CPU at 5.4% of one core for the compositor and 0.5% for
Wingpanel; median RSS was about 190.5 MiB and 422.5 MiB, respectively. A
one-minute `pidstat` profile captured both processes and their threads. The
machine was on AC and the workload was not controlled idle, so these values
cannot establish a performance win against Gala. The owner preferred 1.25×
after seeing 2×; that Rust-only fractional scale is staged for the next login
and has not yet been qualified. Raw captures are in the task-local artifacts
directory, outside this repository.

After the timed rollback, Gala's compositor, wallpaper and Wingpanel processes
started at 12:44:49 EDT. The owner saw the background well before Wingpanel,
which appeared about two minutes later. At login, systemd skipped
`xdg-desktop-portal.service` because `WAYLAND_DISPLAY` was absent from the user
manager environment; portal requests then timed out at 120 seconds, and the
portal and its backends started at 12:46:49 EDT. This timing strongly implicates
portal activation in the delayed panel, but does not prove it caused the
visible delay. Investigate early display-environment publication and portal
activation ordering before the next startup comparison. Gala remains active.

The metrics helpers now match Wingpanel/Dock processes by their absolute
executable path as well as their truncated `comm` name. A corrected 30-second
Gala capture measured median CPU of 15.6% for Gala and 0.7% for Wingpanel;
this quiet-desktop sample and the Rust post-login sample used different
workloads, so they are not a matched comparison.

An exploratory 30-second per-thread sample of the returned Gala session at
12:33 UTC included Gala and Wingpanel (Dock was opted out). `pidstat` reported
26.26% of one core for Gala, 0.50% for Wingpanel, with 24.29% on Gala's main
thread. Foreground activity was not controlled, so this is not an idle or
Rust-comparison result. The raw capture is outside the repository at
`/home/sdolbec/Documents/Codex/2026-10-18/i-no/work/artifacts/gala-thread-profile-20261019.txt`.

In private Xvfb, the release binary launched a GTK Wayland Zenity field;
synthetic key events reached it, and IBus/Mozc committed `konnichiha` as
`こんにちは` using `mozc-jp` with Hiragana enabled in a private profile. This
qualifies one nested input-method-v2/text-input-v3 workflow, not host source
switching, F5 dictation or native input. XWayland also passed an isolated X11
Zenity window and keyboard smoke; clipboard/PRIMARY remain unqualified.
Installed Wingpanel binds the shell protocol and submits SHM panel buffers in
private Xvfb, but the Rust session did not launch it. Keep Gala selected while
the shell launcher is qualified and the new wallpaper renderer is tested on
native output.

The compositor now exposes Dock's `org.pantheon.gala.DesktopIntegration`
D-Bus interface. Window enumeration, app IDs, focus state, workspace listing,
activation and reorder, dynamic workspace creation, window movement, and
cross-workspace focus are implemented. An isolated Xvfb run with a temporary
Wayland client exercised workspace creation, movement, switching and focus.
Gala's scaled multitasking view remains unsupported; `PerformAction(1)` and an
upward three-finger swipe now toggle a grid overview ("expose") instead, which
rearranges the active workspace's windows per output and restores the prior
plain, tiled, maximized or fullscreen arrangement on exit. A private
Xvfb/Winit D-Bus smoke with two GTK Wayland windows opened and closed it; see
`ARCHITECTURE-AND-STATUS.md` for open visual/native gaps.
The nested stock Dock 8.3.3 smoke bound the panel protocol and attached buffers,
but also logged its known asynchronous workspace-initialization critical, so
Dock interaction is still not qualified end to end.

The ARM64 package from commit `83a663c` is saved at
`/home/sdolbec/Documents/Codex/2026-10-18/i-no/work/artifacts/pantheon-workspace-release/pantheon-rust-compositor_0.1.0+git83a663c_arm64.deb`
(SHA-256 `f34220be364417e92c4dab2aa8b9c3c29b5b1cfc9427c710318b42634684634a`).
Its package contents, dependencies and shared-library links were inspected;
it was installed with `gnome-session` and `gtklock` on 2026-10-19 and selected
once through LightDM. The compositor source is unchanged from `83a663c`; the
later commits in this branch update the DRM probe and documentation. The nested
runtime evidence below used the earlier package
from commit `619ca5c`, saved at
`/home/sdolbec/Documents/Codex/2026-10-18/i-no/work/artifacts/pantheon-workspace-release/pantheon-rust-compositor_0.1.0+git619ca5c_arm64.deb`
(SHA-256 `aee4c9af0d12c1a2bddbfd45dcd5a79e71afe8c8adc28d9ff46e7cf204d0ea13`).
The earlier package was not installed. Its release binary started in private Xvfb,
reported XWayland ready, and served a Zenity window through `GetWindows` with
`app-id=zenity`, focus true and the initial two-workspace count. This qualifies
the nested release path for continued development testing only. It does not
qualify visible rendering, native DRM scanout, the full Pantheon shell or a
login session. A second isolated run started Wingpanel against the same release
binary: it sent `get_panel`, top anchor and `never` hide-mode requests, and
allocated SHM buffers without a keyboard assertion. The compositor's
`org.gnome.Mutter.DisplayConfig.GetCurrentState` returned the nested 1280×800
output. Both runs used private D-Bus/Xvfb and a private GSettings fixture; the
active Wingpanel session was not restarted. These checks do not qualify native
DRM scanout, physical keyboard input, the Dock, or a complete login session.

The next gate is to nested-qualify the staged Wingpanel and Dock startup against
`/etc/xdg/io.elementary.desktop.wm.shell`, and qualify the new wallpaper renderer
on native output. Then qualify shell rendering, Dock launcher/window switching,
GTK/Qt clients and real F5 dictation. Package those changes before another
native login. Keep the measured startup, resource, latency, power and
crash/recovery comparison against Gala open; one successful login does not
establish the migration as faster, lighter or more reliable.

The staged systemd service now retries an unexpected compositor failure with
a two-second delay, capped at three starts per minute. After that limit, its
`OnFailure` action requests the GNOME session shutdown target rather than
looping indefinitely. Native DRM event-source and frame-completion errors now
stop the compositor with a failure status; three consecutive render failures
do the same. This connects unrecoverable display failures to the service's
restart path instead of leaving a running but unusable session. The restart,
shutdown and hardware-failure paths have not been exercised in an isolated
login.

`build-deb.sh` builds an arm64 release binary with `native-drm` and packages it
with the separate experimental session files. It derives shared-library
dependencies and requires `dbus-bin`, `gnome-session`, `gtklock`, and
`xdg-desktop-portal`. Build it locally with
`OUTDIR=/path/to/output mseries/pantheon-rust-compositor/build-deb.sh`. The
current package above includes the XWayland runtime dependency and is for
isolated qualification; the build script does not install it. The nested IBus
path is qualified for one GTK/Mozc configuration; native IBus behavior and any
display takeover remain unqualified.

## Install on the existing stack

`mseries/install-pantheon-rust-compositor.sh` deploys the package beside Gala.
Dry run is the default and changes nothing; acting needs root and `--yes`:

```sh
bash mseries/install-pantheon-rust-compositor.sh --dry-run        # checks and plan only
bash mseries/install-pantheon-rust-compositor.sh --status         # installed-vs-loaded state
bash mseries/install-pantheon-rust-compositor.sh --verify         # read-only integrity checks
sudo bash mseries/install-pantheon-rust-compositor.sh --install --yes --deb <package>
sudo bash mseries/install-pantheon-rust-compositor.sh --select --yes        # next login
sudo bash mseries/install-pantheon-rust-compositor.sh --restore-gala --yes # rollback
sudo bash mseries/install-pantheon-rust-compositor.sh --uninstall --yes
```

The Gala package, `/usr/bin/gala` and the `pantheon-wayland` session entry are
never modified; the installer refuses to run without them. It starts and
enables nothing — after `dpkg` it only reloads the user manager's unit list, and
the compositor units carry `RefuseManualStart=on`. Selecting the Rust session
only rewrites the LightDM autologin drop-in (with a backup) and takes effect at
the next login; no timer is armed and nobody is logged out.

## Performance evidence

Matched captures come from `collect-session-metrics.sh`; reduce them with
`summarize-metrics.py` (per-process mean, median, min, max; `NA` samples are
excluded and counted). Startup and per-thread evidence come from
`collect-session-startup.sh` and `collect-session-thread-profile.sh`. The
public summary is the published performance page
[`docs/rust-compositor-performance.html`](../../docs/rust-compositor-performance.html),
linked from the build monitor; the stage-by-stage migration view is the
standalone [`dashboard.html`](dashboard.html). Retained captures are in
[`metrics/`](metrics/). No capture so far is a matched A/B, and no power
measurement exists; the readiness decision above still stands.

## Dock HDMI boundary

The WD22TB4 HDMI goal remains in
[`../fairydust/usb4/PRIMARY-GOAL.md`](../fairydust/usb4/PRIMARY-GOAL.md). The
G3 gate is DCP/kernel link training; a compositor cannot fix an output the
kernel has not exposed. Keep compositor modeset/hotplug qualification separate.

No change here qualifies an M-series session or hardware. Gala remains the
production session and rollback until the scoped experience passes on-device
acceptance.

### Visible dock work area (October 20)

Visible Pantheon panels reserve monitor work area. Maximized and tiled apps
reflow as before; floating Wayland and XWayland apps now move clear and shrink
only when necessary, without focus changes. Fullscreen remains fullscreen.
The owner approved permanent 48-pixel, no-auto-hide dock operation; the
repeatable setup is `mseries/dock-policy/enable-permanent.sh`. The dock client
is still Vala/GTK; the compositor integration is Rust. All 18 unit tests and
the isolated native/X11/focus/typing and bottom-clearance smoke pass. Native
hardware clearance awaits loading the staged compositor at next login.
