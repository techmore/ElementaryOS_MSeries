#!/bin/sh
# Owner-requested permanent Pantheon dock, including removal of bounded trial hooks.
set -eu
config=${XDG_CONFIG_HOME:-$HOME/.config}
state=${XDG_STATE_HOME:-$HOME/.local/state}
# Stop trial controllers before removing their independent deadlines.
for pid in $(pgrep -u "$(id -u)" -f '^/usr/bin/python3 /home/[^/]+/.local/libexec/mseries-dock-trial( |$)' || true); do
    kill "$pid" 2>/dev/null || true
done
systemctl --user stop mseries-dock-trial-stop.timer mseries-dock-restore-visibility.timer pantheon-dock.service 2>/dev/null || true
rm -f "$config/systemd/user/pantheon-dock.service.d/90-bounded-trial.conf"
rm -f "$state/mseries/dock-trial/pending-login-trial"
rm -f "$config/autostart/mseries-dock-trial.desktop"
rm -f "$config/mseries/dock/user-disabled"
gsettings set io.elementary.dock autohide-mode never
# Native dock token from the size system (#332) once adopted; 48 px at the default step.
icon_size=$("${HOME}/.local/bin/mseries-ui-scale" --dock-size native 2>/dev/null) || icon_size=48
case $icon_size in ''|*[!0-9]*) icon_size=48 ;; esac
gsettings set io.elementary.dock icon-size "$icon_size"
systemctl --user daemon-reload
systemctl --user reset-failed pantheon-dock.service
systemctl --user start pantheon-dock.service
systemctl --user is-active pantheon-dock.service
