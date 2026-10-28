/* SPDX-License-Identifier: GPL-3.0-or-later */
namespace MSeries.Remote {
    /* Section/card titles: bold, without depending on a stylesheet class. */
    public void bold (Gtk.Label label) {
        var attrs = new Pango.AttrList ();
        attrs.insert (Pango.attr_weight_new (Pango.Weight.BOLD));
        label.attributes = attrs;
    }
}
