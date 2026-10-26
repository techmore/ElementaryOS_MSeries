#!/usr/bin/env bash
# Apply the complete dock customization stack to a fresh pinned upstream tree.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/../.." && pwd)
source_dir=${1:?usage: prepare-source.sh UPSTREAM_SOURCE}
for patch in dock-drawers dock-workspace-startup dock-taskbar dock-taskbar-codexbar dock-taskbar-repobar dock-taskbar-power-buttons dock-taskbar-notifications; do
  git -C "$source_dir" apply "$repo/mseries/patches/$patch.patch"
done
cp "$here/TaskbarNotifications.vala" "$source_dir/src/TaskbarNotifications.vala"
cp "$here/TaskbarCodexBar.vala" "$source_dir/src/TaskbarCodexBar.vala"
cp "$repo/mseries/quick-settings/AirDropPanel.vala" "$source_dir/src/AirDropPanel.vala"
cp "$here/TaskbarAirDrop.vala" "$source_dir/src/TaskbarAirDrop.vala"
cp "$here/TaskbarT3RPopover.vala" "$source_dir/src/TaskbarT3RPopover.vala"
mkdir -p "$source_dir/src/codexbar"
for source in Indicator JsonBoundary HelperProcess AccountDialog PanelPreferences RefreshPolicy QuotaEta Presentation; do
  cp "$repo/mseries/codexbar-wingpanel/$source.vala" "$source_dir/src/codexbar/"
done
# RepoBar's taskbar anchor sits beside CodexBar and embeds the shared Wingpanel indicator source.
cp "$here/TaskbarRepoBar.vala" "$source_dir/src/TaskbarRepoBar.vala"
mkdir -p "$source_dir/src/repobar"
# The dock links CodexBar's Wingpanel entry point already; drop RepoBar's duplicate (the class stays).
python3 - "$repo/mseries/repobar-wingpanel/Indicator.vala" "$source_dir/src/repobar/Indicator.vala" <<'PY'
import sys
text = open(sys.argv[1]).read()
marker = '\npublic Wingpanel.Indicator? get_indicator ('
assert text.count(marker) == 1, 'RepoBar entry point not found'
open(sys.argv[2], 'w').write(text[:text.index(marker)] + '\n')
PY
# Tracking may change launcher matching/markers, never taskbar/Start/CodexBar.
sha256sum "$source_dir/src/Taskbar.vala" "$source_dir/src/StartMenu.vala" \
  "$source_dir/src/TaskbarCodexBar.vala" "$source_dir/src/TaskbarRepoBar.vala" \
  "$source_dir/src/TaskbarNotifications.vala" "$source_dir/src/TaskbarAirDrop.vala" \
  "$source_dir/src/TaskbarT3RPopover.vala" "$source_dir/src/AirDropPanel.vala" \
  "$source_dir"/src/codexbar/*.vala "$source_dir"/src/repobar/*.vala > "$source_dir/.mseries-preserved.sha256"
git -C "$source_dir" apply "$repo/mseries/patches/dock-running-apps.patch"
git -C "$source_dir" apply "$repo/mseries/patches/dock-unique-launchers.patch"
git -C "$source_dir" apply --unidiff-zero "$repo/mseries/patches/dock-launcher-binding-lifecycle.patch"
# Attach T3's existing local-feed dropdown to its launcher in both Dock layouts.
git -C "$source_dir" apply "$repo/mseries/patches/dock-taskbar-t3r-popup.patch"
python3 - "$source_dir/src/AppSystem/Launcher.vala" <<'PY'
import pathlib, sys
source = pathlib.Path(sys.argv[1]).read_text()
required = [
    'app.bind_property ("current_count", badge, "label", SYNC_CREATE, app_badge_count_to_badge_string);',
    'private static bool app_badge_count_to_badge_string (Binding binding, Value from_value, ref Value to_value)',
]
for token in required:
    if token not in source:
        raise SystemExit(f'Launcher binding lifecycle patch is missing: {token}')
for token in ('private Binding current_count_binding;', 'current_count_binding.unbind ();'):
    if token in source:
        raise SystemExit(f'Launcher retains the old binding lifecycle: {token}')
PY
sha256sum --check --status "$source_dir/.mseries-preserved.sha256"
# Refuse a partial/stock rebuild instead of silently losing the Windows taskbar.
python3 - "$source_dir" <<'PY'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
for filename, required in {
    'src/meson.build': ['Taskbar.vala', 'StartMenu.vala', 'TaskbarCodexBar.vala', 'codexbar/Indicator.vala', 'TaskbarRepoBar.vala', 'repobar/Indicator.vala', 'TaskbarNotifications.vala', 'AirDropPanel.vala', 'TaskbarAirDrop.vala', 'TaskbarT3RPopover.vala'],
    'src/Taskbar.vala': ['new TaskbarCodexBar', 'new TaskbarRepoBar', 'new TaskbarNotifications', 'new TaskbarAirDrop', 'end_box.append (status_box)'],
    'src/AppSystem/Launcher.vala': ['new TaskbarT3RPopover (this, app)', 't3r_popup.toggle_from_icon ()'],
    'src/TaskbarT3RPopover.vala': ['"tokenUsage"', '"usedPercent"', '"repositories"', 'Timeout.add (250', 'Timeout.add (450'],
    'src/TaskbarAirDrop.vala': ['new MSeries.AirDropPanel'],
    'src/AirDropPanel.vala': ['Receive Files'],
    'src/MainWindow.vala': ['taskbar-mode', 'TaskbarRow'],
    'data/dock.gschema.xml': ['taskbar-mode'],
}.items():
    text = (root / filename).read_text()
    for token in required:
        if token not in text:
            raise SystemExit(f'Incomplete Windows taskbar source: {filename} lacks {token}')
PY
