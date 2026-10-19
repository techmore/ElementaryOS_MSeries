#!/usr/bin/env bash
# CI: build the pinned datetime indicator with our patch and run the full agenda suite
# off elementary OS. Granite 7.7 and the Wingpanel indicator API come from the CodexBar
# CI helper when the distribution lacks them; the indicator's GSettings schema is compiled
# into a private directory. Nothing is installed system-wide.
#   bash mseries/calendar/ci-test-agenda.sh WORKDIR
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=$(realpath -m "${1:?usage: ci-test-agenda.sh WORKDIR}")
mkdir -p "$work"
while IFS='=' read -r key value; do export "$key=$value"; done \
    < <(bash "$repo/mseries/codexbar-wingpanel/probe/ci-build-deps.sh" "$work/prefix")
readarray -t pin < <(python3 - "$repo/mseries/panel-factory-pins.json" <<'PY'
import json, sys
entry = next(p for p in json.load(open(sys.argv[1]))['indicators'] if p['name'] == 'datetime')
print(entry['repository']); print(entry['commit'])
PY
)
rm -rf "$work/source" "$work/build"
git init -q "$work/source"
git -C "$work/source" remote add origin "${pin[0]}"
git -C "$work/source" fetch -q --depth=1 origin "${pin[1]}"
git -C "$work/source" checkout -q --detach FETCH_HEAD
git -C "$work/source" apply "$repo/mseries/patches/datetime-agenda-tabs.patch"
meson setup "$work/build" "$work/source" --buildtype=release >/dev/null
ninja -C "$work/build"
mkdir -p "$work/schemas"
cp "$work/source/data/datetime.gschema.xml" "$work/schemas/io.elementary.desktop.wingpanel.datetime.gschema.xml"
# Keep the system schemas (clock format, interface) visible next to the indicator's own.
cp /usr/share/glib-2.0/schemas/*.gschema.xml "$work/schemas/" 2>/dev/null || true
glib-compile-schemas "$work/schemas"
GSETTINGS_SCHEMA_DIR="$work/schemas" bash "$repo/mseries/calendar/test-agenda.sh" "$work/build/libdatetime.so"
