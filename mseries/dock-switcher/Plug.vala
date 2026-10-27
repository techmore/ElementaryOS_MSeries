/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Dock & Taskbar in elementary OS System Settings, under Personal. */
namespace MSeriesDockSwitcher {
    public class Plug : Switchboard.Plug {
        private DockPage? page = null;
        private Gtk.Widget? content = null;

        public Plug () {
            var supported = new Gee.TreeMap<string, string?> (null, null);
            supported.set ("personal/dock-taskbar", "Dock & Taskbar");
            Object (
                category: Category.PERSONAL,
                code_name: "io.elementary.settings.mseries-dock-taskbar",
                display_name: "Dock & Taskbar",
                description: "Choose the Windows 11 taskbar or the elementary dock",
                icon: "preferences-desktop-applications",
                supported_settings: supported
            );
        }

        public override Gtk.Widget get_widget () {
            if (content == null) {
                page = new DockPage ();
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

        public override void shown () {
            get_widget ();
            page.refresh ();
        }

        public override void hidden () {
            if (page != null) {
                page.pause ();
            }
        }

        public override void search_callback (string location) {}

        public override async Gee.TreeMap<string, string> search (string query) {
            var results = new Gee.TreeMap<string, string> (
                (GLib.CompareDataFunc<string>) strcmp,
                (Gee.EqualDataFunc<string>) str_equal
            );
            results.set ("Dock & Taskbar", "style");
            results.set ("Dock & Taskbar → Windows 11 taskbar", "style");
            results.set ("Dock & Taskbar → elementary dock", "style");
            results.set ("Dock & Taskbar → Hide automatically", "style");
            return results;
        }
    }
}

public Switchboard.Plug get_plug (Module module) {
    return new MSeriesDockSwitcher.Plug ();
}
