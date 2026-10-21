#!/usr/bin/env bash
# Compile the exact dock policy methods added by the production patch.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
python3 - "$repo/mseries/patches/dock-taskbar.patch" "$work/test.vala" <<'PY'
import pathlib, sys
added = '\n'.join(line[1:] for line in pathlib.Path(sys.argv[1]).read_text().splitlines()
                  if line.startswith(('+', ' ')) and not line.startswith('+++'))
def method(signature):
    start = added.index(signature)
    opening = added.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (added[end] == '{') - (added[end] == '}')
        end += 1
    return added[start:end]
text = 'class ItemManager : Object {\n private static Settings? settings;\n'
text += method('private static bool size_system_managed ()') + '\n'
text += method('public static int get_icon_size ()') + '\n}\n'
text += r'''
void policy (string contents) {
    try { FileUtils.set_contents (Path.build_filename (Environment.get_user_state_dir (),
        "mseries", "ui-scale-policy.ini"), contents); }
    catch (Error e) { error ("%s", e.message); }
}
int main () {
    DirUtils.create_with_parents (Path.build_filename (Environment.get_user_state_dir (), "mseries"), 0700);
    var settings = new Settings ("io.elementary.dock");
    settings.set_int ("icon-size", 40);
    settings.set_boolean ("taskbar-mode", true);
    assert (ItemManager.get_icon_size () == 48);
    policy ("[SizeSystem]\nversion=1\nmanaged=true\n");
    foreach (var size in new int[] { 32, 36, 40, 44, 48, 52, 56, 60, 72 }) {
        settings.set_int ("icon-size", size);
        foreach (var taskbar in new bool[] { true, false }) {
            settings.set_boolean ("taskbar-mode", taskbar);
            assert (ItemManager.get_icon_size () == size);
        }
    }
    settings.set_boolean ("taskbar-mode", true);
    policy ("[SizeSystem]\nversion=2\nmanaged=true\n");
    assert (ItemManager.get_icon_size () == 48);
    policy ("invalid");
    assert (ItemManager.get_icon_size () == 48);
    policy ("[SizeSystem]\nversion=1\nmanaged=false\n");
    assert (ItemManager.get_icon_size () == 48);
    settings.set_boolean ("taskbar-mode", false);
    assert (ItemManager.get_icon_size () == 72);
    stdout.printf ("PASS: compiled dock policy follows managed tokens; missing/invalid/unmanaged taskbar stays48\n");
    return 0;
}
'''
pathlib.Path(sys.argv[2]).write_text(text)
PY
cat > "$work/dock.gschema.xml" <<'SCHEMA'
<schemalist><schema id="io.elementary.dock" path="/io/elementary/dock/">
<key name="icon-size" type="i"><default>48</default></key>
<key name="taskbar-mode" type="b"><default>false</default></key>
</schema></schemalist>
SCHEMA
glib-compile-schemas "$work"
valac --pkg gio-2.0 "$work/test.vala" -o "$work/test" > "$work/build.log" 2>&1 || { cat "$work/build.log"; exit 1; }
XDG_STATE_HOME="$work/state" GSETTINGS_SCHEMA_DIR="$work" GSETTINGS_BACKEND=memory "$work/test"
