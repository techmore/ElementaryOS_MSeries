/* SPDX-License-Identifier: GPL-3.0
 * One native status-area entry for T3 usage, GitHub and daily activity. */
public class Dock.TaskbarT3 : Gtk.Box {
    private TaskbarT3RPopover menu;
    private Gtk.Image icon;
    private Settings settings = new Settings ("io.elementary.dock");

    construct {
        valign = Gtk.Align.CENTER;
        var button = new Gtk.Button () { valign = Gtk.Align.CENTER };
        button.add_css_class ("flat");
        button.add_css_class ("taskbar-codexbar-button");
        button.update_property (Gtk.AccessibleProperty.LABEL, "T3 · Usage, GitHub and Activity", -1);
        icon = new Gtk.Image.from_icon_name ("io.github.techmore.ClaudePantheonRs");
        button.child = icon;
        append (button);
        menu = new TaskbarT3RPopover (button, ItemManager.get_icon_size () * 7 / 12);
        button.clicked.connect (menu.toggle_from_icon);
        update_size ();
        settings.changed["icon-size"].connect (update_size);
        SizePolicy.get_default ().changed.connect (update_size);
    }

    public override void dispose () {
        if (menu != null) {
            menu.dispose ();
            menu = null;
        }
        base.dispose ();
    }

    private void update_size () {
        icon.pixel_size = ItemManager.get_icon_size () * 7 / 12;
    }
}
