# Rust Pantheon brightness bridge candidate

This crate implements the session-bus name `org.gnome.Shell.Brightness` and
the existing `SetDimming`, `SetAutoBrightnessTarget`, `HasBrightnessControl`,
and `BrightnessChanged` contract. It reads Mutter's `Backlight` property and
uses `SetBacklight` for the active `eDP-*` panel, with the existing power
GSettings keys for idle dimming and automatic brightness.

The Rust service is not installed. `mseries/brightness/shell-bridge.py`
remains the runtime implementation until the exported service passes the
private-bus fake-Mutter fixture, same-host behavior review, and arm64 image
admission. The fixture checks dim/restore, preserving manual changes,
`BrightnessChanged`, automatic-target mapping/validation, and GSettings gates.
The macOS build used for this candidate cannot start its packaged session bus:
its `dbus-daemon` requires a launchd socket, and the sandbox blocks binding a
private Unix socket. The arm64 CI job now runs this fixture under
`dbus-run-session`; that CI result is still pending.

The implementation links to the system GIO library through `pkg-config`; the
Apple Silicon mkosi build already installs GTK development packages, and the
Rust candidate CI installs `libglib2.0-dev` and `pkg-config` explicitly.

```sh
cargo fmt --check --manifest-path mseries/rust/brightness-bridge/Cargo.toml
cargo test --locked --manifest-path mseries/rust/brightness-bridge/Cargo.toml
cargo clippy --locked --manifest-path mseries/rust/brightness-bridge/Cargo.toml --all-targets -- -D warnings
cargo build --locked --release --manifest-path mseries/rust/brightness-bridge/Cargo.toml
python3 mseries/rust/brightness-bridge/test-dbus-runtime.py \
  mseries/rust/brightness-bridge/target/release/mseries-brightness-bridge-rs
```

The unit tests cover saved brightness restoration, preserving manual changes,
settings gates, valid/invalid ambient targets, and changes received during a
dim cycle. The private-bus integration fixture exercises the exported D-Bus
object through GIO and a Mutter-shaped fake service; it does not qualify the
bridge on a live elementary desktop.
