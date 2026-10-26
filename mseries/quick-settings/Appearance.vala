/* SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 ElementaryOS_MSeries
 * Explicit Light/Dark choice in the session Quick Settings panel.
 */
public class QuickSettings.Appearance : Gtk.Box {
    private GLib.Settings settings;
    private Gtk.ToggleButton light_button;
    private Gtk.ToggleButton dark_button;
    private bool updating = false;

    construct {
        orientation = Gtk.Orientation.HORIZONTAL;
        spacing = 8;
        margin_start = 12;
        margin_end = 12;
        margin_top = 2;
        margin_bottom = 2;

        settings = new GLib.Settings ("io.elementary.settings-daemon.prefers-color-scheme");

        append (new Gtk.Image.from_icon_name ("dark-mode-symbolic") { pixel_size = 16 });
        var title = new Gtk.Label (_("Appearance")) {
            xalign = 0,
            hexpand = true
        };
        append (title);

        light_button = new Gtk.ToggleButton.with_label (_("Light"));
        dark_button = new Gtk.ToggleButton.with_label (_("Dark"));
        dark_button.set_group (light_button);
        light_button.add_css_class ("flat");
        dark_button.add_css_class ("flat");
        light_button.tooltip_text = _("Use the light appearance");
        dark_button.tooltip_text = _("Use the dark appearance");
        light_button.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { _("Light appearance") });
        dark_button.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { _("Dark appearance") });

        var choices = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        choices.add_css_class ("linked");
        choices.append (light_button);
        choices.append (dark_button);
        append (choices);

        light_button.toggled.connect (() => {
            if (!updating && light_button.active) {
                settings.set_enum ("color-scheme", Granite.Settings.ColorScheme.LIGHT);
            }
        });
        dark_button.toggled.connect (() => {
            if (!updating && dark_button.active) {
                settings.set_enum ("color-scheme", Granite.Settings.ColorScheme.DARK);
            }
        });

        settings.changed["color-scheme"].connect (sync_selection);
        settings.writable_changed["color-scheme"].connect (sync_selection);
        sync_selection ();
    }

    private void sync_selection () {
        updating = true;
        dark_button.active = settings.get_enum ("color-scheme") == Granite.Settings.ColorScheme.DARK;
        // Elementary's no-preference default presents as light; make that state actionable and
        // explicit by selecting Light until a dark preference is active.
        light_button.active = !dark_button.active;
        bool writable = settings.is_writable ("color-scheme");
        light_button.sensitive = writable;
        dark_button.sensitive = writable;
        if (!writable) {
            light_button.tooltip_text = _("Appearance is managed by your administrator");
            dark_button.tooltip_text = _("Appearance is managed by your administrator");
        }
        updating = false;
    }
}
