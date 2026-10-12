#!/usr/bin/python3
"""Apply the M1 Pro owner's Command shortcuts and brightness-key helper."""
from pathlib import Path
import shutil
import subprocess
from gi.repository import Gio, GLib

repo = Path(__file__).resolve().parents[1]
home = Path.home()
settings = Gio.Settings.new("org.gnome.desktop.input-sources")
options = settings.get_strv("xkb-options")
if "ctrl:swap_lwin_lctl" not in options:
    settings.set_strv("xkb-options", options + ["ctrl:swap_lwin_lctl"])
Gio.Settings.sync()
keys = Gio.Settings.new("io.elementary.desktop.wm.keybindings")
for action, binding in [("screenshot", "<Control><Shift>3"), ("area-screenshot", "<Control><Shift>4")]:
    existing = keys.get_strv(action)
    if binding not in existing:
        keys.set_strv(action, existing + [binding])
Gio.Settings.sync()
# Gala hardcodes Pictures/Screenshots; redirect only that folder, not Pictures.
pictures = Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) or home / "Pictures")
downloads = Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or home / "Downloads")
target = downloads / "Screenshots"
target.mkdir(parents=True, exist_ok=True)
pictures.mkdir(parents=True, exist_ok=True)
link = pictures / "Screenshots"
if not link.exists() and not link.is_symlink():
    link.symlink_to(target, target_is_directory=True)
elif link.resolve() != target.resolve():
    print(f"Existing screenshot folder preserved: {link}. Move it manually to redirect saves.")
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
