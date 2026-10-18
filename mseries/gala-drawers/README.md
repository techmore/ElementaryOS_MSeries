# Gala hotkey drawers

One global shortcut per slot that pops a set of apps **up or down** and snaps
them into a fixed zone of a monitor — a generic, Pantheon-native take on the
Quake-style drop-down terminal. A terminal in the top 40% of the laptop panel,
notes on the right third of an external display, or a *series* (a terminal and an
editor) that comes in side by side and leaves together, each on its own hotkey.

A slot can be filled three ways: press **Assign** with the app focused, pick apps
in **Drawer Shortcuts**, or edit the INI. This is a Gala plugin, installed by
`mseries/install-gala-drawers.sh`.

## Why this has to be a plugin

The usual drop-down/scratchpad tools do not work on Pantheon:

| Approach | Why it fails here |
| --- | --- |
| Guake, Tilda, Yakuake, Tilix quake, `tdrop`, `wmctrl`/`xdotool` scripts | X11 window tools. Gala runs a Wayland session; native Wayland windows are unreachable, and Gala will not place them. |
| GNOME Shell extensions (gTile, *Quake Terminal*, *Drop Down Terminal*) | Gala is not GNOME Shell; extensions cannot load. |
| gtk-layer-shell / wlr-layer-shell apps | Gala does not implement `wlr-layer-shell`; elementary ships its own `pantheon-desktop-shell` protocol. |

Gala's D-Bus surface at `/org/gnome/Shell` is only `GrabAccelerator(s)`,
`UngrabAccelerator(s)`, `ShowOSD`, and the `AcceleratorActivated` signal — there
is no method to move, resize, or toggle a window. The compositor is therefore the
only place that can both grab a global hotkey *and* place an arbitrary window.

Related prior art: `svandragt/gala-xy` does PaperWM-style tiling as a Gala plugin
with a Switchboard pane; this plugin covers the complementary "one slot, one
hotkey, one zone" case.

## How it works

* `Main.vala` is a `Gala.Plugin`. On `initialize` it reads
  `~/.config/mseries/gala-drawers.ini`, and for each configured slot binds two
  accelerators: `drawer-N` (toggle) and `assign-N` (capture the focused window).
* **Toggle** finds each slot app's window with `Meta.Display.list_all_windows()`
  (by GTK application id or WM class), then:
  * if the drawer is focused and up, `Meta.Window.minimize()` (down);
  * else `Meta.Window.unminimize()`, `move_resize_frame()` into the zone,
    `activate()`, `raise()` (up);
  * if no window matches, it launches `command` via its desktop entry.
* **Assign** takes the focused window, works out its app id / WM class and the
  matching desktop entry, writes it to the INI, reloads, and confirms on screen
  with Gala's OSD. That is the "open the app, then assign it" flow.
* The plugin watches the config directory. Saving the INI — by hand or from the
  settings app — **reloads and rebinds live**, no Gala restart.
* Zones are fractions of the target monitor's geometry, so they follow the
  monitor's resolution and scale.

Hotkeys live in a gsettings schema (mutter requires keybindings to be declared in
one); the apps, matches and zones live in a plain INI file.

## Configuration

`~/.config/mseries/gala-drawers.ini`, groups `drawer-1` .. `drawer-9`:

```ini
# Quake-style terminal: full width, top 40%.
[drawer-1]
command=io.elementary.terminal
match=io.elementary.terminal
monitor=-1                 ; -1 or omitted = primary monitor
zone=0.0 0.0 1.0 0.4       ; x y w h, fractions of the monitor

# A series: terminal and editor come in side by side.
[drawer-3]
command=io.elementary.terminal; io.elementary.code
match=io.elementary.terminal; io.elementary.code
zone=0.0 0.5 0.5 0.5  0.5 0.5 0.5 0.5
```

`command` and `match` are `;`-separated lists (a "series"); `match` defaults to
`command`. `zone` is one zone for the whole slot, or one zone per app (in the
same order) to lay a series out side by side. `monitor` is 0-based, or `-1` for
the primary.

Hotkeys, in `org.pantheon.gala.plugins.drawers` (defaults below — left Command is
Control on the M-series keyboard):

```sh
gsettings set org.pantheon.gala.plugins.drawers drawer-1 "['<Control><Alt>1']"        # toggle
gsettings set org.pantheon.gala.plugins.drawers assign-1 "['<Control><Alt><Shift>1']" # capture
gsettings set org.pantheon.gala.plugins.drawers drawer-2 "[]"                         # clear
```

`Command+number` is left free on purpose: it switches tabs inside apps, and a
drawer grab at the Gala level would swallow it before the app ever saw the key.

## Drawer Shortcuts

`mseries-drawers-settings` ("Drawer Shortcuts" in the app grid) lists the nine
slots. For each you can capture the toggle and assign shortcuts, choose the apps
(or a series), set the zone and monitor, or clear it. It writes the same INI and
gsettings, so the plugin picks the change up immediately.

## Build and install

```sh
bash mseries/install-gala-drawers.sh            # build + install into the running Gala
bash mseries/install-gala-drawers.sh --revert   # remove plugin, schema, settings app
```

The installer builds against the installed `gala` and needs Gala's vendored
mutter/clutter vapi files, which upstream ships in its source tree rather than
installing. It clones the pinned `elementary/gala` commit to get them (pass
`--vapidir DIR` to reuse an existing checkout, e.g. the one
`install-gala-screen-corners.sh` builds).

It installs the schema system-wide, compiles it, drops the `.so` into the running
compositor's plugin directory, installs the settings app per-user, and applies the
default accelerators. On this machine the patched Gala under
`/usr/local/lib/mseries/gala` is detected automatically; otherwise the stock
`libdir/gala/plugins` is used.

**The plugin takes effect at the next Gala start** (log out and back in). Gala's
`PluginManager` is supposed to load new `.so` files at runtime, but gala 8.6.2
does not retain the `FileMonitor` it creates
(`src/Misc/PluginManager.vala`: the monitor is unreferenced and finalized), so the
watch is dropped. A one-line fix that stores the monitor would restore live
loading; that means rebuilding the patched Gala.

## Status and risks

* Verified: the plugin compiles and links against gala 8.6.2 / mutter 50.1 and
  exports `register_plugin`; the schema compiles and resolves; the settings app
  passes a syntax check. The plugin is installed into the running patched Gala's
  plugin directory, and the startup enumeration loads plugins from there
  (confirmed via `libgala-pip.so`).
* Found while testing: gala 8.6.2 drops its plugin-directory watch
  (`PluginManager` does not retain the `FileMonitor`), so a newly installed plugin
  is not hot-loaded — it loads at the next Gala start.
* Fixed: `zone` used to be read with `get_double_list`, which splits on `;`, so
  the space-separated zones in the example never parsed. Zones now accept spaces.
* Not yet verified live: window placement and show/hide behaviour, multi-monitor
  zones, the assign/OSD flow, live reload, and the launch-then-place path (a
  freshly launched app appears wherever Gala puts it; press the hotkey again to
  snap it).
* Wayland hide semantics: "down" uses `minimize()`. There is no true
  hide-and-keep-in-place on Wayland, so a drawer reappears through normal window
  activation, not only through its hotkey.
* Pinned to gala 8.6.2 (mutter 18). A Gala or mutter bump may need a `meson.build`
  tweak, like the screen-corners patch.
