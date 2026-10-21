/* SPDX-License-Identifier: GPL-3.0-or-later
 * Wingpanel indicator for Remote Desktop. Visible only while sharing is on;
 * switches to a "sharing" glyph (and says so in its tooltip) for the whole
 * time a phone can see the screen, so the owner always has an at-a-glance
 * consent indicator. */
using Wingpanel;

namespace MSeries.Remote {
    public class Indicator : Wingpanel.Indicator {
        private Service service;
        private Gtk.Image icon;
        private Gtk.Box menu;
        private Gtk.Label title_label;
        private Gtk.Label detail_label;
        private Gtk.Button primary;
        private Gtk.Button end_button;
        private Gtk.Button open_button;

        public Indicator () {
            Object (code_name: "mseries-remote");
        }

        construct {
            icon = new Gtk.Image.from_icon_name ("mseries-remote-symbolic") { pixel_size = 16 };
            icon.update_property (Gtk.AccessibleProperty.LABEL, _("Remote Desktop"), -1);

            title_label = new Gtk.Label ("") { xalign = 0, wrap = true, max_width_chars = 32 };
            bold (title_label);
            detail_label = new Gtk.Label ("") { xalign = 0, wrap = true, max_width_chars = 32 };
            detail_label.add_css_class (Granite.CssClass.DIM);
            primary = new Gtk.Button.with_label ("");
            primary.add_css_class (Granite.CssClass.SUGGESTED);
            end_button = new Gtk.Button.with_label (_("End Session"));
            end_button.add_css_class (Granite.CssClass.DESTRUCTIVE);
            open_button = new Gtk.Button.with_label (_("Open Remote Desktop…"));
            open_button.add_css_class ("flat");

            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
                margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12, width_request = 280
            };
            menu.append (title_label);
            menu.append (detail_label);
            menu.append (primary);
            menu.append (end_button);
            menu.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
            menu.append (open_button);

            open_button.clicked.connect (() => {
                close ();
                launch_app ();
            });
            end_button.clicked.connect (() => {
                service.end_session.begin ();
                close ();
            });
            primary.clicked.connect (() => {
                close ();
                launch_app ();
            });

            service = new Service ();
            service.changed.connect (update);
            service.start ();
            visible = false;
            update ();
        }

        private void launch_app () {
            try {
                Process.spawn_command_line_async ("mseries-remote");
            } catch (Error e) {
                warning ("cannot open Remote Desktop: %s", e.message);
            }
        }

        private void update () {
            var s = service.status;
            visible = Presentation.indicator_visible (s);
            icon.icon_name = Presentation.icon_name (s);
            icon.tooltip_text = Presentation.tooltip (s);
            title_label.label = Presentation.title (s);
            detail_label.label = Presentation.detail (s);
            end_button.visible = s.phase == Phase.ACTIVE || s.phase == Phase.GRACE;
            primary.visible = s.phase == Phase.PENDING || s.phase == Phase.IDLE;
            primary.label = s.phase == Phase.PENDING ? _("Answer…") : _("Connect a Phone…");
            if (Presentation.sharing_now (s)) icon.add_css_class ("remote-sharing"); else icon.remove_css_class ("remote-sharing");
        }

        public override Gtk.Widget get_display_widget () {
            return icon;
        }

        public override Gtk.Widget? get_widget () {
            return menu;
        }

        public override void opened () {
            service.refresh.begin ();
        }

        public override void closed () {
        }
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) return null;
    return new MSeries.Remote.Indicator ();
}
