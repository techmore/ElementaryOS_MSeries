public class OrchardSparkline : Gtk.DrawingArea {
    private double[] samples = {};
    private int64[] timestamps = {};
    private uint sample_limit;
    public uint sample_count { get { return (uint) samples.length; } }
    public OrchardSparkline (uint limit = 28800) {
        sample_limit = uint.max (2, limit);
        content_height = 90;
        hexpand = true;
        set_draw_func ((area, cr, width, height) => {
            if (samples.length < 2) return;
            double maximum = 0.01;
            foreach (var value in samples) maximum = double.max (maximum, value);
            Gdk.RGBA accent;
            if (!get_style_context ().lookup_color ("accent_color", out accent)) accent = get_color ();
            cr.set_source_rgba (accent.red, accent.green, accent.blue, 0.9);
            cr.set_line_width (2);
            double span = double.max (1, timestamps[timestamps.length - 1] - timestamps[0]);
            for (int i = 0; i < samples.length; i++) {
                double x = (timestamps[i] - timestamps[0]) / span * (width - 4) + 2;
                double y = height - 4 - samples[i] / maximum * (height - 8);
                if (i == 0 || timestamps[i] - timestamps[i - 1] > 30) cr.move_to (x, y); else cr.line_to (x, y);
            }
            cr.stroke ();
        });
    }
    public void record (double value, int64 timestamp = 0) {
        if (timestamp == 0) timestamp = new DateTime.now_utc ().to_unix ();
        int trim = 0;
        while (trim < timestamps.length && (timestamps[trim] < timestamp - 86400 || samples.length - trim >= sample_limit)) trim++;
        if (trim > 0) { samples = samples[trim:samples.length]; timestamps = timestamps[trim:timestamps.length]; }
        samples += value; timestamps += timestamp;
        queue_draw ();
    }
}
