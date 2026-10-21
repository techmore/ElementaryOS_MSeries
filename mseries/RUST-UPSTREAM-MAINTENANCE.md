# Rust and Pantheon upstreams: what we pull, what we patch, how to update

This machine runs a custom stack: elementary OS 9 Early Access on Ubuntu 26.04 "resolute", Asahi
kernels, a patched Gala, a private libmutter, and a growing Rust layer. Every piece below comes from
an upstream we must pull from to stay current. Keep this file updated whenever a pin moves.
Background: [`RUST-IN-THE-STACK.md`](RUST-IN-THE-STACK.md) (what is Rust today and why) and
[`PANTHEON-CRASH-2026-10-18.md`](PANTHEON-CRASH-2026-10-18.md) (why we patch mutter).

## Strategy (decided 2026-10-18)

- **Stay on upstream Vala for Pantheon apps.** Gala, Wingpanel, Dock and Granite stay upstream Vala code.
  No Vala-to-Rust translator exists; writing one would mean maintaining a compiler, and generated Rust
  would mirror GObject's shared mutable references inside `unsafe`, losing Rust's benefit.
- **New code in Rust, talking to Vala libraries through GObject Introspection (GIR).** Vala libraries can
  export GIR; gtk-rs generates safe Rust bindings from it.
- **Rewrite in Rust only with evidence** (a crash, a measured cost). The compositor qualifies (mutter is C
  and crashed); see `codex/rust-mutter-pantheon`.

## Upstream inventory

