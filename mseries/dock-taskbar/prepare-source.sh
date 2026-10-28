#!/usr/bin/env bash
# Apply the complete dock customization stack to a fresh pinned upstream tree.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/../.." && pwd)
source_dir=${1:?usage: prepare-source.sh UPSTREAM_SOURCE}
for patch in dock-drawers dock-workspace-startup dock-taskbar dock-taskbar-codexbar dock-taskbar-repobar dock-taskbar-power-buttons dock-taskbar-notifications; do
  git -C "$source_dir" apply "$repo/mseries/patches/$patch.patch"
done
git -C "$source_dir" apply "$repo/mseries/patches/dock-tooltip-optional-menu.patch"
cp "$here/TaskbarNotifications.vala" "$source_dir/src/TaskbarNotifications.vala"
cp "$here/TaskbarCodexBar.vala" "$source_dir/src/TaskbarCodexBar.vala"
cp "$repo/mseries/quick-settings/AirDropPanel.vala" "$source_dir/src/AirDropPanel.vala"
cp "$here/TaskbarAirDrop.vala" "$source_dir/src/TaskbarAirDrop.vala"
cp "$here/TaskbarT3.vala" "$source_dir/src/TaskbarT3.vala"
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
  "$source_dir/src/TaskbarT3RPopover.vala" "$source_dir/src/TaskbarT3.vala" "$source_dir/src/AirDropPanel.vala" \
  "$source_dir"/src/codexbar/*.vala "$source_dir"/src/repobar/*.vala > "$source_dir/.mseries-preserved.sha256"
git -C "$source_dir" apply "$repo/mseries/patches/dock-running-apps.patch"
git -C "$source_dir" apply "$repo/mseries/patches/dock-unique-launchers.patch"
git -C "$source_dir" apply "$repo/mseries/patches/dock-mode-geometry.patch"
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
# Replace the two taskbar status entries with one native T3 menu. Keep their
# sources linked for the shared JSON boundary and embedded repository view.
python3 - "$source_dir" <<'PYUNIFIED'
from pathlib import Path
import sys
root = Path(sys.argv[1])
p = root / 'src/Taskbar.vala'
s = p.read_text()
old = '        codexbar_group.append (new TaskbarCodexBar ());\n        var repobar = new TaskbarRepoBar () { margin_start = 6 };\n        codexbar_group.append (repobar);'
assert s.count(old) == 1, 'Unified T3 anchor replacement mismatch'
p.write_text(s.replace(old, '        codexbar_group.append (new TaskbarT3 ());'))
p = root / 'src/meson.build'
p.write_text(p.read_text().replace("    'TaskbarT3RPopover.vala',", "    'TaskbarT3RPopover.vala',\n    'TaskbarT3.vala',"))
PYUNIFIED
# Refuse a partial/stock rebuild instead of silently losing the Windows taskbar.
python3 - "$source_dir" <<'PY'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
for filename, required in {
    'src/meson.build': ['Taskbar.vala', 'StartMenu.vala', 'TaskbarCodexBar.vala', 'codexbar/Indicator.vala', 'TaskbarRepoBar.vala', 'repobar/Indicator.vala', 'TaskbarNotifications.vala', 'AirDropPanel.vala', 'TaskbarAirDrop.vala', 'TaskbarT3RPopover.vala'],
    'src/Taskbar.vala': ['new TaskbarT3', 'new TaskbarNotifications', 'new TaskbarAirDrop', 'end_box.append (status_box)'],
    'src/AppSystem/Launcher.vala': ['new TaskbarT3RPopover (this, app)', 't3r_popup.toggle_from_icon ()'],
    'src/TaskbarT3RPopover.vala': ['"tokenUsage"', '"usedPercent"', '"settings"', 'Timeout.add (250', 'Timeout.add (450'],
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

python3 - "$source_dir/src/AppSystem/Launcher.vala" <<'PYCODE'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
assert s.count('new TaskbarT3RPopover (this, app)') == 1
p.write_text(s.replace('new TaskbarT3RPopover (this, app)', 'new TaskbarT3RPopover (this, ItemManager.get_icon_size () * 7 / 12)'))
PYCODE

# Opt-in SDK status page. Default builds retain the existing status experience.
# The prefix contains include/msdk-usage.h and lib/libmsdk_gtk.so.
if [[ -n ${MSDK_USAGE_PREFIX:-} ]]; then
  [[ $MSDK_USAGE_PREFIX = /* && -f $MSDK_USAGE_PREFIX/include/msdk-usage.h && -f $MSDK_USAGE_PREFIX/lib/libmsdk_gtk.so ]] || {
    echo 'MSDK_USAGE_PREFIX must be an absolute SDK prefix with its header and library' >&2
    exit 1
  }
  cp "$repo/mseries/sdk-status-host/UsagePage.vala" "$source_dir/src/SdkUsagePage.vala"
  cp "$repo/mseries/sdk-status-host/msdk-usage.vapi" "$source_dir/src/msdk-usage.vapi"
  python3 - "$source_dir/src/meson.build" "$MSDK_USAGE_PREFIX" <<'PYSDK'
from pathlib import Path
import sys
p = Path(sys.argv[1])
prefix = Path(sys.argv[2])
s = p.read_text()
marker = 'executable(\n    meson.project_name(),'
assert s.count(marker) == 1, 'Dock executable declaration changed'
setup = f"sources += ['SdkUsagePage.vala']\ndependencies += declare_dependency(compile_args: ['-I' + {str(prefix / 'include')!r}], link_args: ['-L' + {str(prefix / 'lib')!r}, '-lmsdk_gtk', '-Wl,-rpath,' + {str(prefix / 'lib')!r}])\n\n"
s = s.replace(marker, setup + marker, 1)
target = '    dependencies: dependencies,\n    install: true'
assert s.count(target) == 1, 'Dock executable dependency declaration changed'
s = s.replace(target, "    dependencies: dependencies,\n    vala_args: ['--define=MSDK_STATUS_HOST', '--vapidir=' + meson.current_source_dir(), '--pkg=msdk-usage'],\n    install: true", 1)
p.write_text(s)
PYSDK
fi
