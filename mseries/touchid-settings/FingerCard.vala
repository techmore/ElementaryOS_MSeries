/* SPDX-License-Identifier: GPL-3.0-or-later */
/* A tile for one enrolled finger, and the dashed "Add Fingerprint" tile. */
namespace MSeriesTouchId {
    public class FingerCard : Adw.Bin {
        public signal void remove_requested (string finger);

        public string finger { get; construct; }

        public FingerCard (string finger) {
            Object (finger: finger);
            var label = finger_label (finger);

            var art = new FingerprintArt (60, 8, 2.6) { lit = true };
            art.update_property (Gtk.AccessibleProperty.LABEL, "Fingerprint", -1);

            var name = new Gtk.Label (label) {
                wrap = true,
                justify = Gtk.Justification.CENTER,
                max_width_chars = 16
            };
            name.add_css_class ("mst-card-name");
            var note = new Gtk.Label ("Touch ID");
            note.add_css_class ("dim-label");
            note.add_css_class ("caption");

            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
                halign = Gtk.Align.FILL,
                valign = Gtk.Align.CENTER,
                margin_top = 10,
                margin_bottom = 6
            };
            box.add_css_class ("card");
            box.add_css_class ("mst-card");
            box.append (art);
            box.append (name);
            box.append (note);
            var overlay = new Gtk.Overlay () { child = box };
            child = overlay;

            var remove = new Gtk.Button.from_icon_name ("edit-delete-symbolic") {
                halign = Gtk.Align.END,
                valign = Gtk.Align.START,
                margin_top = 6,
                margin_end = 6,
                tooltip_text = "Remove %s".printf (label.down ())
            };
            remove.add_css_class ("flat");
            remove.add_css_class ("circular");
            remove.add_css_class ("mst-remove");
            remove.update_property (Gtk.AccessibleProperty.LABEL, "Remove %s".printf (label.down ()), -1);
            remove.clicked.connect (() => remove_requested (finger));
            overlay.add_overlay (remove);
        }
    }

    public class AddTile : Gtk.Button {
        public AddTile () {
            var icon = new Gtk.Image.from_icon_name ("list-add-symbolic") { pixel_size = 28 };
            var label = new Gtk.Label ("Add Fingerprint") { wrap = true, justify = Gtk.Justification.CENTER };
            label.add_css_class ("heading");
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
                halign = Gtk.Align.CENTER,
                valign = Gtk.Align.CENTER
            };
            box.append (icon);
            box.append (label);
            child = box;
            add_css_class ("mst-add-tile");
            add_css_class ("flat");
            update_property (Gtk.AccessibleProperty.LABEL, "Add Fingerprint", -1);
        }
    }
}
