# Orchard for Incus

A native GTK4/Granite manager for Incus containers and VMs on elementary OS
M-series. This Python implementation is the installed foreground application
reviewed in the [October 18 UX audit](../../docs/orchard-incus.html).
The separate `../orchard-incus-native/` Vala manager and Wingpanel module remain
available; this installer does not remove or replace them.

Inspired by [andrew-waters/orchard](https://github.com/andrew-waters/orchard)
(MIT, © Andrew Waters; reviewed at `2c78257c8602ffed61f383ee6e737bfc37b142ee`).
This is an independent Incus CLI implementation; no upstream Swift code is copied.

## Developer workflows

- Container/VM creation with distribution presets, custom image selection,
  resource limits and cancellable download progress.
- Live searchable inventory, dashboard and per-instance CPU/memory histories;
  lifecycle controls, native terminal shell, snapshots, clone/rename/delete
  and backup export.
- Command execution with bounded Unicode output, file browsing/transfers,
  folder sharing, port forwards and instance settings.
- Cached images, networks, storage accounting and profiles.
- Native light/dark appearance, reduced-motion support, accessible dashboard
  buttons, contextual action menus and explicit loading/failure states.

Search matches name, image, state and IPv4. Ctrl+F finds instances, Esc clears
search, Ctrl+N creates an instance, Ctrl+1/Ctrl+2 switch Dashboard/Instances,
F5 refreshes, Menu/Shift+F10 opens instance actions, and Ctrl+? lists shortcuts.

Compose, Kubernetes and local-AI sandbox management are not implemented here.

## Run and install

Requires Python 3, PyGObject, GTK4, Granite 7, `incus`, and socket access for
the user (typically the `incus-admin` group). Shell uses elementary Terminal.

```sh
./orchard-incus
./install.sh             # current user; retains one previous package
./install.sh --pin       # also pin to elementary dock
./install.sh --uninstall
```

Reopen the app after an update. Settings/window state use
`$XDG_STATE_HOME/orchard-incus/state.json`. No root install is required.

## Performance boundaries

List refreshes coalesce; tab/resource/catalog reads retain one running and one
replaceable pending request per destination. JSON inventory reads time out
in 20 seconds. Lifecycle events drive refreshes, with chart/idle/safety polling
as fallback. Window closure stops owned timers and the monitor.

Guest command output retains a 65,536-character pending tail and a
262,144-character GTK text tail per instance. Very fast discarded output is
labelled. Incremental UTF-8 decoding handles split characters and long lines;
scrolling back pauses automatic tail following. Creation progress uses its
existing separate stream.

Dashboard cards populate in batches of 16 and offscreen chart updates wait
until scrolled into view. Rows are still retained GTK widgets, so very large
fleets need future virtualization. The audit measures UI-thread updates, not
real Wayland frame pacing or a long-duration memory budget.

## Verification

```sh
python3 -m unittest discover -s tests
xvfb-run -a env -u DBUS_SESSION_BUS_ADDRESS GSK_RENDERER=cairo GDK_BACKEND=x11 \
  G_DEBUG=fatal-criticals python3 -m unittest discover -s tests
xvfb-run -a env -u DBUS_SESSION_BUS_ADDRESS GSK_RENDERER=cairo GDK_BACKEND=x11 \
  python3 tools/audit-ui.py --output /tmp/orchard-audit --screenshots
```

The audit harness uses synthetic inventories and never calls Incus. Its
measurements and screenshots are reproducible. Six mutating live tests are
opt-in with `ORCHARD_LIVE=1`; ordinary test runs skip them. See
[`audit/2026-10-18.json`](audit/2026-10-18.json) for exact results and limits.
