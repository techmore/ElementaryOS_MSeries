#!/usr/bin/python3
"""Apply or restore the compact native dock settings, preserving launchers."""
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from gi.repository import Gio, GLib

# Compact floating-dock icon size at the default step (the size system's "work" token).
DEFAULT_ICON_SIZE = 40


def size_system_dock(mode, fallback):
    """Dock token from the M-Series size system (#332) once it is adopted, else the old literal."""
    tool = shutil.which('mseries-ui-scale') or str(Path.home() / '.local/bin/mseries-ui-scale')
    try:
        result = subprocess.run([tool, '--dock-size', mode], capture_output=True, text=True, timeout=5, check=False)
        return int(result.stdout) if result.returncode == 0 else fallback
    except (OSError, ValueError, subprocess.SubprocessError):
        return fallback


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revert', action='store_true')
args = parser.parse_args()
state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'mseries-desktop-space'
backup = state / 'dock-settings.json'
# The user dock extends the distro schema; use the same private schema as its launcher.
source = Gio.SettingsSchemaSource.get_default()
private = Path.home() / '.local/lib/mseries/dock/share/glib-2.0/schemas'
if (private / 'gschemas.compiled').exists():
    source = Gio.SettingsSchemaSource.new_from_directory(str(private), source, False)
schema = source.lookup('io.elementary.dock', True)
if schema is None:
    raise SystemExit('Dock settings schema is unavailable; nothing changed.')
settings = Gio.Settings.new_full(schema, None, None)
if args.revert:
    if backup.exists():
        for key, value in json.loads(backup.read_text()).items():
            if value is None:
                settings.reset(key)
            else:
                settings.set_value(key, GLib.Variant.parse(None, value, None, None))
        Gio.Settings.sync()
        backup.unlink()
else:
    state.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        saved = {key: value.print_(True) if (value := settings.get_user_value(key)) is not None else None
                 for key in ('icon-size', 'autohide-mode')}
        backup.write_text(json.dumps(saved, indent=2) + '\n')
    if schema.has_key('taskbar-mode') and settings.get_boolean('taskbar-mode'):
        # An update of the old floating-dock profile must not undo the owner's taskbar.
        print('Windows taskbar: existing size, visibility and pinned apps preserved.')
        raise SystemExit(0)
    icon_size = size_system_dock('work', DEFAULT_ICON_SIZE)
    settings.set_int('icon-size', icon_size)
    settings.set_string('autohide-mode', 'overlapping-window')
    Gio.Settings.sync()
print('Restored dock settings.' if args.revert else
      f'Dock: {icon_size} px icons; hide when any window overlaps; pinned apps preserved.')
