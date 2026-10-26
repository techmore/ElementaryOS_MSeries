# M-series app SDK core and CLI

The core provides descriptions (`.msdk` and JSON), checker/discovery/schema,
typed rules, semantic inspection, acceptance scenarios and standalone Rust app
generation. GTK hosting is in `msdk-gtk`. API/release status and remaining
qualification gates: [SDK completion ledger](../../mseries/SDK-COMPLETION.md).

From `rust/`:

```sh
cargo run -p msdk -- templates
cargo run -p msdk -- new settings /tmp/my-settings --id com.example.MySettings --name 'My Settings'
cargo run -p msdk -- check /tmp/my-settings/app.ui.json
cargo run -p msdk -- gate /tmp/my-settings/app.ui.json /tmp/my-settings/app.gates.json
cargo run -p msdk -- gen /tmp/my-settings/app.ui.json /tmp/my-settings-app --sdk-root "$PWD"
cargo run --manifest-path /tmp/my-settings-app/Cargo.toml
```

Use new output directories: `new` and `gen` refuse existing destinations. Keep
the SDK checkout available; generated Cargo dependencies use its canonical local
paths. Generation creates an independent workspace so app builds do not resolve
the compositor/whole OS. The full OS workspace can still resolve unrelated Git
dependencies when building the CLI; use `mseries/sdk-tests/prepare.py` for the
isolated SDK workspace when those sources are unavailable.

The supported native build path requires Linux, Rust 2024, GTK 4.20+ development
headers, pkg-config, Wayland headers and wayland-scanner. Generation/core checks
also run without GTK. Actual supported runtime and target-host acceptance remain
qualification gates; the generator is not a native macOS GTK port.

`gen` emits a Cargo manifest, description, `src/lib.rs` (record structs, `State`,
`Message::into_event`, embedded document), `src/main.rs` (real GTK Host), initial
state round-trip test and app README. Number fields use `serde_json::Number` so
large integer measurements remain exact. Source names are preserved in serde
fields; Rust keywords/non-identifiers get collision-free Rust identifiers.
The executable supports `--screenshot output.png` for isolated render checks and
exits unsuccessfully if opening/rendering fails. Ordinary launches use the
stable application ID and reactivate the existing window.

Custom service manifests next to the source description are embedded and
registered by `app_model::document()`. They declare types, not implementations:
implement `Services` and switch to `Host::open_with` for those backends. For
custom Rust logic, use generated models plus an explicit `LogicFactory`;
project generation rejects missing custom logic instead of inventing behavior.
Generation does not call services, provision credentials or install artifacts.

After generation, `cargo fmt`, `cargo test --all-targets` and
`cargo clippy --all-targets -- -D warnings` check the standalone source. Changes
to the description's types require regenerating models in a new directory and
reviewing app-local changes. Views/rules stay inspectable in `app.ui.json`.

`msdk-run description --watch` is the separate interpreter preview loop.
`describe`, `complete`, `explain`, `schema` and `components` derive from the
checker vocabulary. `render` produces a semantic tree; `gate` runs headless
state/effect scenarios. Neither executes a real backend or proves live GTK
accessibility. `msdk pack`, `parity`, Studio and a live introspection registry
are not implemented commands.
