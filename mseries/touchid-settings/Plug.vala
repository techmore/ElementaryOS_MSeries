/* Touch ID in elementary OS System Settings, under Personal. */
namespace MSeriesTouchId {
    public class Plug : Switchboard.Plug {
        private TouchIdPage? page = null;

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
            if (page == null) {
                page = new TouchIdPage ();
            }
            return page;
        }

        /* Probe the sensor only when the page is opened, never when Settings starts. */
        public override void shown () {
            ((TouchIdPage) get_widget ()).refresh.begin ();
        }

        public override void hidden () {}

        public override void search_callback (string location) {}

        public override async Gee.TreeMap<string, string> search (string query) {
            var results = new Gee.TreeMap<string, string> (
                (GLib.CompareDataFunc<string>) strcmp,
                (Gee.EqualDataFunc<string>) str_equal
            );
            results.set ("Touch ID", "");
            results.set ("Touch ID → Add Fingerprint", "");
            results.set ("Touch ID → Fingerprints", "");
            results.set ("Touch ID → Terminal Commands", "");
            results.set ("Touch ID → System Authorization", "");
            return results;
        }
    }
}

public Switchboard.Plug get_plug (Module module) {
    return new MSeriesTouchId.Plug ();
}