| Component | Upstream | Pinned / installed | Our changes | Where |
|---|---|---|---|---|
| mutter (libmutter) | Ubuntu source `mutter` on Launchpad; GNOME [mutter](https://gitlab.gnome.org/GNOME/mutter) | Ubuntu `50.1-0ubuntu2.4` | Upstream commit `c18af474` (null surface in cursor path), private `libmutter-18.so.0` for the patched Gala only | `install-gala-mutter-fix.sh`, `patches/mutter-surface-actor-null-cursor.patch`, `test-gala-mutter-fix.sh` |
| Gala | [elementary/gala](https://github.com/elementary/gala) | `f0791434ac40a50f2aec64700a47b3bb04145752` (gala 8.6.2+r3174) | Screen/window corners, panel offset (protocol v2), dock work area, screenshot patches | `install-gala-screen-corners.sh`, `patches/gala-*.patch` |
| Wingpanel | [elementary/wingpanel](https://github.com/elementary/wingpanel) | Installed `io.elementary.wingpanel 8.0.4+r814` (elementary daily); patch made against `e737de88bc02` | Export `Wingpanel-9.gir` + typelib (not installed yet) | `patches/wingpanel-export-gir.patch` |
| Granite | [elementary/granite](https://github.com/elementary/granite) | `libgranite-7` 7.8.1 (ships `Granite-7.0.gir`) | None | system package |
| granite-rs | [davidmhewitt/granite-rs](https://github.com/davidmhewitt/granite-rs) (crates.io `granite-rs`, `granite-rs-sys`) | `granite-rs 3.3.0`, `granite-rs-sys 0.9.0` | None; consumers must enable gtk4 `v4_10`+ (see below) | `rust/granite-smoke`, `rust/mseries-updates` (Software Updates app) |
| gtk4-rs / glib | [gtk-rs/gtk4-rs](https://github.com/gtk-rs/gtk4-rs), [gtk-rs/gtk-rs-core](https://github.com/gtk-rs/gtk-rs-core) | `gtk4 0.11.5` (feature `v4_20`), `glib 0.22.10`; system GTK 4.22.4 | None | `rust/Cargo.lock` |
| Smithay | [Smithay/smithay](https://github.com/Smithay/smithay) (`smallvil` example as base) | `023b78b1c5a05ca512767cacc07efca55fae8be4` | Pantheon desktop-shell v2 in a nested compositor | `rust/pantheon-compositor` on `codex/rust-mutter-pantheon` (Codex) |
| Pantheon desktop-shell protocol | XML from elementary/gala `f0791434` | v2 with our `set_offset` | `set_offset` extension | `gala-panel-offset.patch`; copy in the compositor branch |
| Vala | [GNOME/vala](https://gitlab.gnome.org/GNOME/vala) | system `valac` | None | n/a |

Upstream Rust branches checked 2026-10-18: none in GNOME/vala, GNOME/mutter (only `wip/nielsdg/uncrustify`,
a C formatter), elementary/gala, granite, wingpanel or dock.

## Update procedures

### mutter (after every Ubuntu mutter update)

The `mseries-gala` launcher stops using the private libmutter as soon as the system `libmutter-18-0`
version changes (it logs `patched libmutter is for …`). Then:

1. Check whether Ubuntu's new version already contains `c18af474`: search the Launchpad changelog for
   "Handle destroyed surfaces when updating cursor" or check
   `src/compositor/meta-surface-actor-wayland.c` for the `if (surface)` guard. If it does, run
   `bash mseries/install-gala-mutter-fix.sh --uninstall` and drop the patch.
2. Otherwise run `bash mseries/install-gala-mutter-fix.sh` (downloads the matching Ubuntu source, verifies the
   `.dsc` checksums, applies the patch, builds with `debian/rules` flags), then `bash mseries/test-gala-mutter-fix.sh`.
3. If Ubuntu adds build dependencies, the meson step fails with the missing program; add it to `need=()`.

### Gala

`install-gala-screen-corners.sh` pins `commit=`. To move: pick the elementary/gala commit matching the
installed `gala` package, update `commit=`, re-apply each `patches/gala-*.patch` (`git apply --check` first),
rebuild, run `window-snapping/test-nested.sh` and `test-gala-mutter-fix.sh`. Pantheon must be logged out and
in to pick it up.

### Wingpanel GIR

1. Clone elementary/wingpanel at the commit matching the installed `io.elementary.wingpanel` (elementary
   daily `rNNN` numbers do not equal `git rev-list --count`; match by date or ask the packaging repo).
2. `git apply mseries/patches/wingpanel-export-gir.patch`, `meson setup build`, `ninja -C build lib/Wingpanel-9.typelib`.
3. Check: `GI_TYPELIB_PATH=build/lib LD_LIBRARY_PATH=build/lib python3 -c "import gi; gi.require_version('Wingpanel','9'); from gi.repository import Wingpanel"`.
   Verified 2026-10-18: GIR has `Indicator`, `KeybindingHelper`, `PopoverMenuItem`; typelib loads.
4. Not yet installed system-wide or proposed upstream. Proposing it upstream is an outward action: owner decides.
   With it upstream, Rust indicators need no fork.

### granite-rs and gtk4-rs

- `granite-rs 3.3` does not turn on any gtk4 version feature, but `gtk4-rs 0.11` puts `gtk::Accessible` behind
  `v4_10`. Every crate using granite-rs here must set `gtk4 = { version = "0.11", features = ["v4_20"] }` and
  granite-rs features `["v7_8", "gtk_v4_20"]`, or granite-rs fails with `cannot find type Accessible in crate gtk`.
  Worth reporting upstream (owner decides).
- `granite::prelude::*` together with `gtk::prelude::*` makes `Box::append` ambiguous; import the specific
  Granite traits instead (for example `granite::prelude::PlaceholderExt`).
- To update: bump versions in `rust/granite-smoke/Cargo.toml`, `cargo update`, then
  `CARGO_TARGET_DIR=<scratch> cargo build -p granite-smoke` and run it under
  `dbus-run-session -- env -u WAYLAND_DISPLAY GDK_BACKEND=x11 GSETTINGS_BACKEND=memory xvfb-run -a <scratch>/debug/granite-smoke`.
  Expect `PASS: Granite widgets built from Rust …`. Match granite-rs `v7_N` to the installed Granite minor version.

### Smithay compositor

Owned by Codex on `codex/rust-mutter-pantheon`; its README keeps the pin and says to review any Smithay upgrade
explicitly. Do not commit to that branch from another agent.

## Repository caveats

- `rust/target/` (build output, about 377 files) is committed on main. Build with `CARGO_TARGET_DIR` outside the
  repo so those files do not churn; removing them from git is a separate cleanup.
- Packages installed on the owner's machine for the mutter build (2026-10-18): `libei-dev libsysprof-6-dev sysprof
  libcanberra-gtk3-dev libpam0g-dev libumockdev-dev python3-argcomplete python3-docutils patchelf`.

## Testing a Rust session end to end: the login entry

Nested and headless runs only prove pieces. To test the whole thing, the Rust compositor needs its own
**opt-in login session**: a `/usr/share/wayland-sessions/pantheon-rust.desktop` entry next to Pantheon and
Ubuntu in the LightDM session menu. It would start the compositor on DRM/KMS, then the unmodified Vala
Wingpanel, Dock and settings daemon. Rules for that step:

- Never the default or autologin session; Pantheon (`pantheon-wayland`) stays the default and rollback.
- A failure must return to the greeter, not a black screen (same `OnFailure` idea as Gala's unit).
- Prerequisites from the compositor branch: DRM/KMS backend, libinput, output configuration, lock screen.
- Acceptance follows `pantheon-rust-compositor/EXPERIENCE-REQUIREMENTS.md` (login, apps, panel/dock,
  monitor changes, snapping, lock/unlock, crash recovery) on the M1 Pro, with the owner present.
- Consumers: `rust/granite-smoke` (compile check) and `rust/mseries-updates` ([updates-app](updates-app/README.md): header labels,
  placeholder with an action button, toast). Both carry the same `gtk4 v4_20` / granite-rs `v7_8, gtk_v4_20` feature lines; update them together.
  Ubuntu 26.04's own `libgranite-7-dev` is 7.8.0, which is enough for `v7_8`, so CI needs no PPA for it.
- granite-rs 3.3 surprises met while writing the app: `granite::HeaderLabel` has no `set_label` (set the `label` property);
  `PlaceholderExt::append_button` takes a `gio::Icon` (not a `gtk::Image`) and returns the `gtk::Button` (it has no `action-activated`
  signal binding); a `gtk::Expander`'s collapsed child is not reachable by walking `first_child()`, so tests expand it first.
- Dark scheme in a test: Granite's stylesheet follows `gtk-application-prefer-dark-theme` (deprecated since GTK 4.20 but still honoured);
  `gtk-interface-color-scheme` did not switch it on 4.22.4.
