/* SPDX-License-Identifier: GPL-3.0-or-later
 * Mac-style "Sound Output" list for the Quick Settings gear menu. Every PipeWire sink is a row
 * (built-in speakers and headphones, Bluetooth, AirPlay, USB, displays) with its connection type
 * underneath; clicking a row makes it the default output through wpctl and WirePlumber moves the
 * playing streams. The section is one line (the current output) until opened, because a Mac with
 * AirPlay receivers on the network can have a long list. It is re-read each time the menu opens and
 * every few seconds while open. */
public class QuickSettings.AudioOutput : Gtk.Box {
    private Gtk.Box rows;
    private Gtk.Button header;
    private Gtk.Image header_icon;
    private Gtk.Label current;
    private Gtk.Image chevron;
    private Gtk.Revealer revealer;
    private uint refresh_id = 0;
    private bool refreshing = false;

    construct {
        orientation = VERTICAL;
        spacing = 0;

        // This widget stays visible so it still gets map signals; only its contents hide when
        // there is nothing to list (a hidden widget is never mapped, so it would never refresh).
        header_icon = new Gtk.Image.from_icon_name ("audio-speakers-symbolic");
        var name = new Gtk.Label (_("Sound Output")) { xalign = 0 };
        current = new Gtk.Label ("") { xalign = 0, ellipsize = END, max_width_chars = 30 };
        current.add_css_class ("dim-label");
        current.add_css_class ("caption");
        var text = new Gtk.Box (VERTICAL, 0) { hexpand = true, valign = CENTER };
        text.append (name);
        text.append (current);
        chevron = new Gtk.Image.from_icon_name ("pan-end-symbolic");
        var line = new Gtk.Box (HORIZONTAL, 9);
        line.append (header_icon);
        line.append (text);
        line.append (chevron);
        header = new Gtk.Button () { child = line, visible = false };
        header.add_css_class ("flat");
        header.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { _("Sound Output") });

        rows = new Gtk.Box (VERTICAL, 0);
        var body = new Gtk.Box (VERTICAL, 0);
        body.append (rows);
        body.append (new AirPlayOutputs ());
        revealer = new Gtk.Revealer () { child = body, transition_type = SLIDE_DOWN };
        header.clicked.connect (() => { set_expanded (!revealer.reveal_child); });
        append (header);
        append (revealer);

        map.connect (() => {
            set_expanded (false);
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

    private void set_expanded (bool open) {
        revealer.reveal_child = open;
        chevron.icon_name = open ? "pan-down-symbolic" : "pan-end-symbolic";
        header.tooltip_text = open ? _("Hide outputs") : _("Choose an output");
    }

    private async void refresh () {
        if (refreshing) return;
        refreshing = true;
        try {
            var process = new Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_SILENCE, "pw-dump");
            string? stdout_text;
            yield process.communicate_utf8_async (null, null, out stdout_text, null);
            rebuild (AudioOutputModel.parse (stdout_text ?? "[]"));
        } catch (Error e) {
            info ("Sound outputs unavailable: %s", e.message);
            header.visible = false;
            revealer.visible = false;
        }
        refreshing = false;
    }

    private void rebuild (GenericArray<AudioOutputInfo> outputs) {
        for (var child = rows.get_first_child (); child != null; child = rows.get_first_child ()) {
            rows.remove (child);
        }
        header.visible = outputs.length > 0;
        revealer.visible = outputs.length > 0;
        current.label = "";
        foreach (var output in outputs) {
            rows.append (build_row (output));
            if (output.is_default) {
                current.label = output.description;
                header_icon.icon_name = output.icon_name;
            }
        }
    }

    private Gtk.Widget build_row (AudioOutputInfo output) {
        var name = new Gtk.Label (output.description) { xalign = 0, ellipsize = END, max_width_chars = 28 };
        var kind = new Gtk.Label (output.transport.to_label ()) { xalign = 0 };
        kind.add_css_class ("dim-label");
        kind.add_css_class ("caption");
        var text = new Gtk.Box (VERTICAL, 0) { hexpand = true, valign = CENTER };
        text.append (name);
        text.append (kind);

        var line = new Gtk.Box (HORIZONTAL, 9);
        line.append (new Gtk.Image.from_icon_name (output.icon_name));
        line.append (text);
        line.append (new Gtk.Image.from_icon_name ("object-select-symbolic") { opacity = output.is_default ? 1 : 0 });

        var button = new Gtk.Button () { child = line, tooltip_text = "%s – %s".printf (output.description, output.transport.to_label ()) };
        button.add_css_class ("flat");
        button.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { "%s, %s".printf (output.description, output.transport.to_label ()) });
        var id = output.id;
        button.clicked.connect (() => { select.begin (id); });
        return button;
    }

    private async void select (uint id) {
        try {
            var process = new Subprocess (SubprocessFlags.STDOUT_SILENCE | SubprocessFlags.STDERR_SILENCE,
                "wpctl", "set-default", id.to_string ());
            yield process.wait_check_async ();
        } catch (Error e) {
            warning ("Could not switch sound output: %s", e.message);
        }
        set_expanded (false);
        refresh.begin ();
    }
}
