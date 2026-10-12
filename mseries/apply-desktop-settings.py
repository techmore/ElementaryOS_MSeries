#!/usr/bin/python3
"""Apply the M1 Pro owner's Command shortcuts and brightness-key helper."""
from pathlib import Path
import shutil
import subprocess
from gi.repository import Gio

repo = Path(__file__).resolve().parents[1]
home = Path.home()
settings = Gio.Settings.new("org.gnome.desktop.input-sources")
options = settings.get_strv("xkb-options")
if "ctrl:swap_lwin_lctl" not in options:
    settings.set_strv("xkb-options", options + ["ctrl:swap_lwin_lctl"])
Gio.Settings.sync()
Gio.Settings.new("org.gnome.desktop.wm.preferences").set_string("button-layout", "close:minimize,maximize")
Gio.Settings.sync()
helper = home / ".local/libexec/mseries-brightness"
helper.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(repo / "mkosi.images/apple-silicon/mkosi.extra/usr/libexec/mseries-brightness", helper)
helper.chmod(0o755)
autostart = home / ".config/autostart/mseries-brightness.desktop"
autostart.parent.mkdir(parents=True, exist_ok=True)
autostart.write_text("[Desktop Entry]\nType=Application\nName=M-series brightness keys\n"
    f'Exec="{helper}"\nOnlyShowIn=Pantheon;\nNoDisplay=true\n')
print("Command acts as Ctrl; physical left Ctrl acts as Super. Brightness keys start at next login.")
print(f"To start now: {helper}")
