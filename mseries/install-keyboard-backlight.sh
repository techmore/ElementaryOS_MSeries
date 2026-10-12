#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} == --uninstall ]]; then
  rm -f "$HOME/.config/autostart/mseries-keyboard-backlight.desktop"
  pkill -f '^/usr/bin/python3 .*/mseries-keyboard-backlight$' || true
  echo 'Disabled automatic keyboard lighting.'
  exit
fi
/usr/bin/python3 -c 'from gi.repository import Gio, GLib'
install -Dm755 "$repo/mseries/keyboard-backlight/backlight.py" "$HOME/.local/libexec/mseries-keyboard-backlight"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/mseries-keyboard-backlight.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Automatic keyboard lighting
Comment=Adjust keyboard lighting to ambient light
Exec=/usr/bin/python3 "$HOME/.local/libexec/mseries-keyboard-backlight"
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF
pkill -f '^/usr/bin/python3 .*/mseries-keyboard-backlight$' || true
nohup /usr/bin/python3 "$HOME/.local/libexec/mseries-keyboard-backlight" > /tmp/mseries-keyboard-backlight.log 2>&1 < /dev/null &
echo 'Automatic keyboard lighting installed and started.'
