/* SPDX-License-Identifier: GPL-3.0-or-later */
namespace MSeries.Remote {
    /* Draws the invite QR from rows of '0'/'1' with the required quiet zone.
     * Always black on white: a QR on a dark theme background does not scan. */
    public class QrArea : Gtk.DrawingArea {
        private string[] rows = {};

        public QrArea () {
            Object (content_width: 208, content_height: 208, halign: Gtk.Align.CENTER);
            add_css_class ("remote-qr");
            update_property (Gtk.AccessibleProperty.LABEL, _("QR code for the connection link"), -1);
            set_draw_func (draw);
        }

        public void set_rows (string[] new_rows) {
            rows = new_rows;
            queue_draw ();
        }

        private void draw (Gtk.DrawingArea area, Cairo.Context cr, int width, int height) {
            cr.set_source_rgb (1, 1, 1);
            cr.paint ();
            int n = rows.length;
            if (n == 0) return;
            const int QUIET = 4;
            double cell = Math.floor (double.min (width, height) / (double) (n + 2 * QUIET));
            if (cell < 1) cell = 1;
            double ox = (width - cell * n) / 2, oy = (height - cell * n) / 2;
            cr.set_source_rgb (0, 0, 0);
            for (int y = 0; y < n; y++) {
                for (int x = 0; x < rows[y].length && x < n; x++) {
                    if (rows[y].get_char (rows[y].index_of_nth_char (x)) == '1') {
                        cr.rectangle (ox + x * cell, oy + y * cell, cell, cell);
                    }
                }
            }
            cr.fill ();
        }
    }
}
