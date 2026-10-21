#!/usr/bin/env bash
# Rebuild the complete pinned Windows taskbar without installing or restarting it.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
commit=8b45a68a122947ad3a6427bf6e159ec2acf04ad0
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
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
cp "$here/../dock-tests/test-marker-state.vala" "$work/source/src/test-marker-state.vala"
cp "$here/../dock-tests/test-launcher-qualification.vala" "$work/source/src/test-launcher-qualification.vala"
cat >> "$work/source/src/meson.build" <<'MESON'
marker_sources = []
foreach source : sources
  if source != 'Application.vala'
    marker_sources += source
  endif
endforeach
executable('test-markers', gresource, marker_sources, 'test-marker-state.vala', dependencies: dependencies)
executable('test-launcher-qualification', gresource, marker_sources, 'test-launcher-qualification.vala', dependencies: dependencies)
MESON
meson setup "$work/build" "$work/source" --buildtype=release
meson compile -C "$work/build"
glib-compile-schemas --strict --dry-run "$work/source/data"
# These type names are emitted by the actual linked Vala classes.
for component in DockTaskbarRow DockStartMenu DockTaskbarCodexBar DockAppResolver; do
  strings "$work/build/src/io.elementary.dock" | grep -F "$component" > /dev/null
done
bash "$here/../dock-tests/test-markers.sh" "$work/source" "$work/build"
GSETTINGS_SCHEMA_DIR="$work/source/data" python3 "$here/../dock-tests/test-launcher-qualification.py" \
  "$work/build/src/test-launcher-qualification" "${MSERIES_QUALIFICATION_OUT:-$work/qualification}"
bash "$here/test-hover.sh"
bash "$here/../dock-tests/test-running-apps.sh"
echo 'PASS complete Windows taskbar + CodexBar clean build; no deployment'
