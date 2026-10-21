/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Dock & Taskbar in elementary OS System Settings, under Personal. */
namespace MSeriesDockSwitcher {
    public class Plug : Switchboard.Plug {
        private DockPage? page = null;

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
            if (page == null) {
                page = new DockPage ();
            }
            return page;
        }

        public override void shown () {
            ((DockPage) get_widget ()).refresh ();
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
