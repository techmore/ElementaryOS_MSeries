#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
command -v blueferry >/dev/null || { echo 'Install BlueFerry backend and GTK client first.' >&2; exit 1; }
python3 -c 'import gi, dbus; gi.require_version("Gtk", "4.0"); gi.require_version("Granite", "7.0")'
python3 "$here/phone-setup/test_setup.py"
python3 "$here/phone-setup/test_protocol.py"
python3 "$here/phone-setup/test_connection.py"
root=${XDG_DATA_HOME:-$HOME/.local/share}/mseries/phone-setup
install -d "$root" "$HOME/.local/bin" "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
install -m644 "$here/phone-setup/setup_core.py" "$root/setup_core.py"
install -m644 "$here/phone-setup/connection.py" "$root/connection.py"
install -m755 "$here/phone-setup/phone_status.py" "$root/phone_status.py"
install -m755 "$here/phone-setup/phone-setup.py" "$root/phone-setup.py"
ln -sfn "$root/phone-setup.py" "$HOME/.local/bin/mseries-phone-setup"
ln -sfn "$root/phone_status.py" "$HOME/.local/bin/mseries-phone-status"
cat > "${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.elementary.mseries.PhoneSetup.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Connect iPhone
Comment=Set up iPhone messages on this desktop
Exec="$root/phone-setup.py"
Icon=phone
Categories=Network;Settings;
Terminal=false
DESKTOP
update-desktop-database "${XDG_DATA_HOME:-$HOME/.local/share}/applications" 2>/dev/null || true
printf '%s\n' 'Connect iPhone installed. Launch mseries-phone-setup.'
