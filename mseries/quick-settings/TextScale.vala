/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2024 elementary, Inc. (https://elementary.io)
 *
 * ElementaryOS_MSeries: replaces upstream's free 0.75–1.75 slider (0.05 steps)
 * with the size-system ladder in mseries/ui-scale/size-system.json, so the
 * buttons and the slider always land on a named step. Keep STEPS and NAMES in
 * sync with that file; mseries/ui-scale/test_ui_scale.py checks it.
 */

public class QuickSettings.TextScale : Gtk.Box {
    private const double[] STEPS = { 0.85, 0.92, 1.0, 1.1, 1.25, 1.5 };
    private const string[] NAMES = {
        N_("Compact"),
        N_("Small"),
        N_("Default"),
        N_("Large"),
        N_("Larger"),
        N_("Largest")
    };

    private Gtk.Button zoom_in_button;
    private Gtk.Button zoom_out_button;
    private Gtk.Scale zoom_scale;
    private Gtk.Adjustment zoom_adjustment;
    private Settings interface_settings;
    private bool syncing = false;
    private uint update_timeout_id = 0;

    class construct {
        set_css_name ("scalebox");
    }

    construct {
        zoom_out_button = new Gtk.Button.from_icon_name ("quick-settings-text-small-symbolic") {
            tooltip_text = _("Decrease text size"),
            valign = CENTER
        };
        zoom_out_button.add_css_class (Granite.CssClass.CIRCULAR);

        // The slider moves over step indexes, so every position is a ladder step
        // and the steps are evenly spaced regardless of their factors.
        zoom_adjustment = new Gtk.Adjustment (0, 0, STEPS.length - 1, 1, 1, 0);

        zoom_scale = new Gtk.Scale (HORIZONTAL, zoom_adjustment) {
            draw_value = false,
            hexpand = true,
            round_digits = 0
        };
        for (var i = 0; i < STEPS.length; i++) {
            zoom_scale.add_mark (i, BOTTOM, null);
        }

        zoom_in_button = new Gtk.Button.from_icon_name ("quick-settings-text-large-symbolic") {
            tooltip_text = _("Increase text size"),
            valign = CENTER
        };
        zoom_in_button.add_css_class (Granite.CssClass.CIRCULAR);

        add_css_class ("font-size");
        append (zoom_out_button);
        append (zoom_scale);
        append (zoom_in_button);

        interface_settings = new Settings ("org.gnome.desktop.interface");
        interface_settings.changed["text-scaling-factor"].connect (sync_from_settings);
        sync_from_settings ();

        zoom_adjustment.value_changed.connect (() => {
            var index = current_index ();
            if (zoom_adjustment.value != index) {
                zoom_adjustment.value = index;
                return;
            }
            update_labels (index);
            if (!syncing) {
                commit (index);
            }
        });

        zoom_in_button.clicked.connect (() => step (1));
        zoom_out_button.clicked.connect (() => step (-1));
    }

    private void commit (int index) {
        if (update_timeout_id != 0) {
            GLib.Source.remove (update_timeout_id);
        }
        // Coalesce drags so the popover does not reflow under the pointer at every mark.
        update_timeout_id = Timeout.add (350, () => {
            update_timeout_id = 0;
            if (interface_settings.get_double ("text-scaling-factor") != STEPS[index]) {
                interface_settings.set_double ("text-scaling-factor", STEPS[index]);
            }
            return GLib.Source.REMOVE;
        });
    }

    private int current_index () {
        return ((int) Math.round (zoom_adjustment.value)).clamp (0, STEPS.length - 1);
    }

    private static int nearest_index (double factor) {
        var best = 0;
        for (var i = 1; i < STEPS.length; i++) {
            if ((STEPS[i] - factor).abs () < (STEPS[best] - factor).abs ()) {
                best = i;
            }
        }
        return best;
    }

    private void step (int direction) {
        // While a coalesced write is pending, step from the slider, not the stale setting.
        var factor = update_timeout_id != 0 ? STEPS[current_index ()] : interface_settings.get_double ("text-scaling-factor");
        var index = nearest_index (factor);
        // Off-ladder values (left by older builds or other tools) step to the
        // adjacent ladder value in the pressed direction instead of skipping it.
        if ((STEPS[index] - factor).abs () < 0.0001 || (direction > 0) == (STEPS[index] < factor)) {
            index += direction;
        }
        index = index.clamp (0, STEPS.length - 1);
        if (index == current_index ()) {
            // The slider already shows this step; only the stored value is off-ladder.
            commit (index);
        } else {
            zoom_adjustment.value = index;
        }
    }

    private void sync_from_settings () {
        syncing = true;
        zoom_adjustment.value = nearest_index (interface_settings.get_double ("text-scaling-factor"));
        syncing = false;
        update_labels (current_index ());
    }

    private void update_labels (int index) {
        var label = _(NAMES[index]);
        var percent = (int) Math.round (STEPS[index] * 100);
        zoom_scale.tooltip_text = _("Text size: %s (%d%%)").printf (label, percent);
        zoom_scale.update_property (Gtk.AccessibleProperty.LABEL, _("Text size"), -1);
        zoom_scale.update_property (Gtk.AccessibleProperty.VALUE_TEXT, label, -1);

        var factor = interface_settings.get_double ("text-scaling-factor");
        zoom_out_button.sensitive = index > 0 || factor > STEPS[0] + 0.0001;
        zoom_in_button.sensitive = index < STEPS.length - 1 || factor < STEPS[STEPS.length - 1] - 0.0001;
    }
}
