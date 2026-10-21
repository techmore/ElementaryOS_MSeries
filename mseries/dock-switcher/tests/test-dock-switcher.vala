/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Logic and settings tests for the Dock & Taskbar page. They compile fixture
 * schemas into a temporary directory and use the in-memory settings backend,
 * so they touch neither the live dock nor the user's configuration. */
using MSeriesDockSwitcher;

const string PATCHED_SCHEMA = """<?xml version="1.0" encoding="UTF-8"?>
<schemalist>
  <enum id="HideMode">
    <value nick='never' value='0'/>
    <value nick='maximized-focus-window' value='1'/>
    <value nick='overlapping-focus-window' value='2'/>
    <value nick='overlapping-window' value='3'/>
    <value nick='always' value='4'/>
  </enum>
  <schema path="/io/elementary/dock/" id="io.elementary.dock">
    <key enum="HideMode" name="autohide-mode"><default>'overlapping-focus-window'</default></key>
    <key type="i" name="icon-size"><default>48</default></key>
    <key type="b" name="taskbar-mode"><default>false</default></key>
  </schema>
</schemalist>""";

const string STOCK_SCHEMA = """<?xml version="1.0" encoding="UTF-8"?>
<schemalist>
  <enum id="HideMode">
    <value nick='never' value='0'/>
    <value nick='overlapping-focus-window' value='2'/>
  </enum>
  <schema path="/io/elementary/dock/" id="io.elementary.dock">
    <key enum="HideMode" name="autohide-mode"><default>'overlapping-focus-window'</default></key>
    <key type="i" name="icon-size"><default>48</default></key>
  </schema>
</schemalist>""";

string make_schema_dir (string xml) {
    string dir = "";
    try {
        dir = DirUtils.make_tmp ("msd-test-XXXXXX");
        FileUtils.set_contents (Path.build_filename (dir, "io.elementary.dock.gschema.xml"), xml);
        int status;
        Process.spawn_sync (null, { "glib-compile-schemas", dir }, null, SpawnFlags.SEARCH_PATH,
            null, null, null, out status);
        assert (status == 0);
    } catch (Error e) {
        stderr.printf ("fixture schema: %s\n", e.message);
        assert_not_reached ();
    }
    return dir;
}

string no_marker () {
    return Path.build_filename (Environment.get_tmp_dir (), "msd-test-no-such-marker");
}

void pump () {
    var context = MainContext.default ();
    while (context.pending ()) {
        context.iteration (false);
    }
}

void test_availability () {
    assert (availability (true, true, false) == Availability.READY);
    assert (availability (true, false, false) == Availability.NO_TASKBAR_SUPPORT);
    assert (availability (false, false, false) == Availability.NO_DOCK);
    /* The owner's opt-out wins over everything the schema says. */
    assert (availability (true, true, true) == Availability.DOCK_OFF);
    assert (availability (true, false, true) == Availability.DOCK_OFF);
    assert (can_choose (Availability.READY));
    assert (!can_choose (Availability.DOCK_OFF));
    assert (!can_choose (Availability.NO_TASKBAR_SUPPORT));
    assert (!can_choose (Availability.NO_DOCK));
    assert (banner_for (Availability.READY) == "");
    assert (banner_for (Availability.DOCK_OFF).contains ("user-disabled"));
    assert (banner_for (Availability.NO_TASKBAR_SUPPORT) != "");
}

void test_autohide_mapping () {
    assert (AUTOHIDE_NICKS.length == AUTOHIDE_LABELS.length);
    for (var i = 0; i < AUTOHIDE_NICKS.length; i++) {
        assert (autohide_index (AUTOHIDE_NICKS[i]) == i);
        assert (autohide_nick_at (i) == AUTOHIDE_NICKS[i]);
    }
    assert (autohide_index ("sometimes") == -1);
    assert (autohide_nick_at (-1) == null);
    assert (autohide_nick_at (AUTOHIDE_NICKS.length) == null);
    assert (style_name (Style.TASKBAR) == "Windows 11 taskbar");
    assert (switched_message (Style.DOCK) == "Switched to the elementary dock");
}

void test_patched_schema_switches_live () {
    var model = new DockModel (make_schema_dir (PATCHED_SCHEMA), false, no_marker ());
    assert (model.availability () == Availability.READY);
    assert (model.style == Style.DOCK);

    var notified = 0;
    model.changed.connect (() => notified++);
    assert (model.set_style (Style.TASKBAR));
    assert (model.style == Style.TASKBAR);
    pump ();
    assert (notified >= 1);

    assert (model.set_style (Style.DOCK));
    assert (model.style == Style.DOCK);
}

void test_autohide_round_trip () {
    var model = new DockModel (make_schema_dir (PATCHED_SCHEMA), false, no_marker ());
    assert (model.autohide == "overlapping-focus-window");
    assert (model.set_autohide ("always"));
    assert (model.autohide == "always");
    /* An unknown value is refused and leaves the setting alone. */
    assert (!model.set_autohide ("sometimes"));
    assert (model.autohide == "always");
}

void test_stock_dock_cannot_switch () {
    var model = new DockModel (make_schema_dir (STOCK_SCHEMA), false, no_marker ());
    assert (model.schema_found);
    assert (!model.has_taskbar_key);
    assert (model.availability () == Availability.NO_TASKBAR_SUPPORT);
    assert (model.style == Style.DOCK);
    assert (!model.set_style (Style.TASKBAR));
    assert (!model.set_autohide ("always"));
}

void test_missing_dock () {
    string empty = "";
    try {
        empty = DirUtils.make_tmp ("msd-test-XXXXXX");
    } catch (FileError e) {
        assert_not_reached ();
    }
    var model = new DockModel (empty, false, no_marker ());
    assert (!model.schema_found);
    assert (model.availability () == Availability.NO_DOCK);
    assert (!model.set_style (Style.TASKBAR));
}

void test_opt_out_marker () {
    var dir = make_schema_dir (PATCHED_SCHEMA);
    var marker = Path.build_filename (dir, "user-disabled");
    var model = new DockModel (dir, false, marker);
    assert (model.availability () == Availability.READY);
    try {
        FileUtils.set_contents (marker, "");
    } catch (FileError e) {
        assert_not_reached ();
    }
    model.refresh_marker ();
    assert (model.availability () == Availability.DOCK_OFF);
    FileUtils.remove (marker);
    model.refresh_marker ();
    assert (model.availability () == Availability.READY);
}

int main (string[] args) {
    Test.init (ref args);
    Test.add_func ("/state/availability", test_availability);
    Test.add_func ("/state/autohide-mapping", test_autohide_mapping);
    Test.add_func ("/model/patched-schema-switches-live", test_patched_schema_switches_live);
    Test.add_func ("/model/autohide-round-trip", test_autohide_round_trip);
    Test.add_func ("/model/stock-dock-cannot-switch", test_stock_dock_cannot_switch);
    Test.add_func ("/model/missing-dock", test_missing_dock);
    Test.add_func ("/model/opt-out-marker", test_opt_out_marker);
    return Test.run ();
}
