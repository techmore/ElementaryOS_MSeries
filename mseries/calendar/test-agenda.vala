/* Isolated EDS integration test; only synthetic sources on a private D-Bus. */
[CCode (has_target = false)]
public delegate Wingpanel.Indicator? IndicatorFactory (Module module, Wingpanel.ServerType server);
[CCode (has_target = false)]
public delegate int VerseIndex (GLib.DateTime day, int count);

class AgendaTest : Object {
    Wingpanel.Indicator indicator;
    VerseIndex verse_index;
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
        assert ((find_day (widget, today).get_state_flags () & Gtk.StateFlags.SELECTED) != 0);
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

    Gtk.Widget? named (Gtk.Widget node, string name) {
        if (node.name == name) return node;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            var found = named (child, name);
            if (found != null) return found;
        }
        return null;
    }

    void choose_view (string mode) {
        ((Gtk.ToggleButton) named (widget, "agenda-" + mode)).active = true;
    }

    void period_move (bool next) {
        ((Gtk.Button) named (widget, next ? "agenda-next" : "agenda-previous")).clicked ();
    }

    Gtk.Widget active_events () {
        return named (widget, "agenda-time-grid").get_child_visible () &&
            ((Gtk.Stack) named (widget, "agenda-surface")).visible_child_name == "time" ?
            named (widget, "agenda-time-grid") : named (widget, "agenda-events");
    }

    Gtk.Widget? time_event (Gtk.Widget node, string title) {
        if (node.get_type ().name () == "DateTimeWidgetsTimeEvent" && contains (node, title)) return node;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            var found = time_event (child, title);
            if (found != null) return found;
        }
        return null;
    }

    Gtk.MenuButton? menu_in (Gtk.Widget node) {
        if (node is Gtk.MenuButton) return (Gtk.MenuButton) node;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            var menu = menu_in (child);
            if (menu != null) return menu;
        }
        return null;
    }

    int count_title (Gtk.Widget node, string title) {
        int count = node is Gtk.Label && ((Gtk.Label) node).label == title ? 1 : 0;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) count += count_title (child, title);
        return count;
    }

    string dated_event (string uid, string title, GLib.DateTime start, GLib.DateTime end, string extra = "") {
        return "BEGIN:VEVENT\r\nUID:" + uid + "\r\nSUMMARY:" + title +
            "\r\nDTSTART;VALUE=DATE:" + start.format ("%Y%m%d") +
            "\r\nDTEND;VALUE=DATE:" + end.format ("%Y%m%d") + "\r\n" + extra + "END:VEVENT\r\n";
    }

    async void upcoming_checks () throws Error {
        var now = new GLib.DateTime.now_local ();
        var today = new GLib.DateTime.local (now.get_year (), now.get_month (), now.get_day_of_month (), 0, 0, 0);
        add (events, dated_event ("upcoming-tomorrow", "Upcoming tomorrow", today.add_days (1), today.add_days (2)));
        add (events, dated_event ("upcoming-end", "Last upcoming day", today.add_days (29), today.add_days (30)));
        add (events, dated_event ("upcoming-outside", "Outside upcoming range", today.add_days (30), today.add_days (31)));
        add (events, dated_event ("upcoming-past", "Ended yesterday", today.add_days (-1), today));
        add (events, dated_event ("upcoming-ongoing", "Still ongoing", today.add_days (-1), today.add_days (2)));
        assert (((Gtk.ToggleButton) named (widget, "agenda-upcoming")).active);
        yield expect ("Upcoming · next 30 days");
        yield expect ("Upcoming tomorrow");
        yield expect ("Last upcoming day");
        yield expect ("Still ongoing");
        yield expect ("Outside upcoming range", false);
        yield expect ("Ended yesterday", false);
        assert (!named (widget, "agenda-previous").visible);
        var next = find_button (widget, "pan-end-symbolic");
        next.clicked ();
        for (int i = 0; i < 12; i++) yield pause ();
        yield expect ("Upcoming tomorrow");
        yield expect ("Last upcoming day");
        find_button (widget, "office-calendar-symbolic").clicked ();
        stdout.printf ("PASS default Upcoming, month boundary, ongoing/past exclusion and calendar browsing\n");
    }

    async void view_checks (Gtk.Window window) throws Error {
        var now = new GLib.DateTime.now_local ();
        var today = new GLib.DateTime.local (now.get_year (), now.get_month (), now.get_day_of_month (), 0, 0, 0);
        var month = today.add_days (1 - today.get_day_of_month ());
        var next_month = month.add_months (1);
        // The fixture runs in C.UTF-8: Sunday is the first day of the week.
        var week = today.add_days (-(today.get_day_of_week () % 7));
        add (events, dated_event ("month-first", "Month first event", month, month.add_days (1)));
        add (events, dated_event ("month-last", "Month last event", next_month.add_days (-1), next_month));
        add (events, dated_event ("outside-month", "Outside month event", next_month, next_month.add_days (1)));
        add (events, dated_event ("week-first", "Week first event", week, week.add_days (1)));
        add (events, dated_event ("week-last", "Week last event", week.add_days (6), week.add_days (7)));
        add (events, dated_event ("outside-week", "Outside week event", week.add_days (7), week.add_days (8)));
        add (events, dated_event ("tomorrow", "Tomorrow event", today.add_days (1), today.add_days (2)));
        add (events, dated_event ("multi-day", "Multi-day event", today.add_days (-1), today.add_days (2)));
        add (events, dated_event ("recurring", "Recurring event", today, today.add_days (1), "RRULE:FREQ=DAILY;COUNT=3\r\n"));
        var start = today.add_hours (10);
        add (events, "BEGIN:VEVENT\r\nUID:timed-detail\r\nSUMMARY:Detailed meeting\r\nDTSTART:" +
            start.to_utc ().format ("%Y%m%dT%H%M%SZ") + "\r\nDTEND:" + start.add_hours (1).to_utc ().format ("%Y%m%dT%H%M%SZ") +
            "\r\nLOCATION:Room <A> & B\r\nDESCRIPTION:Discuss <scope> & next steps\r\nEND:VEVENT\r\n");
        find_stack (widget).visible_child_name = "events";
        choose_view ("day");
        yield expect ("Detailed meeting");
        var detail_menu = menu_in (time_event (active_events (), "Detailed meeting"));
        detail_menu.popup ();
        yield expect ("Room <A> & B");
        yield expect ("Discuss <scope> & next steps");
        yield expect ("agenda-test-events");
        yield expect ("All day");
        yield expect ("Tomorrow event", false);
        assert (count_title (active_events (), "Multi-day event") == 1);
        assert (count_title (active_events (), "Recurring event") == 1);
        for (int n = 0; n < 5; n++) yield pause ();
        preview (window, "agenda-day");
        detail_menu.popdown ();
        var scroll = (Gtk.ScrolledWindow) named (widget, "calendar-time-scroll");
        scroll.vadjustment.value = 480;
        for (int n = 0; n < 5; n++) yield pause ();
        preview (window, "agenda-day-details");
        period_move (true);
        yield expect ("Tomorrow event");
        yield expect ("Detailed meeting", false);
        period_move (false);
        yield expect ("Detailed meeting");
        stdout.printf ("PASS Day details, literal text, all-day/multi-day/recurring events and period navigation\n");

        choose_view ("week");
        yield wait_grid (7, today.add_days (-(today.get_day_of_week () % 7)));
        yield expect ("Week first event");
        yield expect ("Week last event");
        yield expect ("Outside week event", false);
        var expected = int.min (3, 7 - (int) (today.get_day_of_week () % 7));
        assert (count_title (active_events (), "Recurring event") == expected);
        for (int n = 0; n < 5; n++) yield pause ();
        preview (window, "agenda-week");
        period_move (true);
        yield expect ("Outside week event");
        yield expect ("Week first event", false);
        period_move (false);
        yield expect ("Week first event");
        stdout.printf ("PASS Week boundaries, recurring instances and previous/next week\n");

        choose_view ("month");
        yield expect ("Month first event");
        yield expect ("Month last event");
        yield expect ("Outside month event", false);
        var multi_first = today.add_days (-1).compare (month) < 0 ? month : today.add_days (-1);
        var multi_end = today.add_days (2).compare (next_month) > 0 ? next_month : today.add_days (2);
        assert (count_title (active_events (), "Multi-day event") == (int) (multi_end.difference (multi_first) / TimeSpan.DAY));
        for (int n = 0; n < 5; n++) yield pause ();
        preview (window, "agenda-month");
        period_move (true);
        yield expect ("Outside month event");
        yield expect ("Month first event", false);
        period_move (false);
        yield expect ("Month first event");
        stdout.printf ("PASS Month boundaries, grouped multi-day events and previous/next month\n");

        // Cross December/January and reopen while retaining the selected view.
        for (int i = today.get_month (); i < 12; i++) {
            period_move (true);
            for (int n = 0; n < 3; n++) yield pause ();
        }
        period_move (true);
        for (int n = 0; n < 5; n++) yield pause ();
        var heading = (Gtk.Label) named (widget, "agenda-period");
        assert (heading.label == new GLib.DateTime.local (today.get_year () + 1, 1, 1, 0, 0, 0).format ("%B %Y"));
        yield expect ("No events this month");
        choose_view ("week");
        yield expect ("No events this week");
        choose_view ("day");
        yield expect ("No events this day");
        choose_view ("month");
        find_button (widget, "office-calendar-symbolic").clicked ();
        yield expect ("Month first event");
        indicator.closed (); indicator.opened ();
        yield expect ("Month first event");
        assert (((Gtk.ToggleButton) named (widget, "agenda-month")).active);
        find_stack (widget).visible_child_name = "tasks";
        yield expect ("Undated task");
        find_stack (widget).visible_child_name = "events";
        choose_view ("day");
        yield expect ("Detailed meeting");
        // Live changes must remain visible in the wider views, too.
        choose_view ("month");
        events.modify_object_sync (new ICal.Component.from_string (dated_event ("month-last", "Updated month event", next_month.add_days (-1), next_month)), ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
        yield expect ("Updated month event");
        yield expect ("Month last event", false);
        events.remove_object_sync ("month-last", null, ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
        yield expect ("Updated month event", false);
        choose_view ("day");
        yield expect ("Detailed meeting");
        stdout.printf ("PASS year boundary, view retention, independent Tasks and live wider-view updates\n");
    }

    string timed_event_text (string uid, string title, GLib.DateTime start, GLib.DateTime end, string extra = "") {
        return "BEGIN:VEVENT\r\nUID:" + uid + "\r\nSUMMARY:" + title + "\r\nDTSTART:" +
            start.to_utc ().format ("%Y%m%dT%H%M%SZ") + "\r\nDTEND:" + end.to_utc ().format ("%Y%m%dT%H%M%SZ") +
            "\r\n" + extra + "END:VEVENT\r\n";
    }

    Gtk.Button? label_button (Gtk.Widget node, string label) {
        if (node is Gtk.Button && ((Gtk.Button) node).label == label) return (Gtk.Button) node;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            var result = label_button (child, label);
            if (result != null) return result;
        }
        return null;
    }

    void assert_minutes (Gtk.Widget block, double start, double end) {
        assert (block != null);
        double actual_start, actual_end;
        block.get ("start-minute", out actual_start, "end-minute", out actual_end);
        assert (Math.fabs (actual_start - start) < 0.01 && Math.fabs (actual_end - end) < 0.01);
    }

    async void wait_minutes (string title, double start, double end) throws Error {
        for (int i = 0; i < 200; i++) {
            var block = time_event (active_events (), title);
            if (block != null) {
                double a, b;
                block.get ("start-minute", out a, "end-minute", out b);
                if (Math.fabs (a - start) < 0.01 && Math.fabs (b - end) < 0.01) return;
            }
            yield pause ();
        }
        var canvas = named (widget, "calendar-time-canvas");
        stderr.printf ("RANGE EXPECT %s %.1f–%.1f\n", title, start, end);
        for (var child = canvas.get_first_child (); child != null; child = child.get_next_sibling ()) {
            if (child.get_type ().name () == "DateTimeWidgetsTimeEvent") {
                double a, b;
                child.get ("start-minute", out a, "end-minute", out b);
                stderr.printf ("BLOCK %s %.1f–%.1f\n", child.tooltip_text, a, b);
            }
        }
        throw new IOError.FAILED ("Timed range did not settle for %s".printf (title));
    }

    async void wait_grid (int days, GLib.DateTime first) throws Error {
        for (int i = 0; i < 200; i++) {
            int actual_days; string actual_date;
            named (widget, "agenda-time-grid").get ("day-count", out actual_days, "start-date", out actual_date);
            if (actual_days == days && actual_date == first.format ("%F")) {
                for (int n = 0; n < 5; n++) yield pause ();
                return;
            }
            yield pause ();
        }
        throw new IOError.FAILED ("Time grid view did not settle");
    }

    async void time_grid_checks (Gtk.Window window) throws Error {
        var now = new GLib.DateTime.now_local ();
        var today = new GLib.DateTime.local (now.get_year (), now.get_month (), now.get_day_of_month (), 0, 0, 0);
        choose_view ("day");
        ((Gtk.Button) named (widget, "grid-today")).clicked ();
        add (events, timed_event_text ("grid-a", "Overlap A", today.add_hours (9), today.add_hours (10)));
        add (events, timed_event_text ("grid-b", "Overlap B", today.add_hours (9).add_minutes (30), today.add_hours (10).add_minutes (30)));
        add (events, timed_event_text ("grid-c", "Overlap C", today.add_hours (9).add_minutes (45), today.add_hours (10).add_minutes (15)));
        add (events, timed_event_text ("grid-touch", "Adjacent event", today.add_hours (11), today.add_hours (12)));
        add (events, timed_event_text ("grid-short", "Short event", today.add_hours (12), today.add_hours (12).add_minutes (5)));
        add (events, timed_event_text ("grid-short-two", "Nearby short event", today.add_hours (12).add_minutes (10), today.add_hours (12).add_minutes (20)));
        add (events, timed_event_text ("grid-zero", "Instant event", today.add_hours (13), today.add_hours (13)));
        add (events, timed_event_text ("grid-late", "Ends at midnight", today.add_hours (23).add_minutes (55), today.add_days (1)));
        add (events, timed_event_text ("grid-night", "Overnight event", today.add_hours (23), today.add_days (1).add_hours (1)));
        add (events, timed_event_text ("grid-repeat", "Timed recurring event", today.add_hours (14), today.add_hours (14).add_minutes (30), "RRULE:FREQ=DAILY;COUNT=3\r\n"));
        var duration_start = today.add_hours (17).add_minutes (30);
        var duration_end = today.add_hours (19);
        add (events, timed_event_text ("grid-duration", "Duration event", duration_start, duration_end).replace (
            "DTEND:" + duration_end.to_utc ().format ("%Y%m%dT%H%M%SZ"), "DURATION:PT90M"));
        add (events, timed_event_text ("grid-untitled", "No title", today.add_hours (18), today.add_hours (18).add_minutes (30)).replace ("SUMMARY:No title\r\n", ""));
        for (int i = 0; i < 5; i++) add (events, timed_event_text ("busy-" + i.to_string (), "Busy " + i.to_string (), today.add_hours (16), today.add_hours (17)));
        yield expect ("Busy 4");
        yield expect ("Instant event");
        yield expect ("Untitled event");
        yield wait_minutes ("Duration event", 1050, 1140);
        for (int n = 0; n < 8; n++) yield pause ();
        var canvas = (Gtk.Fixed) named (widget, "calendar-time-canvas");
        var a = time_event (active_events (), "Overlap A");
        var b = time_event (active_events (), "Overlap B");
        var c = time_event (active_events (), "Overlap C");
        assert_minutes (a, 540, 600);
        assert_minutes (b, 570, 630);
        int lanes;
        a.get ("lane-count", out lanes); assert (lanes == 3);
        double ax, ay, bx, by, cx, cy, tx, ty;
        canvas.get_child_position (a, out ax, out ay);
        canvas.get_child_position (b, out bx, out by);
        canvas.get_child_position (c, out cx, out cy);
        canvas.get_child_position (named (widget, "time-slot-9"), out tx, out ty);
        assert (Math.fabs (ay - ty) < 0.01 && Math.fabs (by - ay - 30) < 0.01);
        assert (a.get_height () == 60);
        assert (ax + a.get_width () <= bx + 1 && bx + b.get_width () <= cx + 1);
        time_event (active_events (), "Adjacent event").get ("lane-count", out lanes); assert (lanes == 1);
        time_event (active_events (), "Short event").get ("lane-count", out lanes); assert (lanes == 2);
        yield wait_minutes ("Overnight event", 1380, 1440);
        // The final five-minute block is clipped without a label's minimum
        // height extending past the midnight boundary; its tooltip remains.
        var late_canvas = (Gtk.Fixed) named (widget, "calendar-time-canvas");
        Gtk.Widget? late_block = null;
        for (var child = late_canvas.get_first_child (); child != null; child = child.get_next_sibling ()) {
            if (child.get_type ().name () == "DateTimeWidgetsTimeEvent" && child.tooltip_text != null &&
                child.tooltip_text.has_prefix ("Ends at midnight\n")) late_block = child;
        }
        assert (late_block != null);
        assert_minutes (late_block, 1435, 1440);
        assert (late_block.get_height () == 5);
        var scroll = (Gtk.ScrolledWindow) named (widget, "calendar-time-scroll");
        scroll.vadjustment.value = 510;
        for (int n = 0; n < 5; n++) yield pause ();
        preview (window, "time-grid-day-overlap");
        stdout.printf ("PASS actual timed-block geometry, overlap lanes, adjacent/short/instant events\n");

        // Live edits recalculate lanes and keep the current reading position.
        events.modify_object_sync (new ICal.Component.from_string (timed_event_text ("grid-b", "Moved overlap B", today.add_hours (15), today.add_hours (16))), ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
        yield expect ("Moved overlap B");
        for (int n = 0; n < 5; n++) yield pause ();
        a = time_event (active_events (), "Overlap A");
        a.get ("lane-count", out lanes); assert (lanes == 2);
        scroll = (Gtk.ScrolledWindow) named (widget, "calendar-time-scroll");
        assert (Math.fabs (scroll.vadjustment.value - 510) < 1);
        events.remove_object_sync ("grid-c", null, ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
        yield expect ("Overlap C", false);
        for (int n = 0; n < 5; n++) yield pause ();
        time_event (active_events (), "Overlap A").get ("lane-count", out lanes); assert (lanes == 1);
        stdout.printf ("PASS live block moves/deletion, lane reflow and retained scroll position\n");

        period_move (true);
        yield expect ("Overnight event");
        for (int n = 0; n < 5; n++) yield pause ();
        yield wait_minutes ("Overnight event", 0, 60);
        assert (contains (time_event (active_events (), "Overnight event"), "00:00"));
        yield expect ("Overlap A", false);
        period_move (false);
        yield expect ("Overlap A");
        choose_view ("week");
        yield wait_grid (7, today.add_days (-(today.get_day_of_week () % 7)));
        yield expect ("Week first event");
        for (int n = 0; n < 8; n++) yield pause ();
        assert (count_title (active_events (), "Timed recurring event") == int.min (3, 7 - (int) (today.get_day_of_week () % 7)));
        var busy = time_event (active_events (), "Busy 0");
        busy.get ("lane-count", out lanes); assert (lanes == 5);
        canvas = (Gtk.Fixed) named (widget, "calendar-time-canvas");
        Gtk.Widget previous = busy;
        double px, py, nx, ny;
        for (int i = 1; i < 5; i++) {
            var next = time_event (active_events (), "Busy " + i.to_string ());
            // Sorting equal intervals is stable in the production ArrayList.
            canvas.get_child_position (previous, out px, out py);
            canvas.get_child_position (next, out nx, out ny);
            assert (Math.fabs (px - nx) >= int.min (previous.get_width (), next.get_width ()) - 1);
            previous = next;
        }
        scroll = (Gtk.ScrolledWindow) named (widget, "calendar-time-scroll");
        scroll.vadjustment.value = 510;
        int minimum, natural;
        widget.measure (Gtk.Orientation.HORIZONTAL, -1, out minimum, out natural, null, null);
        assert (minimum <= 800 && natural <= 800);
        window.set_default_size (natural, -1);
        for (int n = 0; n < 5; n++) yield pause ();
        var horizontal = (Gtk.ScrolledWindow) named (widget, "calendar-horizontal-scroll");
        assert (horizontal.hadjustment.upper > horizontal.hadjustment.page_size);
        horizontal.hadjustment.value = 100;
        events.modify_object_sync (new ICal.Component.from_string (timed_event_text ("busy-4", "Updated busy 4", today.add_hours (16), today.add_hours (17))), ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
        yield expect ("Updated busy 4");
        for (int n = 0; n < 5; n++) yield pause ();
        horizontal = (Gtk.ScrolledWindow) named (widget, "calendar-horizontal-scroll");
        assert (Math.fabs (horizontal.hadjustment.value - 100) < 1);
        horizontal.hadjustment.value = 0;
        for (int n = 0; n < 5; n++) yield pause ();
        preview (window, "time-grid-week-overlap");
        stdout.printf ("PASS overnight clipping, recurring week columns and crowded overlap blocks\n");

        choose_view ("day");
        yield wait_grid (1, today);
        yield expect ("Detailed meeting");
        ((Gtk.ScrolledWindow) named (widget, "calendar-time-scroll")).vadjustment.value = 510;
        for (int n = 0; n < 5; n++) yield pause ();
        var menu = menu_in (time_event (active_events (), "Detailed meeting"));
        menu.popup ();
        yield expect ("Room <A> & B");
        yield expect ("Discuss <scope> & next steps");
        for (int n = 0; n < 5; n++) yield pause ();
        assert (menu.popover.get_mapped ());
        preview (window, "time-grid-details");
        var preview_dir = Environment.get_variable ("AGENDA_PREVIEW_DIR");
        if (preview_dir != null) {
            var paintable = new Gtk.WidgetPaintable (menu.popover);
            var snapshot = new Gtk.Snapshot ();
            paintable.snapshot (snapshot, menu.popover.get_width (), menu.popover.get_height ());
            var node = snapshot.to_node ();
            if (node != null) menu.popover.get_native ().get_renderer ().render_texture (node, null).save_to_png (
                Path.build_filename (preview_dir, "time-grid-popup.png"));
        }
        label_button (menu.popover, "Open in Calendar").clicked ();
        var log = Environment.get_variable ("AGENDA_OPEN_LOG");
        for (int n = 0; n < 100 && !FileUtils.test (log, FileTest.EXISTS); n++) yield pause ();
        string command;
        FileUtils.get_contents (log, out command);
        assert (command == "--show-day\n" + today.format ("%F") + "\n");
        // A desktop without the native Calendar client still has full block
        // details; it must not offer an action that cannot launch.
        var old_path = Environment.get_variable ("PATH");
        Environment.set_variable ("PATH", Path.get_dirname (log), true);
        var without_client = menu_in (time_event (active_events (), "Overlap A"));
        try {
            without_client.popup ();
            for (int n = 0; n < 5; n++) yield pause ();
            assert (without_client.popover.get_mapped ());
            assert (label_button (without_client.popover, "Open in Calendar") == null);
            without_client.popdown ();
        } finally {
            Environment.set_variable ("PATH", old_path, true);
        }
        stdout.printf ("PASS literal block details, isolated Calendar action and missing-client fallback\n");
    }

    async void pause () {
        Timeout.add (50, () => { pause.callback (); return Source.REMOVE; });
        yield;
    }

    void dump_labels (Gtk.Widget node) {
        if (node is Gtk.Label) stderr.printf ("LABEL %s\n", ((Gtk.Label) node).label);
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) dump_labels (child);
    }

    string verse_date () {
        string text;
        named (widget, "verse-day").get ("secondary-text", out text);
        return text;
    }

    async void verse_checks (Gtk.Window window) throws Error {
        var stack = find_stack (widget);
        var page = stack.get_page (stack.get_child_by_name ("verse"));
        assert (page.icon_name == "list-add-symbolic");
        assert (page.title == "Verse of the Day");
        stack.visible_child_name = "verse";
        var data = GLib.resources_lookup_data ("/io/elementary/desktop/wingpanel/datetime/daily-verses.tsv",
            GLib.ResourceLookupFlags.NONE);
        string[] references = {};
        string[] texts = {};
        string[] headings = {};
        foreach (var line in ((string) data.get_data ()).split ("\n")) {
            var fields = line.split ("\t", 3);
            if (line.has_prefix ("#") || fields.length < 2) continue;
            references += fields[0];
            texts += fields[1];
            headings += fields.length == 3 ? fields[2] : "";
        }
        assert (references.length >= 366);
        var today = verse_index (new GLib.DateTime.now_local (), references.length);
        yield expect ("— " + references[today]);
        yield expect (texts[today]);
        foreach (var id in new string[] { "verse-sermons", "verse-videos", "verse-context", "verse-copy" }) {
            assert (named (widget, id) is Gtk.Button && ((Gtk.Button) named (widget, id)).sensitive);
        }
        var now = new GLib.DateTime.now_local ();
        var today_button = (Gtk.Button) named (widget, "verse-today");
        assert (!today_button.sensitive);
        assert (verse_date ().has_prefix ("Today · "));
        ((Gtk.Button) named (widget, "verse-next")).clicked ();
        yield expect ("— " + references[verse_index (now.add_days (1), references.length)]);
        assert (today_button.sensitive);
        assert (verse_date ().has_prefix ("Tomorrow · "));
        ((Gtk.Button) named (widget, "verse-previous")).clicked ();
        ((Gtk.Button) named (widget, "verse-previous")).clicked ();
        yield expect ("— " + references[verse_index (now.add_days (-1), references.length)]);
        assert (verse_date ().has_prefix ("Yesterday · "));
        today_button.clicked ();
        yield expect ("— " + references[today]);
        assert (!today_button.sensitive);

        // A Psalm heading is a caption, not part of the verse text.
        int ahead = 1;
        while (headings[verse_index (now.add_days (ahead), references.length)] == "") ahead++;
        for (int i = 0; i < ahead; i++) ((Gtk.Button) named (widget, "verse-next")).clicked ();
        var psalm = verse_index (now.add_days (ahead), references.length);
        yield expect (headings[psalm]);
        yield expect (texts[psalm]);
        assert (named (widget, "verse-heading").visible);
        assert (!texts[psalm].has_prefix (headings[psalm]));
        for (int i = 0; i < 5; i++) yield pause ();
        preview (window, "calendar-verse-psalm");

        // Copy puts the verse and reference on the clipboard and confirms in place.
        ((Gtk.Button) named (widget, "verse-copy")).clicked ();
        yield expect ("Copied");
        var copied = yield widget.get_clipboard ().read_text_async (null);
        assert (copied == "“%s” — %s (WEB)".printf (texts[psalm], references[psalm]));
        yield expect ("Copy Verse");

        // Reopening the panel returns to today's verse.
        indicator.closed ();
        indicator.opened ();
        yield expect ("— " + references[today]);
        assert (verse_date ().has_prefix ("Today · "));
        // No repeats inside a year (leap or not); stable within a day; reshuffled each year.
        foreach (var year in new int[] { 2026, 2027, 2028 }) {
            var used = new GenericSet<int> (direct_hash, direct_equal);
            var day = new GLib.DateTime.local (year, 1, 1, 0, 0, 0);
            for (; day.get_year () == year; day = day.add_days (1)) {
                var index = verse_index (day, references.length);
                assert (index >= 0 && index < references.length);
                assert (!used.contains (index));
                used.add (index);
                var late = new GLib.DateTime.local (year, day.get_month (), day.get_day_of_month (), 23, 59, 0);
                assert (verse_index (late, references.length) == index);
            }
        }
        var day_2026 = new GLib.DateTime.local (2026, 3, 1, 9, 0, 0);
        var same = 0;
        for (int i = 0; i < 30; i++) {
            if (verse_index (day_2026.add_days (i), references.length) ==
                verse_index (day_2026.add_years (1).add_days (i), references.length)) same++;
        }
        assert (same < 5);
        assert (verse_index (day_2026, 0) == -1);
        for (int i = 0; i < 5; i++) yield pause ();
        preview (window, "calendar-verse");
        stdout.printf ("PASS verse tab: today's verse, sermon links, no repeats within a year\n");
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
        var paintable = new Gtk.WidgetPaintable (window);
        var snapshot = new Gtk.Snapshot ();
        paintable.snapshot (snapshot, window.get_width (), window.get_height ());
        var node = snapshot.to_node ();
        if (node != null) {
            var texture = window.get_renderer ().render_texture (node, null);
            texture.save_to_png (Path.build_filename (directory, name + ".png"));
        }
    }

    Gtk.Widget? task_row (Gtk.Widget node, string title) {
        if (node.get_type ().name () == "DateTimeTaskRow" && contains (node, title)) return node;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            var row = task_row (child, title);
            if (row != null) return row;
        }
        return null;
    }

    Gtk.CheckButton? task_check (Gtk.Widget node) {
        if (node is Gtk.CheckButton) return (Gtk.CheckButton) node;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            var check = task_check (child);
            if (check != null) return check;
        }
        return null;
    }

    bool visible_label (Gtk.Widget node, string text) {
        if (node is Gtk.Label && ((Gtk.Label) node).label == text) return node.visible;
        for (var child = node.get_first_child (); child != null; child = child.get_next_sibling ()) {
            if (visible_label (child, text)) return true;
        }
        return false;
    }

    async void checkbox_checks () throws Error {
        find_stack (widget).visible_child_name = "tasks";
        var other = yield create_source ("agenda-other-tasks", ECal.ClientSourceType.TASKS);
        var original = todo ("Checkbox task").replace ("UID:test-task", "UID:panel-check");
        add (tasks, original);
        add (other, original.replace ("Checkbox task", "Other list same UID"));
        yield expect ("Checkbox task");
        yield expect ("Other list same UID");
        var completion_row = task_row (widget, "Checkbox task");
        var completion_list = completion_row.get_parent ();
        var check = task_check (completion_row);
        assert (check != null && check.sensitive);
        // Complete a row after another client has edited its record.
        var edited = original.replace ("Checkbox task", "Latest task edit").replace ("END:VTODO", "DESCRIPTION:Keep this edit\r\nEND:VTODO");
        tasks.modify_object_sync (new ICal.Component.from_string (edited), ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
        bool close_requested = false;
        ulong close_handler = indicator.close.connect (() => { close_requested = true; });
        check.active = true;
        assert (!check.sensitive);
        Signal.emit_by_name (completion_list, "row-activated", (Gtk.ListBoxRow) completion_row);
        assert (!close_requested);
        SignalHandler.disconnect (indicator, close_handler);
        yield expect ("Latest task edit", false);
        yield expect ("Checkbox task", false);
        ICal.Component saved;
        tasks.get_object_sync ("panel-check", null, out saved, null);
        // View removal and the save acknowledgement can arrive in either order.
        for (int n = 0; n < 100 && saved.get_status () != ICal.PropertyStatus.COMPLETED; n++) {
            yield pause (); tasks.get_object_sync ("panel-check", null, out saved, null);
        }
        var record = new ECal.Component.from_icalcomponent (saved.clone ());
        assert (saved.get_status () == ICal.PropertyStatus.COMPLETED);
        assert (saved.get_summary () == "Latest task edit" && saved.get_description () == "Keep this edit");
        assert (record.get_percent_complete () == 100 && record.get_completed () != null);
        ICal.Component untouched;
        other.get_object_sync ("panel-check", null, out untouched, null);
        assert (untouched.get_status () != ICal.PropertyStatus.COMPLETED);
        yield expect ("Other list same UID");
        stdout.printf ("PASS checkbox persists completion metadata, preserves newer edits and isolates source UID\n");
        registry.ref_source ("agenda-other-tasks").remove_sync (null);
        yield expect ("Other list same UID", false);

        var now = new GLib.DateTime.now_local ();
        var day = now.format ("%Y%m%d");
        add (tasks, todo ("Repeating checkbox task", false,
            "DTSTART;VALUE=DATE:" + day + "\r\nDUE;VALUE=DATE:" + day + "\r\nRRULE:FREQ=DAILY;COUNT=3\r\n").replace ("UID:test-task", "UID:repeat-check"));
        yield expect ("Repeating checkbox task");
        task_check (task_row (widget, "Repeating checkbox task")).active = true;
        ICal.Component? repeated = null;
        bool advanced = false;
        for (int n = 0; n < 150; n++) {
            yield pause ();
            tasks.get_object_sync ("repeat-check", null, out repeated, null);
            if (repeated.get_due ().as_ical_string () != day) { advanced = true; break; }
        }
        assert (advanced && repeated != null && repeated.get_status () != ICal.PropertyStatus.COMPLETED);
        yield expect ("Repeating checkbox task");
        stdout.printf ("PASS recurring checkbox advances the next occurrence without completing the series\n");
        tasks.remove_object_sync ("repeat-check", null, ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
        yield expect ("Repeating checkbox task", false);

        add (tasks, todo ("Stale checkbox task").replace ("UID:test-task", "UID:stale-check"));
        yield expect ("Stale checkbox task");
        var stale_row = task_row (widget, "Stale checkbox task");
        var stale_check = task_check (stale_row);
        tasks.remove_object_sync ("stale-check", null, ECal.ObjModType.ALL, ECal.OperationFlags.NONE, null);
        stale_check.active = true;
        bool failed_safely = false;
        for (int n = 0; n < 150; n++) {
            yield pause ();
            if (!stale_check.active && visible_label (stale_row, "Couldn’t complete task. Try again.")) {
                failed_safely = true; break;
            }
        }
        assert (failed_safely);
        stdout.printf ("PASS missing-record failure restores checkbox and exposes a retry error\n");
    }

    string? selected_list (Gtk.DropDown lists) {
        var item = lists.selected_item as Gtk.StringObject;
        return item != null ? item.string : null;
    }

    async void choose_list (Gtk.DropDown lists, string name) throws Error {
        for (int n = 0; n < 150; n++) {
            for (uint i = 0; lists.model != null && i < lists.model.get_n_items (); i++) {
                if (((Gtk.StringObject) lists.model.get_item (i)).string == name) { lists.selected = i; return; }
            }
            yield pause ();
        }
        throw new IOError.FAILED ("Expected writable task list missing");
    }

    int matching_tasks (ECal.Client client, string title) throws Error {
        SList<ECal.Component> tasks;
        client.get_object_list_as_comps_sync ("#t", out tasks, null);
        int matches = 0;
        foreach (var task in tasks) if (task.get_icalcomponent ().get_summary () == title) matches++;
        return matches;
    }

    async void quick_add_checks () throws Error {
        find_stack (widget).visible_child_name = "tasks";
        var entry = (Gtk.Entry) named (widget, "task-title");
        var button = (Gtk.Button) named (widget, "task-add");
        var lists = (Gtk.DropDown) named (widget, "task-list");
        for (int n = 0; n < 150 && selected_list (lists) != "agenda-test-tasks"; n++) yield pause ();
        assert (selected_list (lists) == "agenda-test-tasks");
        entry.text = "   ";
        assert (!button.sensitive);
        Signal.emit_by_name (entry, "activate");
        yield pause ();
        assert (!named (widget, "task-add-error").visible);
        assert (entry.text == "   ");
        stdout.printf ("PASS quick-add default task list and whitespace guard\n");

        var target = yield create_source ("agenda-quick-target", ECal.ClientSourceType.TASKS);
        yield choose_list (lists, "agenda-quick-target");
        entry.text = "  Quick café <A> & B  ";
        bool close_requested = false;
        ulong close_handler = indicator.close.connect (() => { close_requested = true; });
        Signal.emit_by_name (entry, "activate");
        assert (!entry.sensitive && !button.sensitive && !lists.sensitive);
        button.clicked (); // A second submission while pending must not duplicate the task.
        assert (!close_requested);
        SignalHandler.disconnect (indicator, close_handler);
        yield expect ("Quick café <A> & B");
        for (int n = 0; n < 150 && !entry.sensitive; n++) yield pause ();
        assert (entry.sensitive && entry.text == "");
        assert (matching_tasks (target, "Quick café <A> & B") == 1);
        assert (matching_tasks (tasks, "Quick café <A> & B") == 0);
        SList<ECal.Component> saved;
        target.get_object_list_as_comps_sync ("#t", out saved, null);
        foreach (var task in saved) {
            if (task.get_icalcomponent ().get_summary () != "Quick café <A> & B") continue;
            assert (task.get_icalcomponent ().get_uid () != "");
            assert (task.get_status () != ICal.PropertyStatus.COMPLETED);
            assert (task.get_percent_complete () == 0 && task.get_created () != null);
            var due = task.get_icalcomponent ().get_due ();
            assert (due == null || due.is_null_time ());
        }
        entry.text = "Button-created task";
        button.clicked ();
        yield expect ("Button-created task");
        for (int n = 0; n < 150 && !entry.sensitive; n++) yield pause ();
        assert (selected_list (lists) == "agenda-quick-target" && entry.text == "");
        assert (matching_tasks (target, "Button-created task") == 1);
        stdout.printf ("PASS Enter/Add create one real record in chosen list, preserve literal title/metadata and keep dropdown open\n");

        entry.text = "Retained draft";
        var selected = new List<E.Source> ();
        foreach (var source in registry.list_sources (E.SOURCE_EXTENSION_TASK_LIST)) {
            var settings = (E.SourceSelectable) source.get_extension (E.SOURCE_EXTENSION_TASK_LIST);
            if (!settings.selected) continue;
            selected.append (source);
            settings.selected = false;
            source.write_sync (null);
        }
        for (int n = 0; n < 150 && entry.sensitive; n++) yield pause ();
        assert (!entry.sensitive && !button.sensitive && entry.text == "Retained draft");
        button.clicked ();
        assert (matching_tasks (target, "Retained draft") == 0);
        foreach (var source in selected) {
            ((E.SourceSelectable) source.get_extension (E.SOURCE_EXTENSION_TASK_LIST)).selected = true;
            source.write_sync (null);
        }
        for (int n = 0; n < 150 && (!entry.sensitive || selected_list (lists) != "agenda-quick-target"); n++) yield pause ();
        assert (entry.sensitive && selected_list (lists) == "agenda-quick-target" && entry.text == "Retained draft");
        button.clicked ();
        yield expect ("Retained draft");
        for (int n = 0; n < 150 && !entry.sensitive; n++) yield pause ();
        assert (entry.text == "" && matching_tasks (target, "Retained draft") == 1);
        stdout.printf ("PASS unavailable-list guard retains draft/list selection and recovers when lists return\n");
        registry.ref_source ("agenda-quick-target").remove_sync (null);
        yield expect ("Retained draft", false);
    }

    async void run () {
        try {
            registry = new E.SourceRegistry.sync (null);
            events = yield create_source ("agenda-test-events", ECal.ClientSourceType.EVENTS);
            events2 = yield create_source ("agenda-test-events-two", ECal.ClientSourceType.EVENTS);
            tasks = yield create_source ("agenda-test-tasks", ECal.ClientSourceType.TASKS);
            registry.set_default_task_list (registry.ref_source ("agenda-test-tasks"));
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
            yield upcoming_checks ();
            choose_view ("day");
            yield navigation_checks ();
            yield view_checks (window);
            yield time_grid_checks (window);
            choose_view ("upcoming");
            yield expect ("Upcoming · next 30 days");
            preview (window, "calendar-events");
            find_stack (widget).visible_child_name = "tasks";
            yield expect ("Undated task");
            yield expect ("Due-only task");
            for (int i = 0; i < 5; i++) yield pause ();
            preview (window, "calendar-tasks");
            stdout.printf ("PASS tabs, separate calendars with shared UID, undated task\n");
            yield verse_checks (window);
            find_stack (widget).visible_child_name = "tasks";

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
            yield checkbox_checks ();
            yield quick_add_checks ();
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
        assert (module.symbol ("date_time_daily_verse_index_for", out symbol));
        verse_index = (VerseIndex) symbol;
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
    Adw.StyleManager.get_default ().color_scheme = Environment.get_variable ("AGENDA_TEST_DARK") == "1" ? Adw.ColorScheme.FORCE_DARK : Adw.ColorScheme.FORCE_LIGHT;
    return new AgendaTest ().execute (args[1]);
}
