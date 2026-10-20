#!/usr/bin/env bash
# Apply the complete dock customization stack to a fresh pinned upstream tree.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/../.." && pwd)
source_dir=${1:?usage: prepare-source.sh UPSTREAM_SOURCE}
for patch in dock-drawers dock-workspace-startup dock-taskbar dock-taskbar-codexbar; do
  git -C "$source_dir" apply "$repo/mseries/patches/$patch.patch"
done
cp "$here/TaskbarCodexBar.vala" "$source_dir/src/TaskbarCodexBar.vala"
mkdir -p "$source_dir/src/codexbar"
for source in Indicator JsonBoundary HelperProcess AccountDialog PanelPreferences RefreshPolicy QuotaEta Presentation; do
  cp "$repo/mseries/codexbar-wingpanel/$source.vala" "$source_dir/src/codexbar/"
done
# Refuse a partial/stock rebuild instead of silently losing the Windows taskbar.
python3 - "$source_dir" <<'PY'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
for filename, required in {
    'src/meson.build': ['Taskbar.vala', 'StartMenu.vala', 'TaskbarCodexBar.vala', 'codexbar/Indicator.vala'],
    'src/Taskbar.vala': ['new TaskbarCodexBar', 'end_box.append (status_box)'],
    'src/MainWindow.vala': ['taskbar-mode', 'TaskbarRow'],
    'data/dock.gschema.xml': ['taskbar-mode'],
}.items():
    text = (root / filename).read_text()
    for token in required:
        if token not in text:
            raise SystemExit(f'Incomplete Windows taskbar source: {filename} lacks {token}')
PY
