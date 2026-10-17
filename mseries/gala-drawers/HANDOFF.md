# Gala hotkey drawers — resume note (2026-10-16, DeepSeek/OpenCode)

Written for the next session that picks this up. Everything below is the state at
the time of writing; the only thing outstanding is a live test that needs the
owner to log out and back in.

## Update — 2026-10-16 (later session): assign, OSD, live reload, settings app

The plugin was extended from "one app, one hotkey, one zone" to fill three gaps
the owner asked for, and a settings app was added. All committed together.

- **Assign with feedback.** New schema keys `assign-1` .. `assign-9` (default
  `<Control><Alt>N`). Pressing one captures the focused window: works out its GTK
  app id / WM class and matching desktop entry, writes it into the INI, reloads,
  and confirms with Gala's OSD (`ShowOSD` at `/org/gnome/Shell`). This is the
  "open the app, then assign it" flow.
- **Live reload.** The plugin now watches the config *directory*
  (`Gio.FileMonitor`, debounced) and reloads + rebinds on save, so no Gala restart
  is needed to change apps or zones. (The `.so` itself still loads only at the
  next Gala start.)
- **Series + per-app zones.** `command` and `match` accept `;`-separated lists; a
  `zone` with 4 numbers is shared, one with 4×N numbers is per app, so a series
  can sit side by side.
- **Settings app.** `mseries-drawers-settings` ("Drawer Shortcuts"), a GTK4 app
  installed per-user by the installer, to capture shortcuts, choose apps, set
  zones/monitors, and clear slots. It writes the same INI + gsettings.
- **Zone parsing bug fixed.** `zone` was read with `get_double_list`, which splits
  on `;`, so the space-separated zones in the example silently never parsed. It
  now splits on spaces/commas/semicolons.
- **Defaults.** The installer resets `drawer-N`/`assign-N` so the schema defaults
  apply: left Command (Control) + N toggles, Control+Alt+N assigns.

