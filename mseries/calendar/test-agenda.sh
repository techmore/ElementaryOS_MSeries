#!/usr/bin/env bash
# Test an already built plugin without touching desktop or personal calendars.
set -euo pipefail
plugin=$(realpath "${1:?pass the built libdatetime.so}")
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
state=$(mktemp -d "${TMPDIR:-/tmp}/agenda-test.XXXXXX")
trap 'rm -rf "$state"' EXIT
mkdir -p "$state"/{config,data,cache,runtime}
chmod 700 "$state/runtime"
# The synthetic agenda never uses file portals. Prevent private-session portal
# activation from leaving document FUSE mounts behind when D-Bus exits.
mkdir -p "$state/data/dbus-1/services"
cat > "$state/data/dbus-1/services/org.freedesktop.portal.Desktop.service" <<'EOF'
[D-BUS Service]
Name=org.freedesktop.portal.Desktop
Exec=/usr/bin/false
EOF
valac --pkg wingpanel-9 --pkg gtk4 --pkg libadwaita-1 --pkg libecal-2.0 \
    --pkg libedataserver-1.2 --pkg libical-glib --pkg gmodule-2.0 \
    -X -DLIBICAL_GLIB_UNSTABLE_API=1 -o "$state/test-agenda" "$here/test-agenda.vala"
env XDG_CONFIG_HOME="$state/config" XDG_DATA_HOME="$state/data" \
    XDG_CACHE_HOME="$state/cache" XDG_RUNTIME_DIR="$state/runtime" \
    GSETTINGS_BACKEND=memory GSK_RENDERER=cairo GDK_BACKEND=x11 GTK_A11Y=none GIO_USE_VFS=local \
    dbus-run-session -- xvfb-run -a timeout 90 "$state/test-agenda" "$plugin"
