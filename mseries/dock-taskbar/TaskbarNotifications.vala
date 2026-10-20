/* SPDX-License-Identifier: GPL-3.0
 * Native history anchor. All actions affect local notification history only. */
public class Dock.TaskbarNotifications : Gtk.Box {
    private const string BUS = "org.freedesktop.Notifications";
    private const string PATH = "/org/techmore/MSeries/Notifications";
    private const string IFACE = "org.techmore.MSeries.Notifications1";
    private DBusProxy? proxy;
    private Cancellable cancel = new Cancellable ();
    private Gtk.Button button;
    private Gtk.Image icon;
    private Gtk.Label count;
    private Gtk.Label status;
    private Gtk.Label context_error;
    private Gtk.Box entries;
    private Gtk.Popover history;
    private Gtk.Popover context;
    private Gtk.Switch dnd;
    private Gtk.Button mark;
    private bool refreshing;
    private bool refresh_again;
    private bool writing;
    private bool syncing;
    private string? action_error;
    private bool known;
    private bool quiet;
    private int unread;

    construct {
        orientation = Gtk.Orientation.VERTICAL;
        valign = Gtk.Align.CENTER;
        icon = new Gtk.Image.from_icon_name ("notification-symbolic") { pixel_size = 30 };
        count = new Gtk.Label ("") {
            visible = false, halign = Gtk.Align.CENTER, valign = Gtk.Align.CENTER,
            margin_top = 2, can_target = false
        };
        count.add_css_class ("badge");
        var face = new Gtk.Overlay () { child = icon };
        face.add_overlay (count);
        button = new Gtk.Button () { child = face, valign = Gtk.Align.CENTER };
        button.add_css_class ("mseries-notification-bell");
        install_style ();
        append (button);
        history = make_popover ();
        context = make_popover ();
        var body = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) {
            width_request = 360, margin_top = 16, margin_bottom = 8,
            margin_start = 16, margin_end = 16
        };
        var title = new Gtk.Label (_("Notifications")) { xalign = 0 };
        title.add_css_class ("h3");
        var title_attributes = new Pango.AttrList ();
        title_attributes.insert (Pango.attr_weight_new (Pango.Weight.BOLD));
        title_attributes.insert (Pango.attr_scale_new (1.2));
        title.attributes = title_attributes;
        body.append (title);
        status = new Gtk.Label (_("Notifications unavailable")) { wrap = true, xalign = 0 };
        status.add_css_class ("dim-label");
        body.append (status);
        body.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
        entries = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        body.append (new Gtk.ScrolledWindow () {
            child = entries, hscrollbar_policy = Gtk.PolicyType.NEVER,
            max_content_height = 400, propagate_natural_height = true
        });
        history.child = body;
        var menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 4) {
            width_request = 280,
            margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12
        };
        mark = new Gtk.Button.with_label (_("Mark all as read"));
        mark.add_css_class ("flat");
        ((Gtk.Label) mark.child).xalign = 0;
        mark.tooltip_text = _("Mark local notification history as read");
        mark.clicked.connect (() => { mutate.begin ("MarkAllRead", null); });
        menu.append (mark);
        var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        row.append (new Gtk.Label (_("Do Not Disturb")) { hexpand = true, xalign = 0 });
        dnd = new Gtk.Switch () { valign = Gtk.Align.CENTER, sensitive = false };
        dnd.update_property (Gtk.AccessibleProperty.LABEL, _("Do Not Disturb"), -1);
        dnd.state_set.connect ((value) => {
            if (!writing && !syncing && known) mutate.begin ("SetDoNotDisturb", new Variant ("(b)", value));
            return true; // The service confirms both the switch position and state.
        });
        row.add_css_class ("mseries-notification-setting");
        row.append (dnd);
        menu.append (row);
        context_error = new Gtk.Label ("") {
            visible = false, wrap = true, xalign = 0, max_width_chars = 36
        };
        menu.append (context_error);
        context.child = menu;
        button.clicked.connect (() => {
            context.popdown ();
            if (history.visible) history.popdown ();
            else { history.popup (); refresh.begin (); }
        });
        var secondary = new Gtk.GestureClick () { button = Gdk.BUTTON_SECONDARY };
        secondary.pressed.connect (() => {
            history.popdown ();
            context.popup ();
            refresh.begin ();
        });
        button.add_controller (secondary);
        unmap.connect (() => { history.popdown (); context.popdown (); });
        render_status ();
        connect_service.begin ();
    }

    private Gtk.Popover make_popover () {
        var popup = new Gtk.Popover () { position = Gtk.PositionType.TOP, has_arrow = false };
        popup.add_css_class (Granite.STYLE_CLASS_MENU);
        popup.add_css_class ("mseries-notification-popup");
        popup.set_parent (button);
        return popup;
    }

    private static bool style_installed;

    private void install_style () {
        if (style_installed) return;
        var provider = new Gtk.CssProvider ();
        provider.load_from_string ("""
            button.mseries-notification-bell {
                border: none;
                box-shadow: none;
                border-radius: 8px;
                padding: 4px 8px;
            }
            button.mseries-notification-bell label.badge {
                background-color: transparent;
                background-image: none;
                color: inherit;
                border: none;
                border-radius: 999px;
                box-shadow: none;
                text-shadow: none;
                padding: 0 1px;
                min-width: 0;
                min-height: 0;
                font-size: 9px;
                font-weight: 600;
            }
            popover.mseries-notification-popup > contents { padding: 4px; }
            .mseries-notification-popup button.flat {
                padding: 6px 10px;
                border-radius: 6px;
            }
            .mseries-notification-popup .mseries-notification-setting {
                padding: 10px;
                border-top: 1px solid alpha(currentColor, 0.12);
            }
        """);
        Gtk.StyleContext.add_provider_for_display (get_display (), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        style_installed = true;
    }

    private async void connect_service () {
        try {
            proxy = yield new DBusProxy.for_bus (BusType.SESSION,
                DBusProxyFlags.DO_NOT_AUTO_START | DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                null, BUS, PATH, IFACE, cancel);
            proxy.g_signal.connect ((sender, name, parameters) => {
                if (name == "Changed") refresh.begin ();
            });
            proxy.notify["g-name-owner"].connect (() => { refresh.begin (); });
            yield refresh ();
        } catch (Error e) { unavailable (); }
    }

    private async Variant call (string method, Variant? args = null) throws Error {
        if (proxy == null || proxy.g_name_owner == null) throw new IOError.NOT_CONNECTED ("Unavailable");
        return yield proxy.call (method, args, DBusCallFlags.NO_AUTO_START, 4000, cancel);
    }

    private Json.Node parse (Variant result) throws Error {
        string json;
        result.get ("(s)", out json);
        var parser = new Json.Parser ();
        parser.load_from_data (json);
        return parser.get_root ().copy ();
    }

    private void clear_entries () {
        while (entries.get_first_child () != null) entries.remove (entries.get_first_child ());
    }

    private void unavailable () {
        known = false;
        clear_entries ();
        status.label = _("Notifications unavailable");
        render_status ();
    }

    private void render_status () {
        icon.icon_name = known && quiet ? "notifications-disabled-symbolic" : "notification-symbolic";
        count.visible = known && unread > 0;
        count.label = unread > 99 ? "99+" : unread.to_string ();
        var description = !known ? _("Notifications unavailable") :
            _("Notifications: %d unread").printf (unread);
        if (known && quiet) description += " · " + _("Do Not Disturb");
        button.tooltip_text = description;
        button.update_property (Gtk.AccessibleProperty.LABEL, description, -1);
        syncing = true;
        if (known) { dnd.active = quiet; dnd.state = quiet; }
        syncing = false;
        dnd.sensitive = known && !writing;
        mark.sensitive = known && unread > 0 && !writing;
    }

    private async void refresh () {
        if (refreshing) { refresh_again = true; return; }
        refreshing = true;
        do {
            refresh_again = false;
            try {
                var owner = proxy != null ? proxy.g_name_owner : null;
                var node = parse (yield call ("GetStatus"));
                if (node.get_node_type () != Json.NodeType.OBJECT) throw new IOError.INVALID_DATA ("Status");
                var obj = node.get_object ();
                if (!obj.has_member ("unread") || !obj.has_member ("dnd")) throw new IOError.INVALID_DATA ("Status");
                unread = (int) int64.max (0, obj.get_int_member ("unread"));
                quiet = obj.get_boolean_member ("dnd");
                if (proxy.g_name_owner != owner) { refresh_again = true; continue; }
                known = true;
                render_status ();
                if (history.visible) {
                    var list = parse (yield call ("ListNotifications", new Variant ("(u)", 50u)));
                    if (proxy.g_name_owner != owner) { refresh_again = true; continue; }
                    if (list.get_node_type () != Json.NodeType.ARRAY) throw new IOError.INVALID_DATA ("History");
                    clear_entries ();
                    var array = list.get_array ();
                    for (uint i = 0; i < uint.min (50, array.get_length ()); i++) {
                        var entry = array.get_element (i);
                        if (entry.get_node_type () == Json.NodeType.OBJECT) add_entry (entry.get_object ());
                    }
                    status.label = array.get_length () == 0 ? _("No notifications") : _("Recent notifications");
                }
            } catch (Error e) { unavailable (); }
        } while (refresh_again && !cancel.is_cancelled ());
        refreshing = false;
    }

    private static Gtk.Label text_label (string text) {
        return new Gtk.Label (text) {
            xalign = 0, wrap = true, wrap_mode = Pango.WrapMode.WORD_CHAR,
            max_width_chars = 42, natural_wrap_mode = Gtk.NaturalWrapMode.NONE
        };
    }

    private void add_entry (Json.Object item) {
        string[] fields = { "id", "app", "summary", "body", "received_at", "read", "open_available", "can_reply" };
        foreach (var field in fields) if (!item.has_member (field)) return;
        uint id = (uint) item.get_int_member ("id");
        var row = new Gtk.Box (Gtk.Orientation.VERTICAL, 6) {
            margin_top = 12, margin_bottom = 12
        };
        var content = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        row.append (content);
        var meta = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var app = new Gtk.Label (item.get_string_member ("app")) {
            xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END,
            max_width_chars = 20
        };
        app.add_css_class ("dim-label");
        meta.append (app);
        var time = new DateTime.from_unix_local (item.get_int_member ("received_at"));
        var timestamp = new Gtk.Label (time.format ("%H:%M")) {
            tooltip_text = time.format ("%x %X"), valign = Gtk.Align.START
        };
        timestamp.add_css_class ("dim-label");
        meta.append (timestamp);
        content.append (meta);
        var summary = text_label (item.get_string_member ("summary"));
        summary.lines = 2;
        summary.ellipsize = Pango.EllipsizeMode.END;
        summary.tooltip_text = item.get_string_member ("summary");
        if (!item.get_boolean_member ("read")) {
            var emphasis = new Pango.AttrList ();
            emphasis.insert (Pango.attr_weight_new (Pango.Weight.SEMIBOLD));
            summary.attributes = emphasis;
        }
        content.append (summary);
        var body = text_label (item.get_string_member ("body"));
        body.lines = 3;
        body.ellipsize = Pango.EllipsizeMode.END;
        body.tooltip_text = item.get_string_member ("body");
        content.append (body);
        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6) { halign = Gtk.Align.END };
        if (item.get_boolean_member ("open_available")) {
            var open = new Gtk.Button.with_label (_("Open"));
            open.add_css_class ("flat");
            open.update_property (Gtk.AccessibleProperty.LABEL,
                _("Open notification: %s").printf (item.get_string_member ("summary")), -1);
            open.clicked.connect (() => { mutate.begin ("OpenNotification", new Variant ("(u)", id)); });
            actions.append (open);
            // The content remains a default-click target without becoming a
            // large raised button. Keyboard users have the explicit Open action.
            var click = new Gtk.GestureClick () { button = Gdk.BUTTON_PRIMARY };
            click.released.connect (() => {
                if (!writing) mutate.begin ("OpenNotification", new Variant ("(u)", id));
            });
            content.add_controller (click);
        }
        if (item.get_boolean_member ("can_reply")) {
            var reply = new Gtk.Button.with_label (_("Reply"));
            reply.add_css_class ("flat");
            reply.tooltip_text = _("Open the conversation to reply");
            reply.clicked.connect (() => { mutate.begin ("InvokeAction", new Variant ("(us)", id, "reply")); });
            actions.append (reply);
        }
        if (actions.get_first_child () != null) row.append (actions);
        entries.append (row);
        entries.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
    }

    private async void mutate (string method, Variant? args) {
        if (writing) return;
        writing = true;
        context.sensitive = false;
        history.sensitive = false;
        action_error = null;
        context_error.label = "";
        context_error.visible = false;
        try {
            var result = yield call (method, args);
            if ((method == "OpenNotification" || method == "InvokeAction") &&
                !result.get_child_value (0).get_boolean ())
                action_error = _("Action unavailable");
        } catch (Error e) { action_error = _("Could not update notifications"); }
        writing = false;
        context.sensitive = true;
        history.sensitive = true;
        yield refresh ();
        if (action_error != null) {
            status.label = action_error;
            context_error.label = action_error;
            context_error.visible = true;
        }
    }

    public override void dispose () {
        cancel.cancel ();
        if (history != null && history.get_parent () != null) history.unparent ();
        if (context != null && context.get_parent () != null) context.unparent ();
        base.dispose ();
    }
}
