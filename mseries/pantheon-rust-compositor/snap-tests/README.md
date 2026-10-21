# Nested snap regression

Drives the nested compositor through the `gesture-probe` socket (absent from
normal builds and never packaged) and asserts the geometry the compositor laid
out after a real GTK 4 client acked and committed each configure.

```sh
cargo build --manifest-path rust/Cargo.toml -p pantheon-compositor --features gesture-probe
SNAP_TEST_BIN="$PWD/rust/target/debug/pantheon-compositor" \
SNAP_TEST_OUT=/tmp/mseries-snap-receipts \
  bash mseries/pantheon-rust-compositor/snap-tests/run-snap.sh
```

Requires Xvfb/xvfb-run, dbus-run-session and Python GI GTK 4. The runner creates
its own display, D-Bus session and runtime directory; settings use the memory
backend. Probe commands: `snap left|right|up|down` (the Super+Arrow paths),
`mode maximize|unmaximize|fullscreen|unfullscreen` (client requests),
`press X Y` / `motion X Y` / `release` (the real `MoveSurfaceGrab`, as a title-bar
drag starts it) and `placement` (logs `snap probe placement=… x= y= w= h=
pending= states= area= preview=`).

Checks (23): halves, toggles and restore to the pre-snap rect (S1); maximize
remembering a tile and Super+Down stepping back (S2); `Tiled*` states on the
work-area edges only (S8); no move before the client acks (S4, visible as
`pending=true` lines); a click-sized drag leaving a tile alone; drag-out
restoring the floating size with the grab point under the pointer; the edge
preview and release snap recomputed at release (S6); restore after a drag-snap
returning to where the drag began; and a minimum width wider than a half
growing inward from the screen edge on both sides (S5); then a GTK 3 window on
XWayland snapping, resizing itself and being told its tile rect again (S7), and
restoring. Results are written to `snap-receipts.json` beside the compositor log.

Phase 1 adds 11 checks (34 in all) with three GTK 4 windows: snapping a half
offers Snap Assist in the empty half; arrows move the selection; Escape closes
it; clicking a thumbnail snaps that window there and forms a two-member snap
group; dragging the shared edge 200 px resizes both members (the probe's
`split-press X Y` starts the same grab a border resize does); maximize and
restore keep the group and its split; un-snapping one member dissolves the group
and returns the other to its half; snapping beside an existing tile groups at
once. Probe additions: `focus N` (Nth window by creation), `assist
next|prev|choose|dismiss`, `assist-click X Y`, `assist-status`.

Not covered: X11 drag-out, multiple outputs (S3 is covered by unit tests only),
panels/dock work areas, the ack timeout path and native input.

`receipts/2026-10-21/` keeps the passing run (23/23) of the phase-0 branch:
`snap-receipts.json` and the compositor's `snap probe` lines. The 14
`pending=true` lines are placements waiting for the client's ack (S4): the
window keeps its old geometry until the acked commit.

`receipts/2026-10-21-phase1/` keeps the 34/34 run of the phase-1 branch with a
screenshot of Snap Assist (`snap-assist.png`).
