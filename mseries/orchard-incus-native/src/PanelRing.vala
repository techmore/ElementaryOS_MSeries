private class OrchardPanelRing : Gtk.DrawingArea {
    private double fraction = 0;
    private bool known = false;
    private bool memory;
    public OrchardPanelRing (bool memory_ring = false) {
        memory = memory_ring;
        content_width = 18; content_height = 18;
        set_draw_func ((area, cr, width, height) => {
            double radius = double.min (width, height) / 2.0 - 2;
            cr.set_line_width (2.5);
            cr.set_source_rgba (0.5, 0.5, 0.5, 0.35);
            cr.arc (width / 2.0, height / 2.0, radius, 0, Math.PI * 2); cr.stroke ();
            if (known) {
                if (memory) cr.set_source_rgba (0.41, 0.72, 0.14, 1); else cr.set_source_rgba (0.21, 0.54, 0.9, 1);
                cr.arc (width / 2.0, height / 2.0, radius, -Math.PI / 2, -Math.PI / 2 + fraction * Math.PI * 2); cr.stroke ();
            }
        });
    }
    public void update (double value, bool available) { fraction = double.min (1, double.max (0, value)); known = available; queue_draw (); }
}
