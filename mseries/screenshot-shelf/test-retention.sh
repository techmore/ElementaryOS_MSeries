#!/usr/bin/env bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
test_root=$(mktemp -d)
trap 'rm -rf -- "$test_root"' EXIT
mkdir -p "$test_root"/{home,runtime,config,cache,data}
# No service directories: GTK cannot auto-start the owner's portal/keyring/services.
cat > "$test_root/bus.conf" <<'XML'
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir=/tmp</listen>
  <policy context="default">
    <allow send_destination="*"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
XML
HOME="$test_root/home" XDG_RUNTIME_DIR="$test_root/runtime" \
XDG_CONFIG_HOME="$test_root/config" XDG_CACHE_HOME="$test_root/cache" XDG_DATA_HOME="$test_root/data" \
GTK_A11Y=none GIO_USE_VFS=local GSETTINGS_BACKEND=memory GSK_RENDERER=cairo \
MSERIES_SHELF_BACKEND=x11 GDK_SCALE=1 \
dbus-run-session --config-file "$test_root/bus.conf" -- xvfb-run -a \
  /usr/bin/python3 -B "$source_dir/test_retention.py"
