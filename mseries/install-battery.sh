#!/usr/bin/env bash
# Install the Battery history logger, `mseries-battery` command and Battery app. Use --uninstall to remove them
# (the recorded history in ~/.local/share/mseries-battery is kept).
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/battery" && pwd)
dest=/usr/libexec/mseries/battery

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now mseries-battery-logger.service 2>/dev/null || true
  sudo systemctl --global disable mseries-battery-logger.service 2>/dev/null || true
  sudo rm -rf "$dest" /usr/lib/systemd/user/mseries-battery-logger.service /usr/share/applications/org.mseries.Battery.desktop \
    /usr/local/bin/mseries-battery
  echo 'Removed. History kept in ~/.local/share/mseries-battery.'
  exit 0
fi

python3 -I "$here/test_battery_core.py" >/dev/null
sudo install -d "$dest"
sudo install -m 0644 "$here/battery_core.py" "$dest/"
sudo install -m 0755 "$here/mseries-battery-logger.py" "$here/mseries-battery.py" "$here/mseries-battery-app.py" "$dest/"
sudo install -m 0644 "$here/mseries-battery-logger.service" /usr/lib/systemd/user/
sudo install -m 0644 "$here/org.mseries.Battery.desktop" /usr/share/applications/
sudo ln -sfn "$dest/mseries-battery.py" /usr/local/bin/mseries-battery
sudo systemctl --global enable mseries-battery-logger.service
systemctl --user daemon-reload
systemctl --user enable --now mseries-battery-logger.service
sudo update-desktop-database /usr/share/applications 2>/dev/null || true
echo 'Installed. Logging every 15 s; open "Battery" from the launcher or run: mseries-battery status'
