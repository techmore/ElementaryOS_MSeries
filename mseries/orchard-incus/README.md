# Orchard for Incus

A native GTK4/Granite manager for Incus containers and VMs on elementary OS
M-series. This Python implementation is the installed foreground application
verified in the [real Wayland qualification](../../docs/orchard-incus.html).
The separate `../orchard-incus-native/` Vala manager and Wingpanel module remain
available; this installer does not remove or replace them.

Inspired by [andrew-waters/orchard](https://github.com/andrew-waters/orchard)
(MIT, © Andrew Waters; reviewed at `2c78257c8602ffed61f383ee6e737bfc37b142ee`).
This is an independent Incus CLI implementation; no upstream Swift code is copied.

## Developer workflows

- Container/VM creation with distribution presets, custom image selection,
  resource limits, explicit VM Secure Boot choice and cancellable download progress.
  Failed/cancelled creation cleanup verifies a unique creation marker and
  cannot use an existing guest name as ownership evidence.
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
as fallback. Window closure stops owned timers and the monitor. Per-instance metadata edits
serialize, and settings apply all limits in one idempotent update.

Guest command output retains a 65,536-character pending tail and a
262,144-character GTK text tail per live instance. Read-only output disables GTK
undo history so trimmed text is actually released. Deleted guests release their
output buffers after active commands finish, and hidden dashboard cards are
pruned on inventory refresh. Renaming a stopped guest preserves its output.
Very fast discarded output is
labelled. Incremental UTF-8 decoding handles split characters and long lines;
scrolling back pauses automatic tail following. Creation progress uses its
existing separate stream.

Dashboard cards populate in batches of 16 and offscreen chart updates wait
until scrolled into view. Rows are still retained GTK widgets, so very large
fleets need future virtualization. The synthetic audit measures UI-thread updates. A separate real Wayland run
verified 11 workflow groups and compositor presentation feedback (action latency
26 ms median / 34 ms p95). It does not measure physical input-to-photon or a
long-duration memory budget. See the receipt for exact conditions and limits.

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

## Real Wayland qualification

On the actual desktop, with cached Alpine container/VM images and AT-SPI:

```sh
audit_dir=$(mktemp -d)
GDK_BACKEND=wayland python3 tools/qualify-wayland.py \
  --source "$PWD" --output "$audit_dir" --run
```

This opens native windows and creates/deletes uniquely owned temporary guests.
It uses programmatic GTK actions; the backup Save portal uses AT-SPI, and a
one-shot guest profile verifies native Terminal login without keyboard injection.
Use a new empty output directory for each run. The fixture driver rejects
unexpected names/images/limits and host destinations. See
[`audit/2026-10-18-wayland.json`](audit/2026-10-18-wayland.json) for the installed
build's source hashes, all eleven results and measurement limits. The earlier
synthetic receipt remains available as the baseline for that separate method.

## Session resource and retention probes

The native driver can repeat all workflows in one process with unique guest
identities, and observe idle resources before and afterwards:

```sh
audit_dir=$(mktemp -d)
GDK_BACKEND=wayland python3 tools/qualify-wayland.py \
  --source "$PWD" --output "$audit_dir" --run \
  --cycles 3 --idle-before 300 --idle-after 600
```

`resources.jsonl` samples process RSS, PSS, private memory, cumulative CPU,
threads, file descriptors, actual focus/minimized state and cache sizes every
five seconds. CPU percentage is CPU-seconds / elapsed-seconds × 100 (one core =
100%). Reaped command-client CPU is recorded separately; the Incus daemon,
running guests and compositor are outside the process totals. Idle driver
checks run once a second; phase checkpoints collect Python garbage. Exclude
startup and workflow settling when comparing idle intervals. Renderer/allocator
high-water marks and shared graphics mappings can keep RSS above startup without
being a live-object leak. This is a session observation, not a battery or thermal
qualification.

For a fast, independent reproduction of output retention without Incus access:

```sh
xvfb-run -a env -u DBUS_SESSION_BUS_ADDRESS GSK_RENDERER=cairo GDK_BACKEND=x11 \
  python3 tools/probe-output-retention.py --output /tmp/orchard-retention.json
```

Use a new output file. `--source /path/to/package-parent` compares another
installed/candidate build using the same probe. It sends about 48 Mi characters
(72 MiB UTF-8) through 12 synthetic guest identities, then empties the inventory.
Cache and undo counts identify retained text independently of process RSS.
