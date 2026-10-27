/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Touch ID in elementary OS System Settings, under Personal. */
namespace MSeriesTouchId {
    public class Plug : Switchboard.Plug {
        private TouchIdPage? page = null;
        private Gtk.Widget? content = null;

        public Plug () {
            var supported = new Gee.TreeMap<string, string?> (null, null);
            supported.set ("personal/touch-id", "Touch ID");
            Object (
                category: Category.PERSONAL,
                code_name: "io.elementary.settings.mseries-touch-id",
                display_name: "Touch ID",
                description: "Add fingerprints and choose what they unlock",
                icon: "fingerprint",
                supported_settings: supported
            );
        }

        public override Gtk.Widget get_widget () {
            if (content == null) {
                page = new TouchIdPage ();
            // Settings hides its own titlebar and puts the plug straight into a navigation page, so the
            // plug supplies the header bar: drag area, back button and the window buttons.
            var headerbar = new Adw.HeaderBar () {
                show_title = false
            };
            headerbar.add_css_class ("flat");
            page.vexpand = true;
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            box.append (headerbar);
            box.append (page);
            content = box;
            }
            return content;
        }

        /* Probe the sensor only when the page is opened, never when Settings starts. */
        public override void shown () {
            get_widget ();
            page.refresh.begin ();
        }

        public override void hidden () {}

        public override void search_callback (string location) {}

        public override async Gee.TreeMap<string, string> search (string query) {
            var results = new Gee.TreeMap<string, string> (
                (GLib.CompareDataFunc<string>) strcmp,
                (Gee.EqualDataFunc<string>) str_equal
            );
            results.set ("Touch ID", "fingerprints");
            results.set ("Touch ID → Add Fingerprint", "fingerprints");
            results.set ("Touch ID → Fingerprints", "fingerprints");
            results.set ("Touch ID → Terminal Commands", "use-for");
            results.set ("Touch ID → System Authorization", "use-for");
            return results;
        }
    }
}

public Switchboard.Plug get_plug (Module module) {
    return new MSeriesTouchId.Plug ();
}
