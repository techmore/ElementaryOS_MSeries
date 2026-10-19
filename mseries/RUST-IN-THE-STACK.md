# Rust in the M-series desktop stack (2026-10-18)

Claude, checked on the owner's j314s (elementary OS 9 Early Access on Ubuntu 26.04 "resolute",
kernel `7.1.12-2-20261017.20-sep-ARCH`). "Rust" means the installed binary contains Rust runtime
panic paths or reports a Rust implementation; kernel items from `/proc/config.gz`.

## The graphics stack, bottom to top

```
Apps                 GTK4 + Granite (C / Vala)            librsvg (Rust), glycin (Rust) inside GTK
Compositor / shell   Gala, Wingpanel, Dock (Vala)         GNOME Shell (JS) in the Ubuntu session
Engine               libmutter + Clutter + Cogl (C)       today's crash: mseries/PANTHEON-CRASH-2026-10-18.md
GPU userspace        Mesa Asahi driver (C)                Mesa's rusticl is Rust, not used by the desktop
Kernel               drm/asahi GPU driver (RUST)          apple-dcp display driver (C), G3 blocker lives here
```

## Already Rust here

| Layer | Component | Evidence | Benefit |
|---|---|---|---|
| Kernel | Asahi AGX GPU driver | `CONFIG_RUST=y`, `CONFIG_DRM_ASAHI=y` (built in) | Firmware-shared structures and object lifetimes checked by the type system; credited with fast, low-crash bring-up |
| Audio | `speakersafetyd` | Rust panic paths in `/usr/bin/speakersafetyd` | Safety-critical speaker thermal model in a long-running daemon |
| Toolkit | `librsvg` (all SVG/symbolic icons) | Rust panic paths in `librsvg-2.so.2` | Parses untrusted files; ported from C for memory safety |
| Toolkit | `glycin` (linked by `libgtk-4.so.1`) | `libglycin-2.so.0`, Rust panic paths | Sandboxed image loaders |
| System | `sudo-rs` 0.2.13, uutils coreutils 0.10.0 | `/usr/lib/cargo/bin/{sudo,coreutils}` | setuid-root memory safety; modern coreutils |

## Not Rust, and what that means for us

- `apple-dcp` (C): talks to display firmware through complex shared structures, the same shape of problem the
  Rust GPU driver solved well. Strongest Rust candidate in the stack, but kernel work belongs to DeepSeek and a
  rewrite would delay the dock HDMI goal (G3).
- `libmutter` (C): the 2026-10-18 crash was a read through a destroyed surface, a bug class Rust rejects at
  compile time. Fixed here by the upstream patch (`install-gala-mutter-fix.sh`), not by a rewrite.
- Gala, Wingpanel, Dock, Granite (Vala, compiled to C with reference counting): not where today's crash was.
- Mesa Asahi userspace, PipeWire, WirePlumber: C.

## Upstream Rust work for Pantheon or mutter

Searched 2026-10-18: no Rust branch in GNOME/vala, GNOME/mutter (only `wip/nielsdg/uncrustify`, a C
formatter), or elementary/gala, granite, wingpanel, dock. So there is nothing upstream to port from.
Rust compositors exist outside them: Smithay (library), cosmic-comp (System76 COSMIC), niri. GTK4 apps
can be written in Rust with gtk4-rs today.

**Our own effort:** branch `codex/rust-mutter-pantheon` ("Mutter-minimal viable Rust", Codex): a nested
Smithay/Winit compositor in `rust/pantheon-compositor` that already advertises the Pantheon desktop-shell
protocol v2 (panel anchor, size, hide mode, offset; maximize respects panel geometry). Scope and acceptance
list: `mseries/pantheon-rust-compositor/` on that branch. It is a nested prototype; Gala stays the production
session. The 2026-10-18 mutter crash (destroyed surface reached from popup close) is a good acceptance test
for it: closing a popup under the pointer must not touch a freed surface.

## Where Rust fits this project

Main already has a Rust workspace (`rust/`) with `mseries-power`; `rust/pantheon-compositor` is on the
compositor branch. Further daemon candidates: display profiles, docked-lid, dictation input. The compositor
replaces mutter only in qualified slices; Gala remains the session until on-device acceptance, and the
dock HDMI goal (G3) stays a kernel/DCP problem either way.
