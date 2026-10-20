public class Application : Gtk.Application {
    private weak MainWindow? main_window;
    public Application () {
        Object (application_id: "com.github.techmore.orchard-incus",
                flags: ApplicationFlags.HANDLES_OPEN);
    }

    protected override void startup () {
        base.startup ();
        Granite.init ();
        var gtk_settings = Gtk.Settings.get_default ();
        var granite_settings = Granite.Settings.get_default ();
        gtk_settings.gtk_application_prefer_dark_theme =
            granite_settings.prefers_color_scheme == Granite.Settings.ColorScheme.DARK;
        granite_settings.notify["prefers-color-scheme"].connect (() => {
            gtk_settings.gtk_application_prefer_dark_theme =
                granite_settings.prefers_color_scheme == Granite.Settings.ColorScheme.DARK;
        });
    }

    protected override void activate () {
        if (main_window == null) {
            var window = new MainWindow (this);
            main_window = window;
            main_window.close_request.connect (() => { main_window = null; return false; });
        }
        main_window.present ();
    }

    protected override void open (File[] files, string hint) {
        activate ();
        foreach (var file in files) main_window.navigate_uri (file.get_uri ());
    }

    public static int main (string[] args) {
        return new Application ().run (args);
    }
}