Verified: plugin builds and links (gala 8.6.2 / mutter 18); schema compiles
under `--strict`; settings app passes `py_compile`; installer passes `bash -n`.
Still not verified live (needs the owner's relogin).

## Phase 2 (planned, not started): dock integration

The owner wants the *assignment UI* to live on the elementary dock, in a forked
`io.elementary.dock` (tag 8.3.3, matching the installed `8.3.3+r896`), the same
way `install-gala-screen-corners.sh` forks Gala:

1. **Chevron → slots.** A chevron on the dock opens a strip of drop targets;
   dragging a dock app onto a slot assigns that app (writes the drawer's INI).
   Defaults to **5** slots with an expando (chevron / Down on the d-pad / click)
   to reveal the remaining 4.
2. **Command+left-drag to move the dock.** A Ctrl-gated drag on the dock to
   reposition it.

Why it must be inside the dock: the dock's drag payload is an internal
`BaseItem` GObject (`src/BaseItem.vala` `on_drag_prepare` →
`Gdk.ContentProvider.for_value`), so a separate process cannot receive a dock
drag; the chevron and slots have to be in the dock. The dock is bottom-anchored
(`MainWindow` `panel.set_anchor (BOTTOM)`), so "move" means a position/offset
model. Packaging follows the Gala pattern: clone the tag, patch, build, install
under a prefix, and launch with a fallback so a bad dock cannot strand the
session. No plugin change is needed — the dock writes the same INI the plugin
already watches live.

### Dock status (this session)

- **Chevron + slots: implemented and compiling.** `mseries/patches/dock-drawers.patch`
  adds `src/Drawers.vala` (a `DrawersChevron` holding a `Gtk.MenuButton` popover of
  `DrawerSlot` drop targets — 5 shown, an arrow reveals the other 4), appends the
  chevron to `ItemManager`, and adds CSS. It builds clean against dock 8.3.3
  (`ninja -C build`). Not run live.
  * Gotcha: GTK4 `GtkMenuButton` is opaque, so Vala cannot subclass it — the
    chevron *contains* one instead (a subclass fails with "incomplete type").
- **Install:** `mseries/install-dock-drawers.sh` — private build under
  `~/.local/lib/mseries/dock`, plus a wrapper at `~/.local/bin/io.elementary.dock`
  with a stock fallback. **Installed** this session (binary links cleanly, wrapper
  is in the session PATH ahead of /usr/bin); takes effect at the next login.
- **Launch mechanism:** gnome-session starts the dock by name from
  `/etc/xdg/io.elementary.desktop.wm.shell` (`[io.elementary.dock] args=io.elementary.dock`),
  and `~/.local/bin` precedes `/usr/bin` in the session PATH — which is why the
  per-user PATH wrapper is the clean override seam.
- **Move-the-dock: protocol extended (owner chose free slide).** `pantheon-desktop-shell.v1`
  only exposed `set_anchor`/`set_size`, with no offset, so a panel could not slide
  along its edge. Added `io_elementary_pantheon_panel_v1.set_offset (int)` at
  protocol version 2 in **both** forks:
  * Gala (`mseries/patches/gala-panel-offset.patch`): the XML/vapi bump the shell
    and panel interfaces to 2, `PantheonShell` handles it, `ShellClientsManager`
    forwards it, and `PanelWindow` applies it to the centred `x` (and repositions).
    `install-gala-screen-corners.sh` now applies this patch too and builds the
    combined Gala. **Reinstalled** this session (`set_offset` present in the
    installed binary; the drawers plugins survive the install); next login.
  * Dock (`dock-drawers.patch`): binds the shell at version 2 and adds a
    Command (Control) + left-drag `GestureDrag` that calls `set_offset`, guarded by
    `panel.get_version () >= 2` so an older Gala stays centred instead of erroring.
  * Caveat: the offset is **in-memory** — it resets to centred when the dock
    restarts. Persisting it needs a settings key (the dock's schema is system-wide).




## Goal

Owner wanted "hotkeys for popup/pop-down for different apps that snap into
certain places" on elementary OS / Pantheon (this machine: M1 Pro, Wayland,
patched Gala). Chosen direction (owner picked it): a **Gala plugin** — the only
layer that can both grab a global hotkey and place an arbitrary window on
Pantheon, because Gala is a Wayland compositor that is not GNOME Shell, does not
implement `wlr-layer-shell`, and exposes no D-Bus method to move/resize a window.

## Status: installed, awaiting the owner's logout/in

Owner chose to log out and back in themselves (not a compositor restart) to test.
Do not restart Gala for them. Nothing else is pending on my side.

Installed and verified on the running system:

| Item | Location |
| --- | --- |
| Plugin `.so` | `/usr/local/lib/mseries/gala/lib/gala/plugins/libgala-drawers.so` |
| Schema | `/usr/share/glib-2.0/schemas/org.pantheon.gala.plugins.drawers.gschema.xml` (compiled) |
| Config | `~/.config/mseries/gala-drawers.ini` (seeded from the example) |
| Hotkey | `gsettings get org.pantheon.gala.plugins.drawers drawer-1` -> `['<Control><Alt>t']` |

The running Gala at the time was the **patched** one
(`/usr/local/lib/mseries/gala/bin/gala`, mutter 50.1, plugindir as above), which
is detected automatically by the installer.

## Repo artifacts

- `mseries/gala-drawers/Main.vala` — the plugin (`Gala.Plugin`).
- `mseries/gala-drawers/org.pantheon.gala.plugins.drawers.gschema.xml` — hotkeys
  `drawer-1` .. `drawer-9` (type `as`).
- `mseries/gala-drawers/drawers.ini.example` — app + zone config.
- `mseries/gala-drawers/meson.build`, `meson_options.txt` — build.
- `mseries/gala-drawers/README.md` — feature/design/usage.
- `mseries/install-gala-drawers.sh` — build + install + `--revert`.
- `mseries/post-install.sh` — new opt-in stage `drawers` (default `off`).
- `.gitignore` — ignores `mseries/gala-drawers/build/`.

Nothing is committed yet. The repo also has unrelated in-flight changes
(`validate-mseries.yml`, `KVM-VMS.md`, `vms/`, `rust/`) — stage only the drawer
files if committing.

## How it works (short)

On `initialize` the plugin reads `~/.config/mseries/gala-drawers.ini` and, per
configured drawer, calls `Meta.Display.add_keybinding ("drawer-N", schema, ...)`.
On the hotkey it finds the window via `Meta.Display.list_all_windows()` (match on
GTK app id or WM class), then: focused+up -> `minimize()`; else `unminimize()` +
`move_resize_frame()` into the zone + `activate()` + `raise()`; no window ->
launch `command`. Zones are fractions of the target monitor geometry.

## Resume checklist (after the owner is back)

1. Confirm the plugin loaded:
   ```sh
   pid=$(pgrep -x gala | head -1)
   grep -q libgala-drawers /proc/$pid/maps && echo LOADED || echo "not loaded"
   journalctl --user -u io.elementary.gala@wayland.service -b | grep drawers
   ```
   Expect `LOADED` and a `drawers: N drawer(s) bound` line (N = configured
   drawers, currently 2: `drawer-1` terminal, `drawer-2` tasks).
2. Owner presses **Command+Option+T** (physical Ctrl+Alt+T): terminal should pop
   into the top 40% of the built-in panel; a second press minimizes it.
3. If the hotkey does nothing, it may be grabbed by something else. Change it
   live (mutter follows the schema key without a restart):
   `gsettings set org.pantheon.gala.plugins.drawers drawer-1 "['<Control><Alt>grave']"`.
   Only the INI needs a Gala restart to reload.
4. Tune the zone: edit `~/.config/mseries/gala-drawers.ini` (currently
   `zone=0.0 0.0 1.0 0.4`) and restart Gala to reload.

## Finding worth keeping: live plugin loading is broken in gala 8.6.2

`src/Misc/PluginManager.vala` does:

```vala
plugin_dir.monitor_directory (FileMonitorFlags.NONE, null).changed.connect (...);
```

The `FileMonitor` is never stored, so it is finalized immediately and the watch
is dropped. Confirmed empirically: the running Gala has one inotify fd with no
watch on the plugin directory inode. Consequence: **a newly installed plugin is
not hot-loaded; it loads only at the next Gala start.** Startup enumeration does
work (verified: `libgala-pip.so` is mapped into the running Gala), so the plugin
will load at next login. A one-line fix (retain the monitor) would restore live
loading but requires rebuilding the patched Gala (see
`install-gala-screen-corners.sh`).

Do **not** claim "no logout needed" in docs/scripts — already corrected in
`install-gala-drawers.sh` and the README to say it takes effect at next Gala start.

## Build gotchas

- Gala's `libmutter-*/mutter-clutter-*` vapi files are **not installed**; they
  live in a Gala source checkout's `vapi/` directory. The installer clones the
  pinned `elementary/gala` commit (`f0791434`, gala 8.6.2) to get them; pass
  `--vapidir DIR` to reuse an existing checkout. Building needs `--pkg
  mutter-clutter-18 --pkg mutter-cogl-18 --pkg mutter-mtk-18` and `gio-unix-2.0`.
- Local compile smoke test (does not install):
  `valac -C --pkg gala --pkg gee-0.8 --pkg gio-unix-2.0
  --vapidir=<gala-src>/vapi --pkg mutter-clutter-18 --pkg mutter-cogl-18
  --pkg mutter-mtk-18 Main.vala`
- Safety: the `mseries-gala` launcher falls back to stock Gala if the patched one
  dies within 15 s, so a bad plugin cannot strand the session.

## Repo / branch state at time of writing

- The working tree is on branch **`apps-group`** (`bfe7dee`).
- While this note was being written, the owner's own parallel work was committed
  at `2026-10-16 22:49:56` as **`6e97ab6`** on branch
  **`vm-toolkit-desktop-fixes`** ("vms: mseries-vm toolkit plus window corners,
  mouse and chime fixes"), and the tree was briefly checked out to that branch and
  back. That commit added the "VM toolkit, window corners, mouse and chime fixes"
  entry to `OS9-HANDOFF.md` (`+29`), which is why the top of that file can look
  different depending on the branch.
- My `OS9-HANDOFF.md` entry (the "Hotkey drawers" section) was added on
  `apps-group`. Nothing was lost; the VM toolkit entry is safe in `6e97ab6`.
- Untracked and therefore present on every branch: the whole
  `mseries/gala-drawers/` directory and `mseries/install-gala-drawers.sh`.
  Committed files I changed: `.gitignore`, `mseries/post-install.sh`,
  `mseries/OS9-HANDOFF.md` (all uncommitted, on `apps-group`).

## Open items / candidates

- Live verification of placement, show/hide, multi-monitor zones (blocked on the
  owner's relogin).
- Launch-then-place: hook `Meta.Display.window_created` so a freshly launched app
  is snapped on first appearance (today you press the hotkey again).
- Optional: a Switchboard settings pane (like `gala-xy`'s Tiling pane) instead of
  the INI file.
- Optional: the `PluginManager` FileMonitor fix, to make future plugin installs
  live-load.
- Commit the drawer files (not the unrelated in-flight changes).
