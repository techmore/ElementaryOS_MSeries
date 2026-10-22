public class Application : Gtk.Application {
    private weak MainWindow? main_window;

    public Application () {
        Object (application_id: "org.elementary.mseries.ImageStudio",
                flags: ApplicationFlags.DEFAULT_FLAGS);
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

        var quit = new SimpleAction ("quit", null);
        quit.activate.connect (() => { this.quit (); });
        add_action (quit);
        set_accels_for_action ("app.quit", { "<Control>q" });

        var about = new SimpleAction ("about", null);
        about.activate.connect (() => {
            var dialog = new Gtk.AboutDialog () {
                application = this,
                transient_for = active_window,
                modal = true,
                program_name = "Image Studio",
                version = "0.1.0",
                comments = "A native image creation workspace for ElementaryOS_MSeries."
            };
            dialog.present ();
        });
        add_action (about);
    }

    protected override void activate () {
        if (main_window == null) {
            var window = new MainWindow (this);
            main_window = window;
            main_window.close_request.connect (() => { main_window = null; return false; });
        }
        main_window.present ();
    }

    public static int main (string[] args) {
        Environment.set_variable ("GSK_RENDERER",
            Environment.get_variable ("M_SERIES_IMAGE_STUDIO_RENDERER") ?? "cairo", false);
        return new Application ().run (args);
    }
}
