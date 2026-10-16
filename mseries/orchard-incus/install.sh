#!/bin/sh
# Install Orchard for Incus for the current user (no root).
#   ./install.sh            install or update (keeps an existing dock pin)
#   ./install.sh --pin      install and pin to the elementary dock
#   ./install.sh --uninstall
set -eu
ID=io.github.techmore.OrchardIncus
HERE=$(cd "$(dirname "$0")" && pwd)
SHARE=${XDG_DATA_HOME:-$HOME/.local/share}
BIN=$HOME/.local/bin
DESKTOP="$SHARE/applications/$ID.desktop"

dock_has() { gsettings get io.elementary.dock launchers 2>/dev/null | grep -q "$ID.desktop"; }
dock_set() {  # dock_set add|remove
    command -v gsettings >/dev/null 2>&1 || return 0
    python3 - "$1" "$ID.desktop" <<'PY'
import ast, subprocess, sys
op, entry = sys.argv[1:3]
cur = ast.literal_eval(subprocess.run(["gsettings", "get", "io.elementary.dock", "launchers"], capture_output=True, text=True).stdout.strip() or "[]")
new = [x for x in cur if x != entry] + ([entry] if op == "add" else [])
if new != cur:
    subprocess.run(["gsettings", "set", "io.elementary.dock", "launchers", str(new)])
PY
}

if [ "${1:-}" = "--uninstall" ]; then
    dock_set remove
    rm -rf "$SHARE/orchard-incus" "$BIN/orchard-incus" "$DESKTOP" "$SHARE/icons/hicolor/scalable/apps/$ID.svg"
    echo "Orchard for Incus removed."; exit 0
fi

WAS_PINNED=0; dock_has && WAS_PINNED=1
mkdir -p "$SHARE/orchard-incus" "$BIN" "$SHARE/applications" "$SHARE/icons/hicolor/scalable/apps"
rm -rf "$SHARE/orchard-incus/orchard_incus"
cp -r "$HERE/orchard_incus" "$SHARE/orchard-incus/"
find "$SHARE/orchard-incus" -name __pycache__ -prune -exec rm -rf {} +
install -m755 "$HERE/orchard-incus" "$BIN/orchard-incus"
install -m644 "$HERE/$ID.svg" "$SHARE/icons/hicolor/scalable/apps/$ID.svg"
# replace the desktop file atomically: the dock unpins a launcher whose desktop file disappears, even for a moment
sed "s#^Exec=.*#Exec=$BIN/orchard-incus#" "$HERE/$ID.desktop" > "$DESKTOP.new"
mv -f "$DESKTOP.new" "$DESKTOP"
gtk-update-icon-cache -f -t "$SHARE/icons/hicolor" >/dev/null 2>&1 || true
update-desktop-database "$SHARE/applications" >/dev/null 2>&1 || true
if [ "$WAS_PINNED" = 1 ] || [ "${1:-}" = "--pin" ]; then
    sleep 1; dock_set add
fi
echo "Installed: $BIN/orchard-incus (code in $SHARE/orchard-incus)"
