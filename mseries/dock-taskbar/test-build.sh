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
meson setup "$work/build" "$work/source" --buildtype=release
meson compile -C "$work/build"
glib-compile-schemas --strict --dry-run "$work/source/data"
# These type names are emitted by the actual linked Vala classes.
for component in DockTaskbarRow DockStartMenu DockTaskbarCodexBar; do
  strings "$work/build/src/io.elementary.dock" | grep -F "$component" > /dev/null
done
bash "$here/test-hover.sh"
echo 'PASS complete Windows taskbar + CodexBar clean build; no deployment'
