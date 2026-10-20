#!/usr/bin/env bash
set -euo pipefail
source_dir=${1:?source directory}
build_dir=${2:?build directory}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/home/.local/share/applications"
cat > "$work/home/.local/share/applications/TeamsFixture.desktop" <<'APP'
[Desktop Entry]
Type=Application
Name=Teams fixture
Exec=/usr/bin/true
Icon=application-default-icon
StartupWMClass=TeamsFixture
APP
glib-compile-schemas --strict "$source_dir/data"
env HOME="$work/home" XDG_DATA_HOME="$work/home/.local/share" \
  XDG_CONFIG_HOME="$work/home/.config" XDG_CACHE_HOME="$work/home/.cache" \
  GSETTINGS_SCHEMA_DIR="$source_dir/data" GSETTINGS_BACKEND=memory GDK_BACKEND=x11 \
  GSK_RENDERER=cairo xvfb-run -a "$build_dir/src/test-markers"
