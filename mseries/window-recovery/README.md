# Window recovery without the dock

Run `mseries-restore-windows`, or choose **Restore Application Windows** in the
application menu. The chooser lists every application window, including minimized
ones; choosing a row uses Gala's `FocusWindow` interface to restore it on its
workspace. Cancel makes no focus request. There is no daemon, autostart, polling
or global keyboard grab. Titles are available after the updated compositor loads;
the chooser requires the focus-routing capability from the updated compositor.
It refuses to restore against an older running session with the known typing
routing bug. `--list` remains read-only and works with older sessions.

The compositor package installs the command and launcher. For a private install:

```sh
install -Dm755 mseries/window-recovery/restore-windows.py ~/.local/bin/mseries-restore-windows
install -Dm644 mseries/window-recovery/mseries-restore-windows.desktop ~/.local/share/applications/mseries-restore-windows.desktop
```

`--list` prints window metadata as JSON without changing focus. `--focus UID`
restores an explicitly selected existing window. This operates on minimized
windows; it does not resume stopped processes or system suspend.

## Isolated runtime regression

Build the debug compositor with `cargo build --manifest-path rust/Cargo.toml
-p pantheon-compositor --bins --features native-drm`, then run:

```sh
dbus-run-session -- python3 mseries/window-recovery/test-nested.py
```

The test creates private Xvfb, Wayland, D-Bus and GSettings contexts. Its pointer
and key events never target the real desktop. It checks XWayland half geometry,
minimize/restore, dock startup/repeated-activation focus preservation, actual text
entry after dock activation, and native Wayland snapping/recovery. Override the
dock executable with `MSERIES_SMOKE_DOCK=/path/to/io.elementary.dock` to test a
private patched build; its sibling installed schema directory is used. Requires
Xvfb, xdotool, Python GI/GTK4, and the installed stock or private dock.
