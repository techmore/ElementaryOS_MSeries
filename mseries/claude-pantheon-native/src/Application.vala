public class Application : Gtk.Application {
    public static int64 launched = 0;
    private weak MainWindow? main_window;

    public Application () {
        Object (application_id: "io.github.techmore.ClaudePantheon",
                flags: ApplicationFlags.DEFAULT_FLAGS);
    }

    protected override void startup () {
        base.startup ();
        Granite.init ();
        var gtk_settings = Gtk.Settings.get_default ();
        // GTK animates the text cursor's fade with a frame-clock tick for ten
        // seconds after every keystroke, which repaints the window continuously.
        // A steady cursor keeps the app at 0% CPU whenever it is idle.
        gtk_settings.gtk_cursor_blink = false;
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
        set_accels_for_action ("win.new-chat", { "<Control>n" });
        set_accels_for_action ("win.find", { "<Control>f" });
        set_accels_for_action ("win.stop", { "Escape" });
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
        // On Asahi Mesa the GL/Vulkan renderers cost ~180 MB of shader heap for
        // a mostly static chat window; cairo renders the same UI in a third of
        // the memory. CLAUDE_PANTHEON_RENDERER=gl|ngl|vulkan overrides this.
        launched = get_monotonic_time ();
        var renderer = Environment.get_variable ("CLAUDE_PANTHEON_RENDERER");
        Environment.set_variable ("GSK_RENDERER", renderer ?? "cairo", true);
        return new Application ().run (args);
    }
}
