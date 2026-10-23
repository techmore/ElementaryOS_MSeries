#!/usr/bin/python3
"""Keep the Command+Space launcher shortcuts registered.

gsd-media-keys only loads custom shortcuts listed in `custom-keybindings`, and that
list was found emptied after a reboot while the per-shortcut entries survived. Run with
--once to bind and exit; with no argument, bind and re-bind whenever the list changes.
"""
import sys
from pathlib import Path
from gi.repository import Gio, GLib

MEDIA = "org.gnome.settings-daemon.plugins.media-keys"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
LAUNCHER = str(Path.home() / ".local/bin/mseries-launcher")
# Both Command keys are Ctrl (ctrl:swap_lwin_lctl + ctrl:swap_rwin_rctl); Super+Space
# remains available from either physical Ctrl key.
SHORTCUTS = [("mseries-launcher0", "<Control>space"), ("mseries-launcher1", "<Super>space")]


def bind():
    keys = Gio.Settings.new("io.elementary.desktop.wm.keybindings")
    for action in ("switch-input-source", "switch-input-source-backward"):
        current = keys.get_strv(action)
        wanted = [b for b in current if b.lower() != "<super>space"]
        if wanted != current:
            keys.set_strv(action, wanted)
    paths = []
    for name, binding in SHORTCUTS:
        path = f"{BASE}{name}/"
        custom = Gio.Settings.new_with_path(f"{MEDIA}.custom-keybinding", path)
        for key, value in (("name", "M-series launcher"), ("command", LAUNCHER), ("binding", binding)):
            if custom.get_string(key) != value:
                custom.set_string(key, value)
        paths.append(path)
    shortcuts = Gio.Settings.new(MEDIA)
    existing = shortcuts.get_strv("custom-keybindings")
    missing = [p for p in paths if p not in existing]
    if missing:
        shortcuts.set_strv("custom-keybindings", existing + missing)
    Gio.Settings.sync()


bind()
if "--once" not in sys.argv:
    watched = Gio.Settings.new(MEDIA)
    watched.connect("changed::custom-keybindings", lambda *_: GLib.idle_add(bind))
    GLib.MainLoop().run()
