/* SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 ElementaryOS_MSeries
 * Use the same appearance backend as the former standalone panel indicator.
 */
public class QuickSettings.Appearance : Gtk.Box {
    private Gtk.ToggleButton light_button;
    private Gtk.ToggleButton dark_button;
    private Gtk.ToggleButton auto_button;
    private Gtk.Label detail;
    private bool busy = false;
    private bool refreshing = false;
    private uint timer = 0;

    construct {
        orientation = Gtk.Orientation.VERTICAL;
        spacing = 8;
        margin_start = 12;
        margin_end = 12;
        margin_top = 8;
        margin_bottom = 8;

        var title = new Gtk.Label (_("Appearance")) { xalign = 0 };
        title.add_css_class ("heading");
        append (title);
        light_button = new Gtk.ToggleButton.with_label (_("Light")) { hexpand = true };
        dark_button = new Gtk.ToggleButton.with_label (_("Dark")) { hexpand = true, group = light_button };
        auto_button = new Gtk.ToggleButton.with_label (_("Automatic")) { hexpand = true, group = light_button };
        light_button.tooltip_text = _("Use the light appearance");
        dark_button.tooltip_text = _("Use the dark appearance");
        auto_button.tooltip_text = _("Follow the appearance schedule");
        light_button.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { _("Light appearance") });
        dark_button.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { _("Dark appearance") });
        auto_button.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { _("Automatic appearance") });
        var choices = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        choices.add_css_class ("linked");
        choices.append (light_button);
        choices.append (dark_button);
        choices.append (auto_button);
        append (choices);
        detail = new Gtk.Label (_("Reading appearance…")) { xalign = 0, wrap = true, max_width_chars = 36 };
        detail.add_css_class ("dim-label");
        append (detail);
        light_button.clicked.connect (() => choose.begin ("light"));
        dark_button.clicked.connect (() => choose.begin ("dark"));
        auto_button.clicked.connect (() => choose.begin ("auto"));
        set_choices_sensitive (false);
        map.connect (() => {
            refresh.begin ();
            timer = Timeout.add_seconds (10, () => {
                refresh.begin ();
                return Source.CONTINUE;
            });
        });
        unmap.connect (() => {
            if (timer != 0) {
                Source.remove (timer);
                timer = 0;
            }
        });
    }

    private void set_choices_sensitive (bool value) {
        light_button.sensitive = value;
        dark_button.sensitive = value;
        auto_button.sensitive = value;
    }

    private async string command (string[] args) throws Error {
        var process = new Subprocess.newv (args, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
        string output;
        string errors;
        yield process.communicate_utf8_async (null, null, out output, out errors);
        if (!process.get_successful () || errors.strip () != "") {
            throw new IOError.FAILED (errors.strip () != "" ? errors.strip () : _("Appearance command failed"));
        }
        return output;
    }

    private async void refresh () {
        if (busy || refreshing) return;
        refreshing = true;
        try {
            var output = yield command ({ "mseries-dark-mode", "status", "--json" });
            var parser = new Json.Parser ();
            parser.load_from_data (output);
            var data = parser.get_root ().get_object ();
            var mode = data.get_string_member ("mode");
            light_button.active = mode == "light";
            dark_button.active = mode == "dark";
            auto_button.active = mode == "auto";
            detail.label = data.get_string_member ("summary") + "\n" + data.get_string_member ("detail");
            set_choices_sensitive (true);
        } catch (Error e) {
            detail.label = _("Appearance status unavailable: %s").printf (e.message);
            set_choices_sensitive (false);
        }
        refreshing = false;
    }

    private async void choose (string mode) {
        if (busy || refreshing) return;
        busy = true;
        set_choices_sensitive (false);
        detail.label = _("Applying appearance…");
        string? failure = null;
        try {
            yield command ({ "mseries-dark-mode", "appearance", mode });
        } catch (Error e) {
            failure = e.message;
        }
        busy = false;
        yield refresh ();
        if (failure != null) detail.label = _("Could not change appearance: %s").printf (failure);
    }
}
