#!/usr/bin/env bash
set -euo pipefail

# User-local deployment; does not restart Wingpanel or the compositor.
source_dir=$(cd -- "$(dirname -- "$0")/desktop-notifications" && pwd)
install_dir="${XDG_DATA_HOME:-$HOME/.local/share}/mseries/desktop-notifications"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
activate=false
previous_inset=0
if [[ -f "$unit_dir/mseries-desktop-notifications.service" ]]; then
    previous_inset=$(sed -n 's/^Environment=MSERIES_NOTIFICATION_DOCK_INSET=//p' \
        "$unit_dir/mseries-desktop-notifications.service" | tail -n 1)
    previous_inset=${previous_inset:-0}
fi
dock_inset="${MSERIES_NOTIFICATION_DOCK_INSET:-$previous_inset}"
if [[ ! "$dock_inset" =~ ^[0-9]{1,3}$ ]] || (( 10#$dock_inset > 512 )); then
    echo 'MSERIES_NOTIFICATION_DOCK_INSET must be 0..512 logical pixels' >&2
    exit 2
fi
previous_top=0
if [[ -f "$unit_dir/mseries-desktop-notifications.service" ]]; then
    previous_top=$(sed -n 's/^Environment=MSERIES_NOTIFICATION_TOP_INSET=//p' \
        "$unit_dir/mseries-desktop-notifications.service" | tail -n 1)
    previous_top=${previous_top:-0}
fi
top_inset="${MSERIES_NOTIFICATION_TOP_INSET:-$previous_top}"
if [[ ! "$top_inset" =~ ^[0-9]{1,3}$ ]] || (( 10#$top_inset > 512 )); then
    echo 'MSERIES_NOTIFICATION_TOP_INSET must be 0..512 logical pixels' >&2
    exit 2
fi
if [[ ${1:-} == --activate ]]; then
    activate=true
elif [[ $# -ne 0 ]]; then
    echo 'Usage: install-desktop-notifications.sh [--activate]' >&2
    exit 2
fi
install -d -m 755 "$install_dir" "$unit_dir"
for file in "$source_dir"/*.py; do
    [[ $(basename "$file") == test_* ]] && continue
    install -m 644 "$file" "$install_dir/"
done
install -m 644 "$source_dir/README.md" "$install_dir/README.md"
install -m 644 "$source_dir/LICENSE" "$install_dir/LICENSE"
main_file="$install_dir/notifications.py"
[[ -f "$main_file" ]] || { echo 'Notification entry point missing' >&2; exit 1; }
cat > "$unit_dir/mseries-desktop-notifications.service" <<EOF
[Unit]
Description=M-Series desktop notification popups
PartOf=graphical-session.target
After=graphical-session-pre.target

[Service]
Type=dbus
BusName=org.freedesktop.Notifications
ExecStart=/usr/bin/python3 "$main_file"
Environment=GDK_BACKEND=x11
Environment=MSERIES_NOTIFICATION_DOCK_INSET=$dock_inset
Environment=MSERIES_NOTIFICATION_TOP_INSET=$top_inset
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=graphical-session.target
EOF
if "$activate"; then
    # Stop our earlier transient recovery unit before loading its persistent replacement.
    systemctl --user stop mseries-desktop-notifications.service || true
    systemctl --user daemon-reload
    systemctl --user enable --now mseries-desktop-notifications.service
    systemctl --user is-active mseries-desktop-notifications.service
else
    echo 'Installed; activate with --activate after review.'
fi
