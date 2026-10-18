/* Isolated EDS integration test; only synthetic sources on a private D-Bus. */
[CCode (has_target = false)]
public delegate Wingpanel.Indicator? IndicatorFactory (Module module, Wingpanel.ServerType server);

class AgendaTest : Object {
    Wingpanel.Indicator indicator;
    Gtk.Widget widget;
    E.SourceRegistry registry;
    ECal.Client events;
    ECal.Client events2;
    ECal.Client tasks;
    MainLoop loop;
    int result = 1;

    async ECal.Client create_source (string uid, ECal.ClientSourceType type) throws Error {
        var source = new E.Source.with_uid (uid, null);
        source.display_name = uid;
        source.parent = "local-stub";
        stderr.printf ("Creating %s\n", uid);
        string extension = type == ECal.ClientSourceType.TASKS ? E.SOURCE_EXTENSION_TASK_LIST : E.SOURCE_EXTENSION_CALENDAR;
        var selectable = (E.SourceSelectable) source.get_extension (extension);
        selectable.backend_name = "local";
        selectable.selected = true;
        registry.commit_source_sync (source, null);
        stderr.printf ("Connecting %s\n", uid);
        return (ECal.Client) yield ECal.Client.connect (registry.ref_source (uid), type, 10, null);
    }

    string todo (string title, bool complete = false, string dates = "") {
        return "BEGIN:VTODO\r\nUID:test-task\r\nSUMMARY:" + title + "\r\n" + dates +
            (complete ? "STATUS:COMPLETED\r\nPERCENT-COMPLETE:100\r\nCOMPLETED:20261018T120000Z\r\n" : "") + "END:VTODO\r\n";
    }

    string event (string title) {
        var now = new GLib.DateTime.now_local ();
        var day = now.format ("%Y%m%d");
        return "BEGIN:VEVENT\r\nUID:shared-event\r\nSUMMARY:" + title +
            "\r\nDTSTART;VALUE=DATE:" + day + "\r\nDTEND;VALUE=DATE:" + now.add_days (1).format ("%Y%m%d") + "\r\nEND:VEVENT\r\n";
    }

    void add (ECal.Client client, string text) throws Error {
        string uid;
        client.create_object_sync (new ICal.Component.from_string (text), ECal.OperationFlags.NONE, out uid, null);
    }

