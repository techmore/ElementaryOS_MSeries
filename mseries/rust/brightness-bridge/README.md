# Rust Pantheon brightness bridge candidate

This crate implements the session-bus name `org.gnome.Shell.Brightness` and
the existing `SetDimming`, `SetAutoBrightnessTarget`, `HasBrightnessControl`,
and `BrightnessChanged` contract. It reads Mutter's `Backlight` property and
uses `SetBacklight` for the active `eDP-*` panel, with the existing power
GSettings keys for idle dimming and automatic brightness.

The Rust service is not installed. `mseries/brightness/shell-bridge.py`
remains the runtime implementation until the C ABI D-Bus callbacks, settings
behavior, error names, Mutter serial handling, and live display behavior pass
same-host parity and arm64 image admission.

The implementation links to the system GIO library through `pkg-config`; the
Apple Silicon mkosi build already installs GTK development packages, and the
Rust candidate CI installs `libglib2.0-dev` and `pkg-config` explicitly.

```sh
cargo fmt --check --manifest-path mseries/rust/brightness-bridge/Cargo.toml
cargo test --locked --manifest-path mseries/rust/brightness-bridge/Cargo.toml
cargo clippy --locked --manifest-path mseries/rust/brightness-bridge/Cargo.toml --all-targets -- -D warnings
cargo build --locked --release --manifest-path mseries/rust/brightness-bridge/Cargo.toml
```

The unit tests cover saved brightness restoration, preserving manual changes,
settings gates, valid/invalid ambient targets, and changes received during a
dim cycle. They do not claim that a D-Bus object registered through the native
GIO ABI works on an elementary desktop.
