/* SPDX-License-Identifier: GPL-3.0
 * Amber "microphone in use" light in the Windows taskbar status area, like macOS.
 * It reads the ALSA capture state, so it lights for any app holding a microphone. */
public class Dock.TaskbarMicLight : Gtk.Box {
    // The speaker codec's capture streams are speaker-protection sensing, not a microphone.
    private const string[] NOT_MICROPHONES = { "AppleJ314" };
    private uint poll_id = 0;

    construct {
        valign = Gtk.Align.CENTER;
        halign = Gtk.Align.CENTER;
        width_request = 8;
        height_request = 8;
        margin_start = 6;
        margin_end = 6;
        visible = false;
        add_css_class ("taskbar-mic-light");
        tooltip_text = _("Microphone in use");
        update_property (Gtk.AccessibleProperty.LABEL, _("Microphone in use"), -1);

        var css = new Gtk.CssProvider ();
        css.load_from_string (
            ".taskbar-mic-light { min-width: 8px; min-height: 8px; border-radius: 999px;" +
            " background-color: #ff9f0a; box-shadow: 0 0 4px alpha(#ff9f0a, 0.7); }");
        Gtk.StyleContext.add_provider_for_display (Gdk.Display.get_default (), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);

        // Poll from creation: the light starts hidden, and hidden widgets never map.
        refresh ();
        poll_id = Timeout.add (500, () => { refresh (); return Source.CONTINUE; });
    }

    private void stop_polling () {
        if (poll_id != 0) {
            Source.remove (poll_id);
            poll_id = 0;
        }
    }

    private void refresh () {
        var on = microphone_in_use ("/proc/asound");
        if (visible != on) visible = on;
    }

    /* True when any capture substream on a microphone card is running. */
    public static bool microphone_in_use (string root) {
        Dir cards;
        try {
            cards = Dir.open (root);
        } catch (FileError e) {
            return false;
        }
        string? card;
        while ((card = cards.read_name ()) != null) {
            if (!card.has_prefix ("card")) continue;
            var card_dir = Path.build_filename (root, card);
            string id;
            try {
                FileUtils.get_contents (Path.build_filename (card_dir, "id"), out id);
            } catch (FileError e) {
                continue;
            }
            if (id.strip () in NOT_MICROPHONES) continue;
            Dir pcms;
            try {
                pcms = Dir.open (card_dir);
            } catch (FileError e) {
                continue;
            }
            string? pcm;
            while ((pcm = pcms.read_name ()) != null) {
                if (!pcm.has_prefix ("pcm") || !pcm.has_suffix ("c")) continue;
                Dir subs;
                try {
                    subs = Dir.open (Path.build_filename (card_dir, pcm));
                } catch (FileError e) {
                    continue;
                }
                string? sub;
                while ((sub = subs.read_name ()) != null) {
                    if (!sub.has_prefix ("sub")) continue;
                    string status;
                    try {
                        FileUtils.get_contents (Path.build_filename (card_dir, pcm, sub, "status"), out status);
                    } catch (FileError e) {
                        continue;
                    }
                    if (status.has_prefix ("state: RUNNING")) return true;
                }
            }
        }
        return false;
    }

    public override void dispose () {
        stop_polling ();
        base.dispose ();
    }
}
