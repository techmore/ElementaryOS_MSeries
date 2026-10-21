#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=${XDG_DATA_HOME:-$HOME/.local/share}/mseries/phone-setup
units=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
apps=${XDG_DATA_HOME:-$HOME/.local/share}/applications
if [[ ${1:-} == --uninstall ]]; then
    systemctl --user disable --now mseries-verification-codes.service 2>/dev/null || true
    python3 "$here/phone-setup/code_shortcut.py" uninstall "$HOME/.local/bin/mseries-verification-codes" "$root"
    python3 - "$root" "$units" "$apps" "$HOME/.local/bin" <<'PYTHON'
from pathlib import Path
import sys
root,units,apps,bins=map(Path,sys.argv[1:])
files=[root/name for name in ('verification_codes.py','code_offers.py','code_fields.py','code_shortcut.py')]
files += [units/'mseries-verification-codes.service', apps/'io.elementary.mseries.VerificationCodes.desktop', bins/'mseries-verification-codes']
for path in files: path.unlink(missing_ok=True)
PYTHON
    systemctl --user daemon-reload
    update-desktop-database "$apps" 2>/dev/null || true
    echo 'Verification Codes removed; Messages and Bluetooth remain running.'
    exit 0
fi
[[ $# == 0 ]] || { echo 'Usage: install-verification-codes.sh [--uninstall]' >&2; exit 2; }
python3 -c 'import gi, blueferry; gi.require_version("Gtk", "4.0"); gi.require_version("Granite", "7.0"); gi.require_version("Atspi", "2.0"); gi.require_version("GdkX11", "4.0")'
command -v xdotool >/dev/null
python3 "$here/phone-setup/test_codes.py"
install -d "$root" "$HOME/.local/bin" "$units" "$apps"
install -m644 "$here/phone-setup/code_offers.py" "$here/phone-setup/code_fields.py" "$here/phone-setup/code_shortcut.py" "$root/"
install -m755 "$here/phone-setup/verification_codes.py" "$root/verification_codes.py"
cat > "$HOME/.local/bin/mseries-verification-codes" <<LAUNCHER
#!/bin/sh
export GDK_BACKEND=x11
export GSK_RENDERER=cairo
exec /usr/bin/python3 "$root/verification_codes.py" "\$@"
LAUNCHER
chmod 755 "$HOME/.local/bin/mseries-verification-codes"
cat > "$units/mseries-verification-codes.service" <<UNIT
[Unit]
Description=Verification code suggestions from iPhone messages
After=graphical-session.target blueferry.service
PartOf=graphical-session.target
[Service]
ExecStart="$HOME/.local/bin/mseries-verification-codes" --background
Restart=on-failure
RestartSec=3
UMask=0077
[Install]
WantedBy=graphical-session.target
UNIT
cat > "$apps/io.elementary.mseries.VerificationCodes.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Verification Codes
Comment=Use a recent iPhone code in the focused verification field
Exec="$HOME/.local/bin/mseries-verification-codes" --show
Icon=dialog-password
Categories=Utility;
Terminal=false
DESKTOP
python3 "$root/code_shortcut.py" install "$HOME/.local/bin/mseries-verification-codes" "$root"
systemctl --user daemon-reload
systemctl --user enable --now mseries-verification-codes.service
update-desktop-database "$apps" 2>/dev/null || true
echo 'Verification Codes installed. Bluetooth and Messages were not restarted.'
