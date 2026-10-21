/* SPDX-License-Identifier: GPL-3.0-or-later
 * Remote Desktop window: turn sharing on, make a link/QR for a phone, answer
 * a request, and see or end the live session. Mirrors the Orchard/Machine Lab
 * layout (GTK 4 + Granite 7, header bar, placeholder, cards). */
namespace MSeries.Remote {
    public class MainWindow : Gtk.ApplicationWindow {
        public Service service { get; construct; }

        private Gtk.Stack stack;
        private Granite.Placeholder unavailable_page;
        private Gtk.Switch enable_switch;
        private Gtk.Label enable_subtitle;
        private bool updating = false;

        private Gtk.Box idle_box;
        private Gtk.CheckButton offer_control;
        private Gtk.Button create_button;
        private Gtk.Box invite_box;
        private QrArea qr;
        private Gtk.Box link_rows;
        private Gtk.Label invite_expiry;
        private Invite? invite = null;
        private uint expiry_tick = 0;

        private Gtk.Box pending_box;
        private Gtk.Label pending_title;
        private Gtk.Button view_only_button;
        private Gtk.Button control_button;

        private Gtk.Box session_box;
        private Gtk.Label session_title;
        private Gtk.Label session_detail;
        private Gtk.Switch control_switch;
        private Gtk.Box control_row;
        private Granite.Toast toast;

        public MainWindow (Gtk.Application app, Service service) {
            Object (application: app, service: service, default_width: 460, default_height: 600, title: _("Remote Desktop"));
        }

        construct {
            var header = new Gtk.HeaderBar ();
            set_titlebar (header);
            hide_on_close = true;

            unavailable_page = new Granite.Placeholder (_("Remote access isn't running")) {
                description = _("The background service could not be reached."),
                icon = new ThemedIcon ("preferences-system-sharing")
            };
            var start = unavailable_page.append_button (new ThemedIcon ("media-playback-start"), _("Start Service"),
                _("Start the Remote Desktop background service."));
            start.clicked.connect (() => { service.start_service.begin (); });

            var main = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
            main.append (build_enable_row ());
            idle_box = build_idle ();
            pending_box = build_pending ();
            session_box = build_session ();
            main.append (idle_box);
            main.append (pending_box);
            main.append (session_box);

            var scroll = new Gtk.ScrolledWindow () { child = main, hscrollbar_policy = Gtk.PolicyType.NEVER, vexpand = true };
            stack = new Gtk.Stack () { transition_type = Gtk.StackTransitionType.CROSSFADE };
            stack.add_named (scroll, "main");
            stack.add_named (unavailable_page, "unavailable");

            toast = new Granite.Toast ("");
            var overlay = new Gtk.Overlay () { child = stack };
            overlay.add_overlay (toast);
            child = overlay;

            service.changed.connect (update);
            service.failed.connect ((message) => {
                toast.title = message;
                toast.send_notification ();
            });
            update ();
        }

        private Gtk.Widget build_enable_row () {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 2) { hexpand = true, valign = Gtk.Align.CENTER };
            var title = new Gtk.Label (_("Allow remote access")) { halign = Gtk.Align.START, xalign = 0 };
            bold (title);
            enable_subtitle = new Gtk.Label ("") { halign = Gtk.Align.START, xalign = 0, wrap = true };
            enable_subtitle.add_css_class (Granite.CssClass.DIM);
            text.append (title);
            text.append (enable_subtitle);
            enable_switch = new Gtk.Switch () { valign = Gtk.Align.CENTER };
            enable_switch.update_property (Gtk.AccessibleProperty.LABEL, _("Allow remote access"), -1);
            enable_switch.notify["active"].connect (() => {
                if (updating) return;
                service.set_enabled.begin (enable_switch.active);
            });
            row.append (text);
            row.append (enable_switch);
            return row;
        }

