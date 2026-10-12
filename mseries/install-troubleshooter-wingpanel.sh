#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} == --uninstall ]]; then
  systemctl --user stop mseries-crash-watch.service
  rm -f "$HOME/.config/autostart/mseries-crash-watch.desktop" "$HOME/.config/systemd/user/mseries-crash-watch.service"
  sudo rm -f "$(pkg-config --variable=indicatorsdir wingpanel-9)/libmseries-troubleshooter.so"
  systemctl --user daemon-reload
  exit
fi
test -x "$HOME/.local/bin/mseries-troubleshoot" || { echo 'Run mseries/local-ai/install-troubleshooter.sh first.' >&2; exit 1; }
install -Dm755 "$repo/mseries/local-ai/crash-watch.py" "$HOME/.local/libexec/mseries-crash-watch"
mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/autostart"
cat > "$HOME/.config/systemd/user/mseries-crash-watch.service" <<EOF
[Unit]
Description=Watch for local user crashes
[Service]
ExecStart=/usr/bin/python3 "$HOME/.local/libexec/mseries-crash-watch"
Restart=on-failure
RestartSec=10
EOF
cat > "$HOME/.config/autostart/mseries-crash-watch.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Local crash watcher
Exec=systemctl --user start mseries-crash-watch.service
NoDisplay=true
EOF
build_dir=$(mktemp -d /tmp/troubleshooter-wingpanel.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
meson setup "$build_dir" "$repo/mseries/troubleshooter-wingpanel" --prefix=/usr
ninja -C "$build_dir"
sudo ninja -C "$build_dir" install
sudo gtk-update-icon-cache -f -t /usr/share/icons/hicolor
systemctl --user daemon-reload
systemctl --user restart mseries-crash-watch.service
echo 'Installed native troubleshooting menu and crash watcher. Reload Wingpanel to show it.'
