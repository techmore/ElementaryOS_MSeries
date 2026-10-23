# Native screenshot workflow qualification

Build the compositor, then run the private-display workflow:

```sh
cargo build --release --locked --manifest-path rust/Cargo.toml \
  -p pantheon-compositor --bin pantheon-compositor --features native-drm
SCREENSHOT_TEST_BIN=/absolute/path/to/release/pantheon-compositor \
SCREENSHOT_TEST_SHELF=/absolute/path/to/mseries-screenshot-shelf \
  bash mseries/pantheon-rust-compositor/screenshot-tests/run.sh
```

Use Cargo metadata's `target_directory` to locate the binary; global Cargo
configuration may place it outside this repository. The shelf argument is optional;
without it the capture checks run but shelf appearance/expiry is not checked.
Set `SCREENSHOT_TEST_SOUND_FALLBACK=1` to make the canberra stub fail and exercise
the PipeWire playback fallback. Both players are stubbed: this verifies requests,
not audible playback.

Dependencies: Xvfb, xauth, xdotool, D-Bus, system Python GTK4/Cairo bindings and
Pillow. Optional ffmpeg retains a view of the shelf and enables the corresponding
active-window check. The script creates private HOME/XDG directories, a D-Bus
session with service activation disabled and a private X11 display. It retains
the receipt directory printed at startup, including synthetic PNGs and logs.
It never targets the owner's display or phone. Child processes stop on exit.

The test covers full-screen Super+Shift+3, decoded color/orientation checks,
Super+Shift+4 region drag, hovered-window Space capture, Escape cancellation,
PNG permissions, sound requests, and optionally real shelf display, preserved
app active state, expiry and original retention. The shelf must be the reviewed
retention-safe version. Cropping is checked at one nested output and scale.

This does not qualify native DRM readback, rotated/multiple outputs, fractional
output scale, audible sound, actual Signal compose attachments, or lock/grab
interruptions. Session-lock handling cancels capture selection and pending
requests, but requires an integration test. Installing a package leaves the
running compositor unchanged; loading the new binary requires the next login.
