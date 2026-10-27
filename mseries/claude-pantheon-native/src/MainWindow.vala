public class MainWindow : Gtk.ApplicationWindow {
    private Gtk.ListBox session_list;
    private Gtk.SearchEntry search;
    private ChatView chat;
    private Gtk.Label chat_title;
    private Gtk.Label chat_subtitle;
    private Gtk.Entry composer;
    private Gtk.Button send_button;
    private Gtk.Button stop_button;
    private Gtk.Label status_label;
    private Granite.Toast toast;
    private List<Session> sessions = new List<Session> ();
    private Session? current = null;
    private Transcript? current_transcript = null;
    private ClaudeRunner? runner = null;
    private uint load_generation = 0;
    private string permission_mode = "default";
    private bool draft = false;            // a new chat that has no session id yet
    private string? select_after_scan = null;

    public MainWindow (Gtk.Application app) {
        Object (application: app, default_width: 1120, default_height: 700, title: "Claude");
        add_css_class ("claude-window");
        var style = new Gtk.CssProvider ();
        style.load_from_string ("""
            .claude-window .sidebar-pane { border-right: 1px solid alpha(currentColor, 0.1); }
            .claude-window .session-row { padding: 6px 10px; border-radius: 6px; }
            .claude-window .session-time { font-size: 0.85em; }
            .claude-window .project-header { padding: 14px 12px 4px 12px; font-size: 0.8em; font-weight: 700; letter-spacing: 0.06em; opacity: 0.55; }
            .claude-window .user-bubble { background: alpha(@accent_color, 0.16); border-radius: 18px; padding: 10px 14px; }
            .claude-window .assistant-text { padding-right: 24px; }
            .claude-window .code-block { background: alpha(currentColor, 0.06); border-radius: 8px; padding: 0; box-shadow: inset 0 0 0 1px alpha(currentColor, 0.06); }
            .claude-window .code-block .code-caption { font-size: 0.75em; font-weight: 700; opacity: 0.55; padding: 6px 12px 0 12px; letter-spacing: 0.04em; text-transform: uppercase; }
            .claude-window .code-block .code-text { padding: 8px 12px 10px 12px; font-size: 0.92em; }
            .claude-window .tool-row { border-radius: 8px; }
            .claude-window .tool-row-button { padding: 4px 8px; border-radius: 8px; opacity: 0.8; }
            .claude-window .tool-row-button:hover { background: alpha(currentColor, 0.06); opacity: 1; }
            .claude-window .tool-error .code-caption { color: @error_color; opacity: 1; }
            .claude-window .error-note { color: @error_color; }
            .claude-window .composer { padding: 10px 14px 12px 14px; border-top: 1px solid alpha(currentColor, 0.1); }
            .claude-window .composer entry { border-radius: 20px; padding-left: 14px; padding-right: 14px; min-height: 36px; }
            .claude-window .chat-header-title { font-weight: 700; }
            .claude-window .chat-header-subtitle { font-size: 0.85em; opacity: 0.6; }
            /* GTK's default client-side window shadow is a blurred box-shadow that the
               cairo renderer re-blurs over the whole window on every frame (~40 ms at
               2x). A 1px outline keeps the window edge visible without the blur. */
            window.claude-window, window.claude-window.csd, window.claude-window.csd:backdrop,
            window.claude-window decoration, window.claude-window.csd decoration,
            window.claude-window.csd:backdrop decoration { box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35); transition: none; }
        """);
        Gtk.StyleContext.add_provider_for_display (get_display (), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);

        titlebar = new Gtk.Grid () { visible = false };

        // ---- sidebar ----
        var sidebar_header = new Gtk.HeaderBar () { show_title_buttons = false, title_widget = new Gtk.Label ("") };
        sidebar_header.add_css_class (Granite.STYLE_CLASS_FLAT);
        sidebar_header.pack_start (new Gtk.WindowControls (Gtk.PackType.START));
        var new_chat = new Gtk.Button.from_icon_name ("list-add-symbolic") { tooltip_text = "New chat (Ctrl+N)" };
        new_chat.update_property (Gtk.AccessibleProperty.LABEL, "New chat", -1);
        new_chat.clicked.connect (start_new_chat);
        sidebar_header.pack_end (new_chat);
        var refresh = new Gtk.Button.from_icon_name ("view-refresh-symbolic") { tooltip_text = "Rescan chats" };
        refresh.update_property (Gtk.AccessibleProperty.LABEL, "Rescan chats", -1);
        refresh.clicked.connect (() => { rescan.begin (); });
        sidebar_header.pack_end (refresh);

        search = new Gtk.SearchEntry () { placeholder_text = "Search chats…", margin_start = 10, margin_end = 10, margin_top = 4, margin_bottom = 6 };
        search.update_property (Gtk.AccessibleProperty.LABEL, "Search chats", -1);
        search.search_changed.connect (() => { session_list.invalidate_filter (); session_list.invalidate_headers (); });

        session_list = new Gtk.ListBox () { selection_mode = Gtk.SelectionMode.SINGLE, activate_on_single_click = true };
        session_list.add_css_class ("navigation-sidebar");
        session_list.set_header_func (project_header);
        session_list.set_filter_func (filter_row);
        session_list.row_selected.connect (on_row_selected);
        var placeholder = new Gtk.Label ("Scanning ~/.claude/projects…") { margin_top = 24 };
        placeholder.add_css_class ("dim-label");
        session_list.set_placeholder (placeholder);
        var list_scroller = new Gtk.ScrolledWindow () { child = session_list, vexpand = true, hscrollbar_policy = Gtk.PolicyType.NEVER };

        var sidebar = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { width_request = 260 };
        sidebar.add_css_class ("sidebar-pane");
        sidebar.append (sidebar_header);
        sidebar.append (search);
        sidebar.append (list_scroller);

        // ---- content ----
        var header = new Gtk.HeaderBar () { show_title_buttons = false };
        header.add_css_class (Granite.STYLE_CLASS_FLAT);
        var titles = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { valign = Gtk.Align.CENTER };
        chat_title = new Gtk.Label ("Claude") { ellipsize = Pango.EllipsizeMode.END, xalign = 0.5f };
        chat_title.add_css_class ("chat-header-title");
        chat_subtitle = new Gtk.Label ("") { ellipsize = Pango.EllipsizeMode.MIDDLE, xalign = 0.5f };
        chat_subtitle.add_css_class ("chat-header-subtitle");
        titles.append (chat_title); titles.append (chat_subtitle);
        header.title_widget = titles;
        header.pack_end (new Gtk.WindowControls (Gtk.PackType.END));

        var menu = new Menu ();
        var modes = new Menu ();
        modes.append ("Ask before tools (default)", "win.permission-mode::default");
        modes.append ("Accept file edits", "win.permission-mode::acceptEdits");
        modes.append ("Plan only", "win.permission-mode::plan");
        modes.append ("Bypass permissions (dangerous)", "win.permission-mode::bypassPermissions");
        menu.append_section ("Tool permissions", modes);
        var misc = new Menu ();
        misc.append ("Rescan Chats", "win.rescan");
        misc.append ("Quit", "app.quit");
        menu.append_section (null, misc);
        var more = new Gtk.MenuButton () { icon_name = "open-menu-symbolic", menu_model = menu, tooltip_text = "Menu", primary = true };
        more.update_property (Gtk.AccessibleProperty.LABEL, "Menu", -1);
        header.pack_end (more);

        var mode_action = new SimpleAction.stateful ("permission-mode", VariantType.STRING, new Variant.string ("default"));
        mode_action.activate.connect ((parameter) => { permission_mode = parameter.get_string (); mode_action.set_state (parameter); });
        add_action (mode_action);
        var rescan_action = new SimpleAction ("rescan", null);
        rescan_action.activate.connect (() => { rescan.begin (); });
        add_action (rescan_action);
        var new_action = new SimpleAction ("new-chat", null);
        new_action.activate.connect (start_new_chat);
        add_action (new_action);
        var find_action = new SimpleAction ("find", null);
        find_action.activate.connect (() => { search.grab_focus (); });
        add_action (find_action);
        var stop_action = new SimpleAction ("stop", null);
        stop_action.activate.connect (() => { if (runner != null) runner.stop (); });
        add_action (stop_action);

        chat = new ChatView ();

        var composer_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        composer_box.add_css_class ("composer");
        var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        composer = new Gtk.Entry () { placeholder_text = "Message Claude…", hexpand = true };
        composer.update_property (Gtk.AccessibleProperty.LABEL, "Message", -1);
        composer.activate.connect (send_message);
        send_button = new Gtk.Button.from_icon_name ("mail-send-symbolic") { tooltip_text = "Send (Enter)" };
        send_button.add_css_class (Granite.STYLE_CLASS_SUGGESTED_ACTION);
        send_button.add_css_class ("circular");
        send_button.update_property (Gtk.AccessibleProperty.LABEL, "Send", -1);
        send_button.clicked.connect (send_message);
        stop_button = new Gtk.Button.from_icon_name ("media-playback-stop-symbolic") { tooltip_text = "Stop (Esc)", visible = false };
        stop_button.add_css_class (Granite.STYLE_CLASS_DESTRUCTIVE_ACTION);
        stop_button.add_css_class ("circular");
        stop_button.update_property (Gtk.AccessibleProperty.LABEL, "Stop", -1);
        stop_button.clicked.connect (() => { if (runner != null) runner.stop (); });
        row.append (composer); row.append (send_button); row.append (stop_button);
        status_label = new Gtk.Label ("") { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
        status_label.add_css_class ("dim-label");
        status_label.add_css_class ("session-time");
        composer_box.append (row); composer_box.append (status_label);

        var content = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        content.append (header);
        var overlay = new Gtk.Overlay () { child = chat, vexpand = true };
        toast = new Granite.Toast ("");
        overlay.add_overlay (toast);
        content.append (overlay);
        content.append (composer_box);

        var paned = new Gtk.Paned (Gtk.Orientation.HORIZONTAL) { start_child = sidebar, end_child = content, resize_start_child = false, shrink_start_child = false, shrink_end_child = false, position = 300 };
        child = paned;

        update_status ();
        rescan.begin ();
        arm_screenshot ();
        if (Environment.get_variable ("CLAUDE_PANTHEON_DEBUG") != null) {
            map.connect (() => { stderr.printf ("startup: window mapped after %.0f ms, scale %d\n", (get_monotonic_time () - Application.launched) / 1000.0, get_scale_factor ()); });
        }
    }

    /* CLAUDE_PANTHEON_SCREENSHOT=<png path> renders the window to a file a few
     * seconds after start; CLAUDE_PANTHEON_OPEN=<session id prefix> picks the
     * chat to show first. Used for the docs screenshots since this desktop has
     * no screenshot D-Bus interface. */
    private void arm_screenshot () {
        var send = Environment.get_variable ("CLAUDE_PANTHEON_SEND");
        if (send != null) Timeout.add (1500, () => { composer.text = send; send_message (); return Source.REMOVE; });
        var target = Environment.get_variable ("CLAUDE_PANTHEON_SCREENSHOT");
        if (target == null) return;
        int delay = 4000;
        var delay_text = Environment.get_variable ("CLAUDE_PANTHEON_SCREENSHOT_DELAY");
        if (delay_text != null) int.try_parse (delay_text, out delay);
        Timeout.add (delay, () => {
            try {
                var paintable = new Gtk.WidgetPaintable (this);
                var snapshot = new Gtk.Snapshot ();
                paintable.snapshot (snapshot, get_width (), get_height ());
                var node = snapshot.free_to_node ();
                if (node != null) {
                    var texture = get_renderer ().render_texture (node, null);
                    texture.save_to_png (target);
                    message ("Saved screenshot to %s", target);
                }
            } catch (Error e) { warning ("Screenshot failed: %s", e.message); }
            return Source.REMOVE;
        });
    }

    /* ---- sidebar ---- */

    private async void rescan () {
        List<Session> found = null;
        SourceFunc resume = rescan.callback;
        new Thread<void*> ("scan", () => { found = SessionIndex.scan (); Idle.add ((owned) resume); return null; });
        yield;
        sessions = (owned) found;
        rebuild_list ();
    }

    private void rebuild_list () {
        string? keep = select_after_scan ?? (current != null && !draft ? current.id : null);
        select_after_scan = null;
        // Order projects by their newest session, then sessions newest first.
        var project_rank = new HashTable<string, int64?> (str_hash, str_equal);
        foreach (var session in sessions) {
            var best = project_rank.lookup (session.project);
            if (best == null || session.modified > best) project_rank.insert (session.project, session.modified);
        }
        var ordered = sessions.copy ();
        ordered.sort_with_data ((a, b) => {
            if (a.project != b.project) {
                int64 ra = project_rank.lookup (a.project), rb = project_rank.lookup (b.project);
                if (ra != rb) return ra > rb ? -1 : 1;
                return a.project.collate (b.project);
            }
            return a.modified > b.modified ? -1 : a.modified < b.modified ? 1 : 0;
        });
        Gtk.ListBoxRow? to_select = null;
        session_list.remove_all ();
        foreach (var session in ordered) {
            var row = make_row (session);
            session_list.append (row);
            if (keep != null && session.id == keep) to_select = row;
        }
        var wanted = Environment.get_variable ("CLAUDE_PANTHEON_OPEN");
        if (to_select == null && wanted != null && current == null) {
            for (var child = session_list.get_first_child (); child != null; child = child.get_next_sibling ()) {
                var row = child as Gtk.ListBoxRow;
                if (row != null && row.get_data<Session> ("session").id.has_prefix (wanted)) { to_select = row; break; }
            }
        }
        if (to_select != null) session_list.select_row (to_select);
        update_status ();
    }

    private Gtk.ListBoxRow make_row (Session session) {
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        box.add_css_class ("session-row");
        var title = new Gtk.Label (session.title) { xalign = 0, ellipsize = Pango.EllipsizeMode.END, single_line_mode = true };
        var time = new Gtk.Label (Granite.DateTime.get_relative_datetime (new DateTime.from_unix_local (session.modified))) { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
        time.add_css_class ("dim-label");
        time.add_css_class ("session-time");
        box.append (title); box.append (time);
        var row = new Gtk.ListBoxRow () { child = box, tooltip_text = session.title };
        row.set_data<Session> ("session", session);
        return row;
    }

    private void project_header (Gtk.ListBoxRow row, Gtk.ListBoxRow? before) {
        var session = row.get_data<Session> ("session");
        Session? previous = null;
        // Find the previous *visible* row so headers survive filtering.
        var cursor = before;
        while (cursor != null) {
            var candidate = cursor.get_data<Session> ("session");
            if (filter_row (cursor)) { previous = candidate; break; }
            cursor = (Gtk.ListBoxRow?) cursor.get_prev_sibling ();
        }
        if (previous != null && previous.project == session.project) { row.set_header (null); return; }
        var label = new Gtk.Label (session.project_name.up ()) { xalign = 0, ellipsize = Pango.EllipsizeMode.MIDDLE, tooltip_text = session.project };
        label.add_css_class ("project-header");
        row.set_header (label);
    }

    private bool filter_row (Gtk.ListBoxRow row) {
        var needle = search.text.strip ().casefold ();
        if (needle == "") return true;
        var session = row.get_data<Session> ("session");
        return session.title.casefold ().contains (needle) || session.project_name.casefold ().contains (needle);
    }

    private void on_row_selected (Gtk.ListBoxRow? row) {
        if (row == null) return;
        var session = row.get_data<Session> ("session");
        if (current != null && current.id == session.id && !draft) return;
        if (runner != null) { toast.title = "Wait for the running reply to finish first."; toast.send_notification (); return; }
        open_session (session);
    }

    private void open_session (Session session) {
        current = session;
        draft = false;
        current_transcript = null;
        chat_title.label = session.title;
        chat_subtitle.label = session.project;
        chat.show_empty ("Loading…");
        load_generation++;
        uint generation = load_generation;
        var path = session.path;
        Transcript? result = null;
        new Thread<void*> ("parse", () => {
            result = Transcript.load (path);
            Idle.add (() => {
                if (generation != load_generation) return Source.REMOVE;
                current_transcript = result;
                if (result.cwd != "") { session.project = result.cwd; chat_subtitle.label = result.cwd; }
                chat.follow_tail = true;
                chat.show_transcript (result);
                update_status ();
                composer.grab_focus ();
                return Source.REMOVE;
            });
            return null;
        });
    }

    private void start_new_chat () {
        if (runner != null) { toast.title = "Wait for the running reply to finish first."; toast.send_notification (); return; }
        var session = new Session ();
        session.id = "";
        session.project = current != null ? current.project : Environment.get_home_dir ();
        session.title = "New chat";
        session.modified = new DateTime.now_local ().to_unix ();
        current = session;
        draft = true;
        current_transcript = null;
        session_list.unselect_all ();
        chat_title.label = "New chat";
        chat_subtitle.label = session.project;
        chat.show_empty ("Say something to start a new chat in\n" + session.project);
        composer.grab_focus ();
        update_status ();
    }

    /* ---- talking to claude ---- */

    private void send_message () {
        var prompt = composer.text.strip ();
        if (prompt == "" || runner != null) return;
        if (current == null) start_new_chat ();
        if (draft) chat.clear ();
        composer.text = "";
        chat.append_user (prompt);
        chat.begin_live_turn ();
        var session = current;
        runner = new ClaudeRunner ();
        runner.session_started.connect ((id) => {
            if (session.id == "") { session.id = id; chat_title.label = Transcript.first_line (prompt); session.title = chat_title.label; }
        });
        runner.text_delta.connect (chat.live_text_delta);
        runner.text_done.connect (chat.live_text_done);
        runner.tool_use.connect (chat.live_tool_use);
        runner.tool_result.connect (chat.live_tool_result);
        runner.finished.connect ((ok, note) => {
            if (note != "") chat.live_status (note, !ok);
            chat.end_live_turn ();
            runner = null;
            set_busy (false);
            if (session.id != "") { select_after_scan = session.id; draft = false; }
            rescan.begin ();
        });
        set_busy (true);
        runner.start (prompt, session.project, draft ? null : session.id, permission_mode);
    }

    private void set_busy (bool busy) {
        send_button.visible = !busy;
        stop_button.visible = busy;
        composer.sensitive = !busy;
        update_status ();
        if (!busy) composer.grab_focus ();
    }

    private void update_status () {
        if (runner != null) { status_label.label = "Claude is working… Esc stops it."; return; }
        var binary = ClaudeRunner.find_binary ();
        if (binary == null) { status_label.label = "claude command line tool not found; chats are read-only."; return; }
        var count = sessions.length ();
        var suffix = current != null ? (draft ? "New chat in " + current.project : "Resumes session " + current.id.substring (0, 8) + " in " + current.project) : "%u chats on disk".printf (count);
        status_label.label = suffix;
    }
}