    bool contains (Gtk.Widget node, string title) {
        if (node is Gtk.Label && ((Gtk.Label) node).label == title) return true;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            if (contains (child, title)) return true;
        }
        return false;
    }

    Gtk.Stack? find_stack (Gtk.Widget node) {
        if (node is Gtk.Stack && ((Gtk.Stack) node).get_child_by_name ("tasks") != null) return (Gtk.Stack) node;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            var stack = find_stack (child);
            if (stack != null) return stack;
        }
        return null;
    }

    Gtk.Button? find_button (Gtk.Widget node, string icon) {
        if (node is Gtk.Button && (((Gtk.Button) node).icon_name == icon ||
            (icon == "office-calendar-symbolic" && ((Gtk.Button) node).label == "Today"))) return (Gtk.Button) node;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            var button = find_button (child, icon);
            if (button != null) return button;
        }
        return null;
    }

    Gtk.Widget? find_day (Gtk.Widget node, GLib.DateTime date) {
        if (node.get_type ().name () == "DateTimeWidgetsGridDay") {
            GLib.DateTime day;
            node.get ("date", out day);
            if (day.get_year () == date.get_year () && day.get_day_of_year () == date.get_day_of_year ()) return node;
        }
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            var day = find_day (child, date);
            if (day != null) return day;
        }
        return null;
    }

    async void navigation_checks () throws Error {
        var today = new GLib.DateTime.now_local ();
        var other = today.get_day_of_month () == 1 ? today.add_days (1) : today.add_days (-1);
        var day = find_day (widget, other);
        assert (day != null);
        var controllers = day.observe_controllers ();
        for (uint i = 0; i < controllers.get_n_items (); i++) {
            var controller = controllers.get_item (i);
            if (controller is Gtk.EventControllerFocus) Signal.emit_by_name (controller, "enter");
        }
        yield expect ("Second calendar same UID", false);
        var today_button = find_button (widget, "office-calendar-symbolic");
        assert (today_button != null);
        today_button.clicked ();
        yield expect ("Second calendar same UID");
        for (int i = 0; i < 3; i++) today_button.clicked ();
        yield expect ("Second calendar same UID");
        var next = find_button (widget, "pan-end-symbolic");
        var previous = find_button (widget, "pan-start-symbolic");
        for (int pass = 0; pass < 2; pass++) {
            for (int i = 0; i < 3; i++) {
                (pass == 0 ? next : previous).clicked ();
                for (int n = 0; n < 12; n++) yield pause ();
            }
            today_button.clicked ();
            today_button.clicked ();
            today_button.clicked ();
            for (int n = 0; n < 12; n++) yield pause ();
            yield expect (today.format ("%OB, %Y"));
            yield expect ("Second calendar same UID");
            today_button.clicked ();
            yield expect ("Second calendar same UID");
        }
        next.clicked ();
        for (int n = 0; n < 12; n++) yield pause ();
        yield expect (today.add_months (1).format ("%OB, %Y"));
        today_button.clicked ();
        for (int n = 0; n < 12; n++) yield pause ();
        yield expect (today.format ("%OB, %Y"));
        yield expect ("Second calendar same UID");
        stdout.printf ("PASS Today restores selected day and events after repeated clicks and month navigation\n");
    }

    async void pause () {
        Timeout.add (50, () => { pause.callback (); return Source.REMOVE; });
        yield;
    }

    void dump_labels (Gtk.Widget node) {
        if (node is Gtk.Label) stderr.printf ("LABEL %s\n", ((Gtk.Label) node).label);
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) dump_labels (child);
    }

    async void expect (string title, bool present = true) throws Error {
        for (int n = 0; n < 200; n++) {
            if (contains (widget, title) == present) return;
            yield pause ();
        }
        dump_labels (widget);
        throw new IOError.FAILED ("Expected '%s' present=%s".printf (title, present.to_string ()));
    }

    void preview (Gtk.Window window, string name) {
        var directory = Environment.get_variable ("AGENDA_PREVIEW_DIR");
        if (directory == null) return;
        var paintable = new Gtk.WidgetPaintable (widget);
        var snapshot = new Gtk.Snapshot ();
        paintable.snapshot (snapshot, widget.get_width (), widget.get_height ());
        var node = snapshot.to_node ();
        if (node != null) {
            var texture = window.get_renderer ().render_texture (node, null);
            texture.save_to_png (Path.build_filename (directory, name + ".png"));
        }
    }

    async void run () {
        try {
            registry = new E.SourceRegistry.sync (null);
            events = yield create_source ("agenda-test-events", ECal.ClientSourceType.EVENTS);
            events2 = yield create_source ("agenda-test-events-two", ECal.ClientSourceType.EVENTS);
            tasks = yield create_source ("agenda-test-tasks", ECal.ClientSourceType.TASKS);
            stderr.printf ("Creating fixtures\n");
            add (events, event ("First calendar"));
            add (events2, event ("Second calendar same UID"));
            add (tasks, todo ("Undated task"));
            var due = new GLib.DateTime.now_utc ().add_days (2).format ("%Y%m%dT%H%M%SZ");
            add (tasks, todo ("Due-only task", false, "DUE:" + due + "\r\n").replace ("UID:test-task", "UID:dated-task"));
            stderr.printf ("Constructing widget\n");
            widget = indicator.get_widget ();
            var window = new Gtk.Window () { child = widget };
            window.present ();
            yield pause ();
            indicator.opened ();
            yield expect ("Events");
            yield expect ("Tasks");
            yield expect ("Calendar Accounts…");
            yield expect ("First calendar");
            yield expect ("Second calendar same UID");
            yield navigation_checks ();
            preview (window, "calendar-events");
            find_stack (widget).visible_child_name = "tasks";
            yield expect ("Undated task");
            yield expect ("Due-only task");
            for (int i = 0; i < 5; i++) yield pause ();
            preview (window, "calendar-tasks");
            stdout.printf ("PASS tabs, separate calendars with shared UID, undated task\n");

            events.modify_object_sync (new ICal.Component.from_string (event ("Updated event")), ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
            yield expect ("Updated event");
            yield expect ("First calendar", false);
            tasks.modify_object_sync (new ICal.Component.from_string (todo ("Updated task")), ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
            yield expect ("Updated task");
            yield expect ("Undated task", false);
            stdout.printf ("PASS event/task modifications\n");

            tasks.modify_object_sync (new ICal.Component.from_string (todo ("Completed task", true)), ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
            yield expect ("Updated task", false);
            tasks.remove_object_sync ("dated-task", null, ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
            yield expect ("Due-only task", false);
            yield expect ("No incomplete tasks");
            events.remove_object_sync ("shared-event", null, ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
            yield expect ("Updated event", false);
            yield expect ("Second calendar same UID");
            stdout.printf ("PASS completion/deletion without losing another calendar\n");

            var source = registry.ref_source ("agenda-test-events-two");
            source.enabled = false;
            source.write_sync (null);
            yield expect ("Second calendar same UID", false);
            source.enabled = true;
            source.write_sync (null);
            yield expect ("Second calendar same UID");
            stdout.printf ("PASS source enable/disable discovered live\n");
            var late = yield create_source ("agenda-late-account", ECal.ClientSourceType.EVENTS);
            add (late, event ("New account event"));
            yield expect ("New account event");
            registry.ref_source ("agenda-late-account").remove_sync (null);
            yield expect ("New account event", false);
            stdout.printf ("PASS account source added/removed after opening\n");
            indicator.closed ();
            indicator.opened ();
            yield expect ("Second calendar same UID");
            result = 0;
        } catch (Error e) { stderr.printf ("FAIL: %s\n", e.message); }
        loop.quit ();
    }

    public int execute (string library) {
        var module = Module.open (library, ModuleFlags.LAZY);
        assert (module != null);
        module.make_resident ();
        void* symbol;
        assert (module.symbol ("get_indicator", out symbol));
        var factory = (IndicatorFactory) symbol;
        indicator = factory (module, Wingpanel.ServerType.SESSION);
        loop = new MainLoop ();
        run.begin ();
        loop.run ();
        return result;
    }
}

int main (string[] args) {
    Gtk.init ();
    Adw.init ();
    return new AgendaTest ().execute (args[1]);
}
