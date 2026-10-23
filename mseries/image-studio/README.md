# M-Series Image Studio

The app source lives in [`rust/mseries-image-studio`](../../rust/mseries-image-studio): a native GTK 4 + Granite 7 app built with `gtk4-rs`, `granite-rs`, and the repo's shared `mseries-pantheon-kit` SDK. The window uses a real GTK titlebar, Granite navigation and section labels, and the SDK's theme-neutral geometry, text-scaled spacing, and responsive sizing helpers. The SDK dependency is pinned to repository revision `e15f9272` while the shared crate is being integrated into `dev`.

Build and run it from the repository root:

```sh
CARGO_TARGET_DIR="$HOME/.cache/cargo-target" cargo build --manifest-path rust/Cargo.toml -p mseries-image-studio
"$HOME/.cache/cargo-target/debug/mseries-image-studio"
```

Run core and GTK interaction coverage:

```sh
CARGO_TARGET_DIR="$HOME/.cache/cargo-target" cargo test --manifest-path rust/Cargo.toml -p mseries-image-studio --lib
dbus-run-session -- env -u WAYLAND_DISPLAY CARGO_TARGET_DIR="$HOME/.cache/cargo-target" GDK_BACKEND=x11 GSETTINGS_BACKEND=memory GSK_RENDERER=cairo xvfb-run -a -s "-screen 0 1440x1000x24" cargo test --manifest-path rust/Cargo.toml -p mseries-image-studio --test render
dbus-run-session -- env -u WAYLAND_DISPLAY CARGO_TARGET_DIR="$HOME/.cache/cargo-target" M_SERIES_IMAGE_STUDIO_TEST_COMPACT=1 GDK_BACKEND=x11 GSETTINGS_BACKEND=memory GSK_RENDERER=cairo xvfb-run -a -s "-screen 0 1440x1000x24" cargo test --manifest-path rust/Cargo.toml -p mseries-image-studio --test render
```

The window opens on the adult streamer-series prompt from the requested test case. Three workflow presets seed repeatable recipes; settings and prompt-type decisions can be reviewed and restored from Library. Recipes store prompts, model/LoRA notes and weight, output size, batch, seed, and tags. PNG output metadata uses the same JSON recipe format.

The app currently has no qualified image runtime connected. Generation remains disabled until an engine/model/size tuple has a measured memory budget and is qualified on this device. It also never starts a model worker. Prompt help and prompt-type suggestions call only the already-running loopback assistant at `127.0.0.1:8766`, and pause while the 6 GiB desktop reserve is unmet.

On this host, 5.8 GiB was available at the latest check (below the desktop reserve), `mseries-ai-everyday.service` was failed, no local image/text endpoint was listening, and the model cache contained Qwen text weights but no diffusion model. The UI/data path has been tested; no AI image was generated. See [OS9 handoff](../OS9-HANDOFF.md) and [roadmap](../ROADMAP.md) for the runtime qualification blocker.

### Result inspection

Library image rows offer **View image** and **Use these settings**. Reuse creates an editable copy in Create. Sidecars optionally record `elapsed_seconds`, `peak_memory_mib`, and `settings_note`; missing measurements are shown as unknown. Hosted sample model/seed/sampler values are unavailable and cannot be reproduced exactly. Imported contact-sheet dimensions map to the available local size presets when reused. Progressive previews and actual inference benchmarks require a connected, qualified engine.
