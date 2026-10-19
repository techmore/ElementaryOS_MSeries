#!/usr/bin/env bash
# Smoke test for install-gala-mutter-fix.sh: start the patched Gala headless on a private bus with the
# same library path the mseries-gala launcher builds, check that it loaded the fixed libmutter and that
# it serves windows. The real session, its display and its dconf database are untouched.
set -euo pipefail
if [[ ${MSERIES_MUTTER_FIX_TEST_BUS:-} != 1 ]]; then
    exec dbus-run-session -- env MSERIES_MUTTER_FIX_TEST_BUS=1 bash "$0"
fi
mfix=/usr/local/lib/mseries/gala/mutter-fix
gala=/usr/local/lib/mseries/gala/bin/gala
[[ -e $mfix/libmutter-18.so.0 && -x $gala ]] || { echo "FAIL: fix or patched Gala not installed" >&2; exit 1; }
[[ $(cat "$mfix/mutter-version") == "$(dpkg-query -W -f='${Version}' libmutter-18-0)" ]] \
    || { echo "FAIL: fix built for another mutter version; the launcher would skip it" >&2; exit 1; }

test_dir=$(mktemp -d)
export XDG_CONFIG_HOME=$test_dir/config XDG_DATA_HOME=$test_dir/data GSETTINGS_BACKEND=memory
export WAYLAND_DISPLAY=mseries-mutter-fix-test-$$
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"
printf '# No panels or dock in the isolated test desktop.\n' > "$XDG_CONFIG_HOME/io.elementary.desktop.wm.shell"
LD_LIBRARY_PATH=$mfix:/usr/local/lib/mseries/gala/lib "$gala" --wayland --headless --no-x11 \
    --wayland-display="$WAYLAND_DISPLAY" --virtual-monitor=1600x1000 >"$test_dir/gala.log" 2>&1 &
pid=$!
cleanup() { kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; rm -rf "$test_dir"; }
trap cleanup EXIT

up=0
for ((i = 0; i < 100; i++)); do
    if gdbus call --session --dest org.pantheon.gala --object-path /org/pantheon/gala/DesktopInterface \
        --method org.pantheon.gala.DesktopIntegration.GetWindows >/dev/null 2>&1; then up=1; break; fi
    kill -0 "$pid" 2>/dev/null || break
    sleep .1
done
if [[ $up != 1 ]]; then echo "FAIL: Gala did not come up" >&2; cat "$test_dir/gala.log" >&2; exit 1; fi
grep -q "$mfix/libmutter-18.so.0" "/proc/$pid/maps" || { echo "FAIL: Gala did not load the fixed libmutter" >&2; exit 1; }
grep -q '/usr/lib/.*/mutter-18/libmutter-clutter-18.so.0' "/proc/$pid/maps" || { echo "FAIL: system clutter not loaded" >&2; exit 1; }

# A Wayland client maps and unmaps a window; Gala must still be alive afterwards.
GDK_BACKEND=wayland timeout 10 python3 -I - <<'PY'
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
app = Gtk.Application(application_id="org.mseries.MutterFixTest")
def on_activate(a):
    w = Gtk.ApplicationWindow(application=a, title="mutter fix test")
    w.present()
    GLib.timeout_add(800, lambda: (w.destroy(), a.quit()) and False)
app.connect("activate", on_activate)
app.run([])
PY
sleep .5
kill -0 "$pid" 2>/dev/null || { echo "FAIL: Gala exited after a window closed" >&2; cat "$test_dir/gala.log" >&2; exit 1; }
echo "PASS: patched Gala runs headless on the fixed libmutter ($(cat "$mfix/mutter-version") + c18af474)"
