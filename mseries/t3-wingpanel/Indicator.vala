/* SPDX-License-Identifier: GPL-3.0 */
namespace MSeries {
    public class T3Indicator : Wingpanel.Indicator {
        private Gtk.Box display;
        private Gtk.Label badge;
        private Dock.TaskbarT3RPopover menu;
        // The embedded GitHub page is on-demand and never notifies. Keep exactly
        // one normal RepoBar instance as the existing background notification owner.
        private RepoBarIndicator notification_owner;

        public T3Indicator () {
            Object (code_name: "mseries-t3");
            display = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 3);
            display.append (new Gtk.Image.from_icon_name ("io.github.techmore.ClaudePantheonRs-symbolic"));
            badge = new Gtk.Label ("") { visible = false };
            badge.add_css_class ("caption");
            display.append (badge);
            display.update_property (Gtk.AccessibleProperty.LABEL, "T3 · Usage, GitHub, Activity and Fleet", -1);
            display.tooltip_text = "T3 · Usage, GitHub, Activity and Fleet";
            menu = new Dock.TaskbarT3RPopover (display, 28, true);
            menu.request_close.connect (() => close ());
            menu.status_changed.connect ((live, pending, running) => {
                badge.label = live && pending > 0 ? pending.to_string () :
                    live && running > 0 ? running.to_string () : "";
                badge.visible = badge.label.length > 0;
                display.tooltip_text = !live ? "T3 · No live server status" : pending > 0 ?
                    "T3 · %s awaiting approval".printf (pending.to_string ()) :
                    "T3 · %s running".printf (running.to_string ());
            });
            notification_owner = new RepoBarIndicator ();
            visible = true;
        }

        public override Gtk.Widget get_display_widget () { return display; }
        public override Gtk.Widget? get_widget () { return menu.get_host_widget (); }
        public override void opened () { menu.open_host (); }
        public override void closed () { menu.close_host (); }
        public override void dispose () {
            if (menu != null) { menu.dispose (); menu = null; }
            base.dispose ();
        }
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) return null;
    return new MSeries.T3Indicator ();
}
