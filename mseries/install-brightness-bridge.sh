#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} == --uninstall ]]; then
  systemctl --user stop mseries-brightness-bridge.service
  rm -f "$HOME/.config/autostart/mseries-brightness-bridge.desktop" "$HOME/.config/systemd/user/mseries-brightness-bridge.service"
  /usr/bin/python3 - <<'PYTHON'
from pathlib import Path
import json
from gi.repository import Gio
path = Path.home() / '.local/state/mseries-brightness-bridge/preferences.json'
if path.exists():
    Gio.Settings.new('org.gnome.settings-daemon.plugins.power').set_boolean('ambient-enabled', json.loads(path.read_text())['ambient-enabled'])
    Gio.Settings.sync()
    path.unlink()
PYTHON
  systemctl --user daemon-reload
  exit
fi
install -Dm755 "$repo/mseries/brightness/shell-bridge.py" "$HOME/.local/libexec/mseries-brightness-bridge"
mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/autostart"
cat > "$HOME/.config/systemd/user/mseries-brightness-bridge.service" <<EOF
[Unit]
Description=Pantheon compatibility for GNOME brightness management
[Service]
ExecStart=/usr/bin/python3 "$HOME/.local/libexec/mseries-brightness-bridge"
Restart=on-failure
RestartSec=5
EOF
cat > "$HOME/.config/autostart/mseries-brightness-bridge.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Pantheon brightness compatibility
OnlyShowIn=Pantheon;
Exec=systemctl --user start mseries-brightness-bridge.service
NoDisplay=true
EOF
# Previously auto display brightness had no functional provider. Keep the owner's
# working manual level; the bridge also supports enabling ambient mode later.
/usr/bin/python3 - <<'PYTHON'
from pathlib import Path
import json
from gi.repository import Gio
path = Path.home() / '.local/state/mseries-brightness-bridge/preferences.json'
path.parent.mkdir(parents=True, exist_ok=True)
settings = Gio.Settings.new('org.gnome.settings-daemon.plugins.power')
if not path.exists():
    path.write_text(json.dumps({'ambient-enabled': settings.get_boolean('ambient-enabled')}))
    settings.set_boolean('ambient-enabled', False)
Gio.Settings.sync()
PYTHON
systemctl --user daemon-reload
systemctl --user restart mseries-brightness-bridge.service
echo 'Installed GNOME brightness compatibility. Manual screen brightness preserved.'
