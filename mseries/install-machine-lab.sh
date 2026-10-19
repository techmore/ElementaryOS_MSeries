#!/usr/bin/env bash
# Build Machine Lab and install it for the current user: binary, launcher, icon,
# desktop entry, and a pin in the elementary dock.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/machine-lab
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT

meson setup "$build" "$here" --prefix="$HOME/.local" >/dev/null
meson compile -C "$build"
meson install -C "$build" >/dev/null

# The launcher is installed as bin/machine-lab-run-vm by meson; refresh caches.
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

# Pin to the dock (idempotent).
desktop=io.github.mseries.MachineLab.desktop
current=$(dconf read /io/elementary/dock/launchers 2>/dev/null || true)
if [ -n "$current" ] && [[ "$current" != *"$desktop"* ]]; then
    dconf write /io/elementary/dock/launchers "${current%]}, '$desktop']"
fi
echo "Machine Lab installed. Launch it from the dock or: $HOME/.local/bin/machine-lab"
