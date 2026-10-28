#!/usr/bin/env bash
# Rebuild the complete pinned Windows taskbar without installing or restarting it.
set -euo pipefail
# Every linked-widget fixture must share only a private bus/runtime. Service
# activation is disabled so GTK cannot start host portals or keyring services.
if [[ ${MSERIES_DOCK_TEST_BUS:-} != 1 ]]; then
  isolated=$(mktemp -d)
  trap 'rm -rf "$isolated"' EXIT
  mkdir "$isolated/runtime"
  chmod 0700 "$isolated/runtime"
  cat > "$isolated/bus.conf" <<'BUS'
<busconfig>
  <type>session</type><listen>unix:tmpdir=/tmp</listen>
  <policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy>
</busconfig>
BUS
  env XDG_RUNTIME_DIR="$isolated/runtime" GTK_A11Y=none GIO_USE_VFS=local MSERIES_DOCK_TEST_BUS=1 \
    dbus-run-session --config-file="$isolated/bus.conf" -- bash "$0"
  exit
fi
# The reachable private bus also serves as the logical system bus; optional
# service requests must never reach the host system bus.
export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
commit=8b45a68a122947ad3a6427bf6e159ec2acf04ad0
work=$(mktemp -d)
# Build tools retain normal data roots for VAPI metadata. Each native fixture
# excludes host schema roots in its runtime environment, after compilation.
portal_pid=
cleanup() {
  if [[ -n $portal_pid ]]; then
    kill "$portal_pid" 2>/dev/null || true
    wait "$portal_pid" 2>/dev/null || true
  fi
  rm -rf "$work"
}
trap cleanup EXIT
export QUAL_PORTAL_READY="$XDG_RUNTIME_DIR/dock-portal-ready"
python3 "$here/../dock-tests/test-launcher-qualification.py" --portal &
portal_pid=$!
python3 - "$QUAL_PORTAL_READY" "$portal_pid" <<'PYREADY'
from pathlib import Path
import os,sys,time
ready = Path(sys.argv[1])
deadline = time.monotonic() + 10
while not ready.exists():
    os.kill(int(sys.argv[2]), 0)
    assert time.monotonic() < deadline, 'Private portal readiness timed out'
    time.sleep(0.02)
PYREADY
mkdir "$work/source"
if [[ -n ${MSERIES_DOCK_SOURCE:-} ]]; then
  [[ $(git -C "$MSERIES_DOCK_SOURCE" rev-parse HEAD) == "$commit" ]]
  git -C "$MSERIES_DOCK_SOURCE" archive HEAD | tar -x -C "$work/source"
else
  git -C "$work/source" init -q
  git -C "$work/source" fetch -q --depth=1 https://github.com/elementary/dock.git "$commit"
  git -C "$work/source" checkout -q --detach FETCH_HEAD
fi
bash "$here/prepare-source.sh" "$work/source"
cp "$here/test-unified.vala" "$work/source/src/test-unified.vala"
cp "$here/../dock-tests/test-marker-state.vala" "$work/source/src/test-marker-state.vala"
cp "$here/../dock-tests/test-size-policy.vala" "$work/source/src/test-size-policy.vala"
cp "$here/../dock-tests/test-launcher-qualification.vala" "$work/source/src/test-launcher-qualification.vala"
cat >> "$work/source/src/meson.build" <<'MESON'
marker_sources = []
foreach source : sources
  if source != 'Application.vala'
    marker_sources += source
  endif
endforeach
executable('test-unified', gresource, marker_sources, 'test-unified.vala', dependencies: dependencies)
executable('test-size-policy', gresource, marker_sources, 'test-size-policy.vala', dependencies: dependencies)
executable('test-markers', gresource, marker_sources, 'test-marker-state.vala', dependencies: dependencies)
executable('test-launcher-qualification', gresource, marker_sources, 'test-launcher-qualification.vala', dependencies: dependencies)
MESON
meson setup "$work/build" "$work/source" --buildtype=release
meson compile -C "$work/build"
glib-compile-schemas --strict --dry-run "$work/source/data"
# These type names are emitted by the actual linked Vala classes.
for component in DockTaskbarT3 DockTaskbarRow DockStartMenu DockTaskbarCodexBar DockTaskbarRepoBar DockTaskbarRemote DockTaskbarNotifications DockTaskbarAirDrop DockTaskbarCalendar MSeriesAirDropPanel DockAppResolver; do
  strings "$work/build/src/io.elementary.dock" | grep -F "$component" > /dev/null
done
bash "$here/../dock-tests/test-size-policy.sh" "$work/source" "$work/build"
bash "$here/../dock-tests/test-markers.sh" "$work/source" "$work/build"
GSETTINGS_SCHEMA_DIR="$work/source/data" python3 "$here/../dock-tests/test-launcher-qualification.py" \
  "$work/build/src/test-launcher-qualification" "${MSERIES_QUALIFICATION_OUT:-$work/qualification}"
bash "$here/test-hover.sh"
bash "$here/test-calendar.sh"
bash "$here/test-unified.sh" "$work/source" "$work/build" "${MSERIES_QUALIFICATION_OUT:-$work/qualification}/unified"
bash "$here/../dock-tests/test-running-apps.sh"
echo 'PASS complete Windows taskbar + CodexBar clean build; no deployment'
