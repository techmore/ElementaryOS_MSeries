#!/usr/bin/env bash
# Real GTK popup with isolated config/backend; no live accounts or dock service.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/home/.local/bin" "$work/schemas" "$work/schema-free-data"
cat > "$work/home/.local/bin/codexbar-linux" <<'BACKEND'
#!/bin/sh
[ "$1" = --snapshot ] && printf '{"entries":[]}'
exit 0
BACKEND
chmod +x "$work/home/.local/bin/codexbar-linux"
cat > "$work/schemas/io.elementary.dock.gschema.xml" <<'SCHEMA'
<schemalist><schema id="io.elementary.dock" path="/io/elementary/dock/"><key name="icon-size" type="i"><default>48</default></key></schema></schemalist>
SCHEMA
glib-compile-schemas --strict "$work/schemas"
sources=()
for source in Indicator JsonBoundary HelperProcess AccountDialog PanelPreferences RefreshPolicy QuotaEta Presentation; do
  sources+=("$repo/mseries/codexbar-wingpanel/$source.vala")
done
valac --pkg wingpanel-9 --pkg granite-7 --pkg json-glib-1.0 -X -lm \
  --directory="$work" -o "$work/test-hover" "$here/TaskbarCodexBar.vala" "$here/test-hover.vala" "${sources[@]}" >"$work/build.log" 2>&1 || { cat "$work/build.log"; exit 1; }
env HOME="$work/home" XDG_CONFIG_HOME="$work/home/.config" XDG_DATA_HOME="$work/home/.local/share" \
  XDG_CACHE_HOME="$work/home/.cache" GSETTINGS_BACKEND=memory GSETTINGS_SCHEMA_DIR="$work/schemas" \
  XDG_DATA_DIRS="$work/schema-free-data" G_DEBUG=fatal-criticals GDK_BACKEND=x11 GSK_RENDERER=cairo \
  xvfb-run -a "$work/test-hover"
