# Finger-following gesture qualification

The nested-only `gesture-probe` feature adds a Unix datagram socket under the
private `XDG_RUNTIME_DIR`. It drives the same swipe begin/update/end functions
as libinput; it is absent from normal builds and never installed by the package
builder. Native mode does not create this socket, even if the feature is enabled.

```sh
cargo build --manifest-path rust/Cargo.toml -p pantheon-compositor --features gesture-probe
GESTURE_TEST_BIN="$PWD/rust/target/debug/pantheon-compositor" \
GESTURE_TEST_OUT=/tmp/mseries-gesture-receipts GESTURE_TEST_RECORD=1 \
  bash mseries/pantheon-rust-compositor/gesture-tests/run-smoke.sh
```

Requires Xvfb/xvfb-run, dbus-run-session, FFmpeg (including libx264 for the optional
recording), Python GI GTK 4 and Pillow. The runner creates its own display,
D-Bus session, config/cache and runtime directory; settings use an in-memory
backend. GTK uses Cairo because this host's Vulkan path loses nested surfaces.

The runner asserts actual red/blue pixel bounds and compositor state after:

- Halfway workspace drag, release completion and cancellation back to origin.
- Rubber-banding at the first workspace (no wrap or workspace creation).
- Halfway overview opening, committed grid, cancelled close and committed close.
- Interrupting a release spring before it can commit.
- Release with `enable-animations=false` (immediate commit, no settling preview).

`receipts/2026-10-20/` retains the passing pixel measurements, state log, selected
screenshots and an overview opening/closing recording. These were captured from
the implementation after the `dev` merge at `e77f5c4`; subsequent lint-only edits
preserve behavior. The figures contain fixture windows and the existing desktop
wallpaper. Tests assert that cancellation and closing restore the original
rendered bounds. Math tests additionally cover flick velocity, reversal, stale
velocity, resistance, exact spring endpoints and aspect-preserving grid cells.

This proves the nested render and state path, not native input or performance.
Physical trackpad sensitivity, native frame pacing, multiple outputs, mixed
Wayland/XWayland preview windows and lock/grab interruption on hardware remain
unqualified. A drag of 360 libinput logical units spans one output; axis locking
starts after 8 units. These constants still need physical M-series tuning.
The settled overview still configures clients into the grid; only gesture
previews avoid reconfiguring them, and client minimum sizes can affect endpoints.
