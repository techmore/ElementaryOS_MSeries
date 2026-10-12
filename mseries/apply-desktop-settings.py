#!/usr/bin/python3
"""Apply the M1 Pro owner's Command shortcuts, Command+Space launcher and brightness-key helper."""
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
# Command+Space launcher. mseries-launcher-keys binds <Control>space (Command is Ctrl here)
# and <Super>space (right Command), frees Super+Space from the input-source switch, and
# re-binds at every login because the shortcut list was once found emptied after a reboot.
launcher = home / ".local/bin/mseries-launcher"
launcher.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(repo / "mseries/mseries-launcher.py", launcher)
launcher.chmod(0o755)
keys_helper = home / ".local/libexec/mseries-launcher-keys"
keys_helper.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(repo / "mseries/mseries-launcher-keys.py", keys_helper)
keys_helper.chmod(0o755)
keys_autostart = home / ".config/autostart/mseries-launcher-keys.desktop"
keys_autostart.parent.mkdir(parents=True, exist_ok=True)
keys_autostart.write_text("[Desktop Entry]\nType=Application\nName=M-series launcher shortcuts\n"
    f'Exec="{keys_helper}"\nOnlyShowIn=Pantheon;\nNoDisplay=true\n')
subprocess.run([str(keys_helper), "--once"], check=True)
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
print("Command acts as Ctrl; physical left Ctrl acts as Super. Command+Space opens the launcher. Brightness keys start at next login.")
print(f"To start now: {helper}")
