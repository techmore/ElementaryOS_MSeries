#!/usr/bin/env bash
# Run only against a private D-Bus session masquerading as the system bus.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
valac --pkg gtk4 --pkg granite-7 -X '-DGETTEXT_PACKAGE="quick-settings"' \
    -o "$work/probe" "$here/../Bluetooth.vala" "$here/bluetooth-probe.vala" >"$work/build.log" 2>&1 || {
    cat "$work/build.log"; exit 1;
}
export BT_TEST_DIR="$here" BT_TEST_WORK="$work"
dbus-run-session -- bash -euo pipefail -c '
    export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
    python3 "$BT_TEST_DIR/fake_bluez.py" >"$BT_TEST_WORK/bus.log" 2>&1 &
    service_pid=$!
    trap '\''kill "$service_pid" 2>/dev/null || true'\'' EXIT
    for attempt in {1..50}; do
        if grep -q READY "$BT_TEST_WORK/bus.log"; then break; fi
        if ! kill -0 "$service_pid" 2>/dev/null; then cat "$BT_TEST_WORK/bus.log"; exit 1; fi
        sleep 0.1
    done
    G_DEBUG=fatal-criticals GIO_USE_VFS=local GTK_A11Y=none GSK_RENDERER=cairo GDK_BACKEND=x11 xvfb-run -a "$BT_TEST_WORK/probe" || { cat "$BT_TEST_WORK/bus.log"; exit 1; }
'
