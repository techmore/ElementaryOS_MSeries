#!/usr/bin/env bash
# Build Orchard (machines, Incus and Podman in one app) and install it for the current
# user under ~/.local: binary, launcher helpers, icons, desktop entry, and a pin in the
# elementary dock. Removes the entries of the two apps it replaces (Machine Lab and
# Orchard for Incus) so the applications menu and the dock show one Orchard.
#   bash mseries/install-orchard.sh            # install or update
#   bash mseries/install-orchard.sh --no-dock  # do not touch the dock pins or restart the dock
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/orchard
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
touch_dock=1
[ "${1:-}" = "--no-dock" ] && touch_dock=0

share=${XDG_DATA_HOME:-$HOME/.local/share}
apps="$share/applications"
icons="$share/icons/hicolor/scalable"
desktop=com.github.techmore.orchard.desktop

# The Wingpanel indicator installs under /usr/lib (root), so it is left out of a ~/.local install.
meson setup "$build" "$here" --prefix="$HOME/.local" -Dwingpanel=disabled >/dev/null
meson compile -C "$build"
meson install -C "$build" >/dev/null

# Stale entries of the apps Orchard replaces: Machine Lab, the native Orchard for Incus and
# the older Python Orchard for Incus. Their data stays (~/.config/machine-lab, ~/.config/orchard-incus).
for old in io.github.mseries.MachineLab com.github.techmore.orchard-incus io.github.techmore.OrchardIncus; do
    rm -f "$apps/$old.desktop" "$icons/apps/$old.svg"
done
rm -f "$HOME/.local/bin/machine-lab" "$HOME/.local/bin/com.github.techmore.orchard-incus" "$HOME/.local/bin/com.github.techmore.orchard-incus.pre-podman"
rm -f "$share/metainfo/io.github.mseries.MachineLab.metainfo.xml"
# The Python Orchard for Incus (mseries/orchard-incus/install.sh) installed a launcher and a tree of its own.
rm -rf "$HOME/.local/bin/orchard-incus" "$share/orchard-incus"

update-desktop-database "$apps" 2>/dev/null || true
gtk-update-icon-cache -f -t "$share/icons/hicolor" 2>/dev/null || true

if [ "$touch_dock" = 1 ] && command -v dconf >/dev/null; then
    # Replace the old pins with one Orchard pin, in Machine Lab's place when it had one (idempotent).
    current=$(dconf read /io/elementary/dock/launchers 2>/dev/null || true)
    if [ -n "$current" ]; then
        updated=$(python3 - "$current" "$desktop" <<'PY'
import ast, sys
current = ast.literal_eval(sys.argv[1]); new = sys.argv[2]
old = {"io.github.mseries.MachineLab.desktop", "com.github.techmore.orchard-incus.desktop", "io.github.techmore.OrchardIncus.desktop"}
out = []
for entry in current:
    if entry in old:
        if new not in out: out.append(new)
    elif entry == new:
        if new not in out: out.append(new)
    else:
        out.append(entry)
if new not in out: out.append(new)
print(repr(out))
PY
)
        if [ "$updated" != "$current" ]; then
            dconf write /io/elementary/dock/launchers "$updated"
        fi
    fi
    # A newly installed app shows the wrong dock icon until the dock re-reads the entries. The
    # KillMode=process drop-in keeps dock-launched apps alive across this restart.
    systemctl --user restart pantheon-dock 2>/dev/null || true
fi
echo "Orchard installed. Launch it from the dock or: gio launch $apps/$desktop"