        private Gtk.Box build_idle () {
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12);
            box.append (new Granite.HeaderLabel (_("Connect a phone")));
            var hint = new Gtk.Label (_("Create a link, then open it on your phone or scan the code. Each link works once and expires in five minutes.")) {
                wrap = true, xalign = 0, halign = Gtk.Align.START
            };
            hint.add_css_class (Granite.CssClass.DIM);
            box.append (hint);

            offer_control = new Gtk.CheckButton.with_label (_("Let me allow remote control"));
            offer_control.tooltip_text = _("You will still choose between View Only and Allow Control when the phone asks.");
            box.append (offer_control);

            create_button = new Gtk.Button.with_label (_("Create Link"));
            create_button.add_css_class (Granite.CssClass.SUGGESTED);
            create_button.halign = Gtk.Align.START;
            create_button.clicked.connect (() => { create_invite.begin (); });
            box.append (create_button);

            invite_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { visible = false };
            qr = new QrArea ();
            invite_box.append (qr);
            link_rows = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
            invite_box.append (link_rows);
            invite_expiry = new Gtk.Label ("") { halign = Gtk.Align.CENTER };
            invite_expiry.add_css_class (Granite.CssClass.DIM);
            invite_box.append (invite_expiry);
            box.append (invite_box);
            return box;
        }

        private Gtk.Box build_pending () {
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { visible = false };
            box.append (new Granite.HeaderLabel (_("Connection request")));
            pending_title = new Gtk.Label ("") { wrap = true, xalign = 0, halign = Gtk.Align.START };
            bold (pending_title);
            box.append (pending_title);
            var detail = new Gtk.Label (_("It will see your whole screen. Nothing is recorded.")) { wrap = true, xalign = 0, halign = Gtk.Align.START };
            detail.add_css_class (Granite.CssClass.DIM);
            box.append (detail);
            var buttons = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var deny = new Gtk.Button.with_label (_("Deny"));
            deny.clicked.connect (() => { answer.begin (Answer.DENY); });
            view_only_button = new Gtk.Button.with_label (_("View Only"));
            view_only_button.add_css_class (Granite.CssClass.SUGGESTED);
            view_only_button.clicked.connect (() => { answer.begin (Answer.VIEW_ONLY); });
            control_button = new Gtk.Button.with_label (_("Allow Control"));
            control_button.add_css_class (Granite.CssClass.DESTRUCTIVE);
            control_button.clicked.connect (() => { answer.begin (Answer.CONTROL); });
            buttons.append (deny);
            buttons.append (view_only_button);
            buttons.append (control_button);
            box.append (buttons);
            return box;
        }

        private Gtk.Box build_session () {
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { visible = false };
            box.append (new Granite.HeaderLabel (_("Active session")));
            session_title = new Gtk.Label ("") { wrap = true, xalign = 0, halign = Gtk.Align.START };
            bold (session_title);
            box.append (session_title);
            session_detail = new Gtk.Label ("") { wrap = true, xalign = 0, halign = Gtk.Align.START };
            session_detail.add_css_class (Granite.CssClass.DIM);
            box.append (session_detail);

            control_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            var ctext = new Gtk.Label (_("Allow remote control")) { hexpand = true, xalign = 0 };
            control_switch = new Gtk.Switch () { valign = Gtk.Align.CENTER };
            control_switch.update_property (Gtk.AccessibleProperty.LABEL, _("Allow remote control"), -1);
            control_switch.notify["active"].connect (() => {
                if (updating) return;
                service.set_control.begin (control_switch.active);
            });
            control_row.append (ctext);
            control_row.append (control_switch);
            box.append (control_row);

            var end = new Gtk.Button.with_label (_("End Session"));
            end.add_css_class (Granite.CssClass.DESTRUCTIVE);
            end.halign = Gtk.Align.START;
            end.clicked.connect (() => { service.end_session.begin (); });
            box.append (end);
            return box;
        }

        public async void create_invite () {
            create_button.sensitive = false;
            invite = yield service.create_invite (offer_control.active);
            create_button.sensitive = true;
            show_invite ();
        }

        private async void answer (Answer a) {
            var p = service.status.pending;
            if (p == null) return;
            yield service.decide (p.id, a != Answer.DENY, a == Answer.CONTROL);
        }

        private void show_invite () {
            if (expiry_tick != 0) {
                Source.remove (expiry_tick);
                expiry_tick = 0;
            }
            if (invite == null || invite.links.length == 0) {
                invite_box.visible = false;
                return;
            }
            qr.set_rows (invite.qr);
            for (var c = link_rows.get_first_child (); c != null; c = link_rows.get_first_child ()) link_rows.remove (c);
            foreach (var link in invite.links) link_rows.append (link_row (link));
            invite_box.visible = true;
            update_expiry ();
            expiry_tick = Timeout.add_seconds (1, () => {
                if (!update_expiry ()) {
                    expiry_tick = 0;
                    return Source.REMOVE;
                }
                return Source.CONTINUE;
            });
        }

        private bool update_expiry () {
            if (invite == null) return false;
            int64 left = invite.expires_ms - get_real_time () / 1000;
            if (left <= 0) {
                invite = null;
                invite_box.visible = false;
                return false;
            }
            invite_expiry.label = _("Link expires in %s").printf (Presentation.countdown (left));
            return true;
        }

        private Gtk.Widget link_row (Link link) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true };
            var label = new Gtk.Label (link.label) { xalign = 0, halign = Gtk.Align.START };
            var url = new Gtk.Label (link.url) { xalign = 0, halign = Gtk.Align.START, ellipsize = Pango.EllipsizeMode.MIDDLE, selectable = true };
            url.add_css_class (Granite.CssClass.DIM);
            url.add_css_class (Granite.CssClass.SMALL);
            text.append (label);
            text.append (url);
            var copy = new Gtk.Button.from_icon_name ("edit-copy-symbolic") { valign = Gtk.Align.CENTER, tooltip_text = _("Copy link") };
            copy.update_property (Gtk.AccessibleProperty.LABEL, _("Copy %s link").printf (link.label), -1);
            copy.clicked.connect (() => {
                get_clipboard ().set_text (link.url);
                toast.title = _("Link copied");
                toast.send_notification ();
            });
            row.append (text);
            row.append (copy);
            return row;
        }

        private void update () {
            var s = service.status;
            updating = true;
            if (!service.settled || s.phase == Phase.UNAVAILABLE) {
                stack.visible_child_name = service.settled ? "unavailable" : "main";
                updating = false;
                if (!service.settled) enable_subtitle.label = _("Looking for the service…");
                return;
            }
            stack.visible_child_name = "main";
            enable_switch.active = s.enabled;
            enable_subtitle.label = s.enabled
                ? _("Phones on your network or Tailscale can ask to connect. Nothing is shared until you approve.")
                : _("Nobody can connect.");
            // Never stack the idle controls over a live request or session.
            idle_box.visible = s.enabled && (s.phase == Phase.IDLE);
            pending_box.visible = s.phase == Phase.PENDING;
            session_box.visible = s.phase == Phase.ACTIVE || s.phase == Phase.GRACE;

            if (s.phase == Phase.PENDING && s.pending != null) {
                pending_title.label = _("“%s” wants to connect").printf (s.pending.device);
                control_button.visible = s.pending.control_offered;
            }
            if (session_box.visible && s.session != null) {
                session_title.label = Presentation.title (s);
                session_detail.label = Presentation.detail (s);
                control_row.visible = s.session.control_permitted;
                control_switch.active = s.session.control;
                control_switch.sensitive = s.phase == Phase.ACTIVE;
            }
            if (!idle_box.visible) {
                invite = null;
                invite_box.visible = false;
            }
            updating = false;
        }
    }
}
