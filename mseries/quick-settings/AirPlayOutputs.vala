/* SPDX-License-Identifier: GPL-3.0-or-later
 * "AirPlay" row for the Sound Output list in the Quick Settings gear menu. Clicking the row opens
 * one dot per AirPlay receiver found on the network; a filled dot means that receiver is active.
 * Clicking a dot enables or disables it. The work is done by `mseries-airplay-outputs` (see
 * mseries/airplay/): active receivers play together as the "AirPlay Group" output, which is
 * chosen in the Sound Output list above like any other output. Nothing here touches the default
 * output. MSERIES_AIRPLAY_BIN overrides the helper path (used by the headless render test). */
public class QuickSettings.AirPlayOutputs : Gtk.Box {
    private Gtk.Revealer revealer;
    private Gtk.Box dots;
    private Gtk.Label summary;
    private Gtk.Image chevron;
    private uint refresh_id = 0;
    private bool refreshing = false;
    private bool busy = false;
    private static bool css_loaded = false;

    construct {
        orientation = VERTICAL;
        spacing = 0;

        if (!css_loaded) {
            css_loaded = true;
            var css = new Gtk.CssProvider ();
            css.load_from_string (
                "button.airplay-dot { min-width: 20px; min-height: 20px; padding: 0; border-radius: 999px;" +
                " border: 2px solid alpha(currentColor, 0.55); background: transparent; }" +
                "button.airplay-dot:checked { background: @accent_color; border-color: @accent_color; }" +
                "button.airplay-dot:hover { border-color: @accent_color; }");
            Gtk.StyleContext.add_provider_for_display (Gdk.Display.get_default (), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        }

        var name = new Gtk.Label (_("AirPlay")) { xalign = 0, hexpand = true };
        summary = new Gtk.Label ("") { xalign = 1 };
        summary.add_css_class ("dim-label");
        summary.add_css_class ("caption");
        chevron = new Gtk.Image.from_icon_name ("pan-end-symbolic");
        var line = new Gtk.Box (HORIZONTAL, 9);
        line.append (new Gtk.Image.from_icon_name ("network-wireless-symbolic"));
        line.append (name);
        line.append (summary);
        line.append (chevron);
        var header = new Gtk.Button () { child = line };
        header.add_css_class ("flat");
        header.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { _("AirPlay outputs") });

        dots = new Gtk.Box (VERTICAL, 0) { margin_start = 12 };
        revealer = new Gtk.Revealer () { child = dots, transition_type = SLIDE_DOWN };
        header.clicked.connect (() => {
            revealer.reveal_child = !revealer.reveal_child;
            chevron.icon_name = revealer.reveal_child ? "pan-down-symbolic" : "pan-end-symbolic";
        });
        append (header);
        append (revealer);

        // Always visible so it still gets map signals; contents hide when no receiver exists.
        header.visible = false;
        map.connect (() => {
            refresh.begin ();
            refresh_id = Timeout.add_seconds (3, () => {
                refresh.begin ();
                return Source.CONTINUE;
            });
        });
        unmap.connect (() => {
            if (refresh_id != 0) {
                Source.remove (refresh_id);
                refresh_id = 0;
            }
        });
    }

    private static string helper () {
        var over = Environment.get_variable ("MSERIES_AIRPLAY_BIN");
        return over ?? Path.build_filename (Environment.get_home_dir (), ".local", "bin", "mseries-airplay-outputs");
    }

    private async string? run (string[] args) {
        try {
            string[] argv = { helper () };
            foreach (var a in args) argv += a;
            var process = new Subprocess.newv (argv, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_SILENCE);
            string? out_text;
            yield process.communicate_utf8_async (null, null, out out_text, null);
            return process.get_successful () ? out_text : null;
        } catch (Error e) {
            return null;
        }
    }

    private async void refresh () {
        if (refreshing || busy) return;
        refreshing = true;
        var text = yield run ({ "json" });
        rebuild (text);
        refreshing = false;
    }

    private void rebuild (string? text) {
        var header = (Gtk.Widget) get_first_child ();
        for (var child = dots.get_first_child (); child != null; child = dots.get_first_child ()) {
            dots.remove (child);
        }
        var parser = new Json.Parser ();
        try {
            if (text == null) throw new IOError.FAILED ("no output");
            parser.load_from_data (text);
        } catch (Error e) {
            header.visible = false;
            revealer.reveal_child = false;
            return;
        }
        var array = parser.get_root ().get_array ();
        header.visible = array.get_length () > 0;
        int on = 0;
        foreach (var node in array.get_elements ()) {
            var obj = node.get_object ();
            var key = obj.get_string_member ("key");
            var label = obj.get_string_member ("name");
            bool enabled = obj.get_boolean_member ("enabled");
            if (enabled) on++;

            var dot = new Gtk.ToggleButton () { active = enabled, valign = CENTER, tooltip_text = enabled ? _("On – click to turn off") : _("Off – click to turn on") };
            dot.add_css_class ("airplay-dot");
            dot.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { label });
            dot.toggled.connect (() => { toggle.begin (key); });
            var row = new Gtk.Box (HORIZONTAL, 9) { margin_top = 4, margin_bottom = 4, margin_start = 6 };
            row.append (dot);
            row.append (new Gtk.Label (label) { xalign = 0, hexpand = true, ellipsize = END, max_width_chars = 26 });
            dots.append (row);
        }
        summary.label = on > 0 ? _("%d on").printf (on) : "";
    }

    private async void toggle (string key) {
        busy = true;
        yield run ({ "toggle", key });
        busy = false;
        refresh.begin ();
    }
}
