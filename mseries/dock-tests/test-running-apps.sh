#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/../.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT
source_dir=$test_dir/source
mkdir -p "$source_dir" "$test_dir/data/applications" "$test_dir/runtime" "$test_dir/schemas"
chmod 0700 "$test_dir/runtime"
if [[ -n ${MSERIES_DOCK_SOURCE:-} ]]; then
    git -C "$MSERIES_DOCK_SOURCE" archive 8b45a68a122947ad3a6427bf6e159ec2acf04ad0 | tar -x -C "$source_dir"
else
    git -C "$source_dir" init -q
    git -C "$source_dir" fetch -q --depth=1 https://github.com/elementary/dock.git 8b45a68a122947ad3a6427bf6e159ec2acf04ad0
    git -C "$source_dir" checkout -q --detach FETCH_HEAD
fi
bash "$repo/mseries/dock-taskbar/prepare-source.sh" "$source_dir"
cat > "$test_dir/schemas/io.elementary.dock.gschema.xml" <<'XML'
<schemalist><schema id="io.elementary.dock" path="/io/elementary/dock/">
<key name="launchers" type="as"><default>[]</default></key>
</schema></schemalist>
XML
glib-compile-schemas "$test_dir/schemas"
python3 - "$test_dir/data/applications" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
tools=root.parent/'tools'
tools.mkdir()
fixtures={
 'io.elementary.appcenter': ('appcenter','io.elementary.appcenter'),
 'chatgpt': ('chatgpt','Chatgpt'),
 'org.techmore.mseries.TeamsWeb': ('brave','brave-teams.microsoft.com__v2_-Default'),
 'org.techmore.mseries.OutlookWeb': ('brave','brave-outlook.office.com__mail_-Default'),
 'class-one': ('class-one-exec','SharedApplication'), 'class-two': ('class-two-exec','SharedApplication'),
 'CaseAlias': ('case-upper-exec',''), 'casealias': ('case-lower-exec',''),
 'odd-name': ('legacy-exec',''), 'flat-one': ('flatpak',''), 'flat-two': ('flatpak',''),
}
for name,(exe,wmclass) in fixtures.items():
 executable=tools/exe
 if not executable.exists(): executable.symlink_to('/usr/bin/true')
 (root/(name+'.desktop')).write_text(f'[Desktop Entry]\nType=Application\nName={name}\nExec={executable}\nStartupWMClass={wmclass}\n')
PY
if ! valac --pkg gio-2.0 --pkg gio-unix-2.0 --directory="$test_dir" --main=RunningTest.main -o "$test_dir/running" \
    "$source_dir/src/AppSystem/AppResolver.vala" "$source_dir/src/AppSystem/AppSystem.vala" \
    "$here/running-app-stubs.vala" > "$test_dir/build.log" 2>&1; then
    cat "$test_dir/build.log" >&2
    exit 1
fi
XDG_DATA_HOME="$test_dir/data" XDG_DATA_DIRS="$test_dir/empty" XDG_RUNTIME_DIR="$test_dir/runtime" \
GSETTINGS_SCHEMA_DIR="$test_dir/schemas" GSETTINGS_BACKEND=memory G_DEBUG=fatal-criticals "$test_dir/running"
