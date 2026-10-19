#!/usr/bin/env bash
# Run after installation. The real session and its dconf database are untouched.
set -euo pipefail
if [[ ${MSERIES_SNAPPING_TEST_BUS:-} != 1 ]]; then
    exec dbus-run-session -- env MSERIES_SNAPPING_TEST_BUS=1 bash "$0"
fi
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
test_dir=$(mktemp -d)
export XDG_CONFIG_HOME=$test_dir/config
export XDG_DATA_HOME=$test_dir/data
export GSETTINGS_BACKEND=memory
export GDK_BACKEND=wayland
export WAYLAND_DISPLAY=mseries-snapping-test-$$
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"
printf '# No panels or dock in the isolated test desktop.\n' > "$XDG_CONFIG_HOME/io.elementary.desktop.wm.shell"
prefix=${MSERIES_TEST_GALA_PREFIX:-/usr/local/lib/mseries/gala}
gala=$prefix/bin/gala
export LD_LIBRARY_PATH=$prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
[[ -x $gala ]] || gala=$(command -v gala)
"$gala" --wayland --headless --no-x11 --wayland-display="$WAYLAND_DISPLAY" \
    --virtual-monitor=1600x1000 >"$test_dir/gala.log" 2>&1 &
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
if ! python3 "$here/test-native.py"; then
    cat "$test_dir/gala.log" >&2
    exit 1
fi
