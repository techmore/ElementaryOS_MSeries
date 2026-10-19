#!/usr/bin/env bash
# Production Wingpanel measurement/reparenting and actual Gala readiness, isolated from the owner.
set -euo pipefail
if [[ ${MSERIES_PANEL_TEST_BUS:-} != 1 ]]; then
    exec dbus-run-session -- env MSERIES_PANEL_TEST_BUS=1 bash "$0"
fi
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
test_dir=$(mktemp -d)
prefix=${MSERIES_TEST_GALA_PREFIX:-/usr/local/lib/mseries/gala}
gala_pid=
cleanup() {
    if [[ -n $gala_pid ]]; then
        kill "$gala_pid" 2>/dev/null || true
        wait "$gala_pid" 2>/dev/null || true
    fi
    rm -rf "$test_dir"
}
trap cleanup EXIT
git -C "$test_dir" init -q
git -C "$test_dir" fetch -q --depth=1 "${MSERIES_WINGPANEL_SOURCE:-https://github.com/elementary/wingpanel.git}" 6b8ae0453b1fd6dc07bd246642998011f04b2125
git -C "$test_dir" checkout -q --detach FETCH_HEAD
for patch in wingpanel-full-height wingpanel-clockright-order wingpanel-startup-layout; do
    git -C "$test_dir" apply "$repo/mseries/patches/$patch.patch"
done
cp "$repo/mseries/display-space/test-panel-startup.vala" "$test_dir/src/"
python3 - "$test_dir/src/meson.build" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
files = sorted(str(f.relative_to(p.parent)) for f in p.parent.rglob('*.vala') if f.name != 'Application.vala')
p.write_text(p.read_text() + "\nexecutable('test-panel-startup', css_gresource, files(" +
             ','.join(repr(f) for f in files) + "), dependencies: wingpanel_deps)\n")
PY
meson setup "$test_dir/build" "$test_dir" --prefix=/usr --buildtype=release >"$test_dir/build.log" 2>&1
if ! ninja -C "$test_dir/build" >>"$test_dir/build.log" 2>&1; then
    cat "$test_dir/build.log" >&2
    exit 1
fi
export XDG_CONFIG_HOME=$test_dir/config
export XDG_DATA_HOME=$test_dir/data
export GSETTINGS_BACKEND=keyfile
export GDK_BACKEND=wayland
export WAYLAND_DISPLAY=mseries-panel-test-$$
export LD_LIBRARY_PATH=$prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"
# A no-window fake client reproduces the disabled dock without invoking its launcher.
cat > "$XDG_CONFIG_HOME/io.elementary.desktop.wm.shell" <<EOF
[io.elementary.dock]
args=/usr/bin/sleep;infinity;
wait-for-n-panels=1
session-type=desktop
EOF
start_gala() {
    "$prefix/bin/gala" --wayland --headless --no-x11 --wayland-display="$WAYLAND_DISPLAY" \
        --virtual-monitor=1512x982 >"$test_dir/gala.log" 2>&1 &
    gala_pid=$!
    for ((attempt=0; attempt<100; attempt++)); do
        if gdbus call --session --dest org.gnome.Mutter.DisplayConfig --object-path /org/gnome/Mutter/DisplayConfig \
            --method org.gnome.Mutter.DisplayConfig.GetCurrentState >/dev/null 2>&1; then return; fi
        sleep .1
    done
    cat "$test_dir/gala.log" >&2
    return 1
}
start_gala
sleep 5.5
rg -q '1 panels failed to start in time' "$test_dir/gala.log"
echo 'PASS: baseline reproduces the disabled-panel timeout'
kill "$gala_pid"
wait "$gala_pid" || true
gala_pid=
touch "$test_dir/disabled-marker"
python3 "$repo/mseries/display-space/session_startup.py" \
    --source "$XDG_CONFIG_HOME/io.elementary.desktop.wm.shell" \
    --output "$XDG_CONFIG_HOME/io.elementary.desktop.wm.shell" --disabled-marker "$test_dir/disabled-marker"
start_gala
G_DEBUG=fatal-criticals "$test_dir/build/src/test-panel-startup"
sleep 5.5
if rg 'panels failed to start in time' "$test_dir/gala.log"; then exit 1; fi
echo 'PASS: repaired no-window client causes no panel-readiness timeout'
