#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/home" "$work/runtime"
chmod 700 "$work/runtime"
cat > "$work/bus.conf" <<'BUS'
<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>
BUS
HOME="$work/home" XDG_RUNTIME_DIR="$work/runtime" XDG_CONFIG_HOME="$work/config" XDG_CACHE_HOME="$work/cache" XDG_DATA_HOME="$work/data" \
  MSERIES_DISPLAY_FAKE=1 GSETTINGS_BACKEND=memory GDK_BACKEND=x11 GDK_SCALE=1 GIO_USE_VFS=local NO_AT_BRIDGE=1 \
  dbus-run-session --config-file="$work/bus.conf" -- xvfb-run -a /usr/bin/python3 -B "$here/test_canvas.py"
