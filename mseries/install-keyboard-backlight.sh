#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} == --uninstall ]]; then
  rm -f "$HOME/.config/autostart/mseries-keyboard-backlight.desktop"
  systemctl --user stop mseries-keyboard-backlight.service 2>/dev/null || true
  rm -f "$HOME/.config/systemd/user/mseries-keyboard-backlight.service"
  systemctl --user daemon-reload
  pkill -f '^/usr/bin/python3 .*/mseries-keyboard-backlight$' || true
  echo 'Disabled automatic keyboard lighting.'
  exit
fi
/usr/bin/python3 -c 'from gi.repository import Gio, GLib'
install -Dm755 "$repo/mseries/keyboard-backlight/backlight.py" "$HOME/.local/libexec/mseries-keyboard-backlight"
mkdir -p "$HOME/.config/autostart" "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/mseries-keyboard-backlight.service" <<EOF
[Unit]
Description=Ambient keyboard lighting for elementary OS
[Service]
ExecStart=/usr/bin/python3 "$HOME/.local/libexec/mseries-keyboard-backlight"
Restart=on-failure
RestartSec=10
EOF
systemctl --user daemon-reload
cat > "$HOME/.config/autostart/mseries-keyboard-backlight.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Automatic keyboard lighting
Comment=Adjust keyboard lighting to ambient light
Exec=systemctl --user start mseries-keyboard-backlight.service
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF
pkill -f '^/usr/bin/python3 .*/mseries-keyboard-backlight$' || true
systemctl --user restart mseries-keyboard-backlight.service
echo 'Automatic keyboard lighting installed and started.'
