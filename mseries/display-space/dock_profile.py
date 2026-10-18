#!/usr/bin/python3
"""Apply or restore the compact native dock settings, preserving launchers."""
import argparse
import json
import os
from pathlib import Path
from gi.repository import Gio, GLib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revert', action='store_true')
args = parser.parse_args()
state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'mseries-desktop-space'
backup = state / 'dock-settings.json'
settings = Gio.Settings.new('io.elementary.dock')
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
    settings.set_int('icon-size', 40)
    settings.set_string('autohide-mode', 'overlapping-window')
    Gio.Settings.sync()
print('Restored dock settings.' if args.revert else 'Dock: 40 px icons; hide when any window overlaps; pinned apps preserved.')
