/* Keep the date and time visible in Wingpanel's right-hand indicator area. */
using GLib;
using Gtk;
using Wingpanel;

private class RightClockIndicator : Wingpanel.Indicator {
    private Gtk.Box display;
    private Gtk.Label clock_label;
    private GLib.Settings settings;
    private uint update_timer = 0;

    public RightClockIndicator () {
        GLib.Object (code_name: "clockright");
    }

    construct {
        settings = new GLib.Settings ("io.elementary.desktop.wingpanel.datetime");
        display = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        clock_label = new Gtk.Label ("") {
            xalign = 0.5f,
            halign = Gtk.Align.CENTER
        };
        clock_label.add_css_class ("numeric");
        display.append (clock_label);
        display.set_tooltip_text ("Date and time");
        visible = true;

        update_clock ();
        settings.changed.connect ((key) => {
            if (key == "clock-show-seconds") {
                start_timer ();
            }
            update_clock ();
        });
        start_timer ();
    }

    // The tick rate follows the "show seconds" setting, including when it is
    // changed while the panel is running.
    private void start_timer () {
        if (update_timer != 0) {
            Source.remove (update_timer);
        }
        update_timer = Timeout.add_seconds (
            settings.get_boolean ("clock-show-seconds") ? 1 : 15,
            () => { update_clock (); return Source.CONTINUE; }
        );
    }

    private void update_clock () {
        var now = new DateTime.now_local ();
        string date_text = "";
        if (settings.get_boolean ("clock-show-weekday")) {
            date_text = now.format ("%a");
        }
        if (settings.get_boolean ("clock-show-date")) {
            var date = now.format ("%b %e").strip ();
            date_text = date_text.length > 0 ? date_text + " " + date : date;
        }

        var format = settings.get_string ("clock-format");
        var time_text = format == "24h" ? now.format ("%H:%M") :
            format == "ISO8601" ? now.format ("%Y-%m-%d %H:%M") :
            now.format (settings.get_boolean ("clock-show-seconds") ? "%I:%M:%S %p" : "%I:%M %p");
        clock_label.set_text (date_text.length > 0 ? date_text + "   " + time_text : time_text);
    }

    public override Gtk.Widget get_display_widget () {
        return display;
    }

    public override Gtk.Widget? get_widget () {
        return null;
    }

    public override void opened () { }
    public override void closed () { }

    public override void dispose () {
        if (update_timer != 0) {
            Source.remove (update_timer);
            update_timer = 0;
        }
        base.dispose ();
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) {
        return null;
    }
    return new RightClockIndicator ();
}
