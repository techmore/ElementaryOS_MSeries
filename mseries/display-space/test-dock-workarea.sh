#!/usr/bin/env bash
# Real dock/GTK clients in an isolated two-monitor Wayland desktop.
set -euo pipefail
if [[ ${MSERIES_DOCK_TEST_BUS:-} != 1 ]]; then
    exec dbus-run-session -- env MSERIES_DOCK_TEST_BUS=1 bash "$0"
fi
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
test_dir=$(mktemp -d)
prefix=${MSERIES_TEST_GALA_PREFIX:-/usr/local/lib/mseries/gala}
dock_prefix=${MSERIES_TEST_DOCK_PREFIX:-$HOME/.local/lib/mseries/dock}
export XDG_CONFIG_HOME=$test_dir/config
export XDG_DATA_HOME=$test_dir/data
export GSETTINGS_BACKEND=keyfile
export GDK_BACKEND=wayland
export WAYLAND_DISPLAY=mseries-dock-test-$$
export LD_LIBRARY_PATH=$prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export GSETTINGS_SCHEMA_DIR=$dock_prefix/share/glib-2.0/schemas
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"
cat > "$XDG_CONFIG_HOME/io.elementary.desktop.wm.shell" <<EOF
[io.elementary.dock]
args=$dock_prefix/bin/io.elementary.dock;
wait-for-n-panels=1
session-type=desktop
EOF
# Keyfile settings intentionally bypass the user's dconf policy. Reproduce the
# half-snap bindings explicitly and remove the stock workspace-key conflict.
gsettings set org.gnome.mutter edge-tiling true
gsettings set org.gnome.mutter.keybindings toggle-tiled-right "['<Super>Right']"
gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-right "[]"
"$prefix/bin/gala" --wayland --headless --no-x11 --wayland-display="$WAYLAND_DISPLAY" \
    --virtual-monitor=1600x1000 --virtual-monitor=1200x800 >"$test_dir/gala.log" 2>&1 &
gala_test_pid=$!
cleanup() {
    kill "$gala_test_pid" 2>/dev/null || true
    wait "$gala_test_pid" 2>/dev/null || true
    rm -rf "$test_dir"
}
trap cleanup EXIT
for ((attempt=0; attempt<100; attempt++)); do
    if gdbus call --session --dest org.pantheon.gala --object-path /org/pantheon/gala/DesktopInterface \
        --method org.pantheon.gala.DesktopIntegration.GetWindows >/dev/null 2>&1; then break; fi
    sleep .1
done
if ! python3 "$here/test-dock-workarea.py"; then
    cat "$test_dir/gala.log" >&2
    exit 1
fi
