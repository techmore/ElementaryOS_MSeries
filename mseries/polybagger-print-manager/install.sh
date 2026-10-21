#!/usr/bin/env bash
# Install a launcher for PolyBagger Print Manager that runs it from this checkout.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_id=io.techmore.PolyBaggerPrintManager
dest="${XDG_DATA_HOME:-$HOME/.local/share}/applications/$app_id.desktop"
mkdir -p "$(dirname "$dest")"
cat > "$dest" <<DESKTOP
[Desktop Entry]
Name=PolyBagger Print Manager
Comment=Load labels onto the T-1000 bagger's Zebra printer and verify each step
Exec=python3 "$here/polybagger_print_manager.py"
Icon=printer
Terminal=false
Type=Application
Categories=Utility;
StartupWMClass=$app_id
DESKTOP
python3 "$here/polybagger_print_manager.py" --sync >/dev/null || true
echo "Installed $dest"
