#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_dir=${1:?source directory}
build_dir=${2:?build directory}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/home/.local/share/applications" "$work/runtime" "$work/schemas" "$work/schema-free-data"
chmod 0700 "$work/runtime"
cat > "$work/bus.conf" <<'BUS'
<busconfig>
  <type>session</type><listen>unix:tmpdir=/tmp</listen>
  <policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy>
</busconfig>
BUS
cat > "$work/home/.local/share/applications/TeamsFixture.desktop" <<'APP'
[Desktop Entry]
Type=Application
Name=Teams fixture
Exec=/usr/bin/true
Icon=application-default-icon
StartupWMClass=TeamsFixture
APP
# Use the actual prepared production dock schemas plus the exact Gala key this
# widget consumes. Never inherit a schema from the development desktop.
cp "$source_dir/data/dock.gschema.xml" "$work/schemas/"
cp "$source_dir/data/org.techmore.mseries.dock.gschema.xml" "$work/schemas/"
cp "$here/fixtures/gala-workspace-keybindings.gschema.xml" "$work/schemas/"
glib-compile-schemas --strict "$work/schemas"
env HOME="$work/home" XDG_DATA_HOME="$work/home/.local/share" \
  XDG_CONFIG_HOME="$work/home/.config" XDG_CACHE_HOME="$work/home/.cache" \
  XDG_STATE_HOME="$work/home/.local/state" \
  XDG_DATA_DIRS="$work/schema-free-data" GSETTINGS_SCHEMA_DIR="$work/schemas" GSETTINGS_BACKEND=memory GDK_BACKEND=x11 \
  XDG_RUNTIME_DIR="$work/runtime" GTK_A11Y=none GIO_USE_VFS=local G_DEBUG=fatal-criticals \
  GSK_RENDERER=cairo dbus-run-session --config-file="$work/bus.conf" -- \
    python3 "$here/test-size-policy.py" "$build_dir/src/test-size-policy"
