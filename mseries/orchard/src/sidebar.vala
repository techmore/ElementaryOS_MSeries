/* Sidebar rows shared by the three sections: Machines (QEMU/KVM), Incus and Podman.
 * Every row knows its group, sort key, section header and the content page it opens. */
using Gtk;

public class SidebarRow : Gtk.ListBoxRow {
    public virtual int group { get { return 0; } }
    public virtual string sort_key { owned get { return ""; } }
    public virtual string header_title { owned get { return ""; } }
    public virtual string page_name { owned get { return ""; } }

    /* The icon-with-status-dot and two-line text every row uses. */
    protected Gtk.Label name_label;
    protected Gtk.Label sub_label;
    protected Gtk.Box dot;
    protected Gtk.Image icon;

    protected void build_row (string icon_name, int color) {
        var box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10);
        box.margin_top = 4;
        box.margin_bottom = 4;
        box.margin_start = 6;
        box.margin_end = 6;

        var overlay = new Gtk.Overlay ();
        icon = new Gtk.Image.from_icon_name (icon_name);
        icon.pixel_size = 32;
        icon.add_css_class ("ml-row-icon");
        icon.add_css_class ("ml-c-%d".printf (color));
        overlay.child = icon;
        dot = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        dot.add_css_class ("ml-dot");
        dot.halign = Gtk.Align.END;
        dot.valign = Gtk.Align.END;
        dot.width_request = 10;
        dot.height_request = 10;
        overlay.add_overlay (dot);
        box.append (overlay);

        var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        text.valign = Gtk.Align.CENTER;
        name_label = new Gtk.Label ("");
        name_label.xalign = 0;
        name_label.ellipsize = Pango.EllipsizeMode.END;
        name_label.add_css_class ("ml-machine-name");
        sub_label = new Gtk.Label ("");
        sub_label.xalign = 0;
        sub_label.ellipsize = Pango.EllipsizeMode.END;
        sub_label.add_css_class ("ml-machine-sub");
        text.append (name_label);
        text.append (sub_label);
        box.append (text);
        child = box;
    }

    protected void set_running (bool running) {
        if (running) {
            dot.add_css_class ("running");
        } else {
            dot.remove_css_class ("running");
        }
    }

    protected void set_color (int color) {
        for (int i = 0; i < 8; i++) {
            icon.remove_css_class ("ml-c-%d".printf (i));
        }
        icon.add_css_class ("ml-c-%d".printf (color));
    }
}

/* One Incus container or virtual machine. */
public class IncusRow : SidebarRow {
    public Instance instance { get; private set; }

    public override int group { get { return 2; } }
    public override string sort_key { owned get { return instance.name.down (); } }
    public override string header_title { owned get { return "INCUS"; } }
    public override string page_name { owned get { return "incus:" + instance.name; } }

    public IncusRow (Instance instance) {
        this.instance = instance;
        build_row (instance.is_vm ? "computer" : "package-x-generic", instance.is_vm ? 7 : 1);
        update (instance);
    }

    public void update (Instance inst) {
        instance = inst;
        // No live memory figure here: a label that changes every poll repaints the sidebar every poll.
        string where = inst.ipv4 != "" ? " · " + inst.ipv4 : "";
        string text = "%s · %s%s".printf (inst.kind_label, inst.status, where);
        if (sub_label.label != text) sub_label.label = text;
        if (name_label.label != inst.name) name_label.label = inst.name;
        set_running (inst.running);
    }
}

/* The Incus section's own row: dashboard, resources and tools. Always first in its section. */
public class IncusHomeRow : SidebarRow {
    public override int group { get { return 2; } }
    public override string sort_key { owned get { return ""; } }
    public override string header_title { owned get { return "INCUS"; } }
    public override string page_name { owned get { return "incus-home"; } }

    public IncusHomeRow () {
        build_row ("orchard-incus-symbolic", 2);
        name_label.label = "Incus";
        sub_label.label = "Containers and virtual machines";
    }

    public void update (int total, int running, string? error) {
        if (error != null) {
            sub_label.label = "Not reachable";
            set_running (false);
            return;
        }
        var text = total == 0 ? "No instances yet" : "%d of %d running".printf (running, total);
        if (sub_label.label != text) sub_label.label = text;
        set_running (running > 0);
    }
}

/* The Podman section's row: the user's rootless containers, images and volumes. */
public class PodmanRow : SidebarRow {
    public override int group { get { return 3; } }
    public override string sort_key { owned get { return ""; } }
    public override string header_title { owned get { return "PODMAN"; } }
    public override string page_name { owned get { return "podman"; } }

    public PodmanRow () {
        build_row ("package-x-generic", 4);
        name_label.label = "Podman";
        sub_label.label = "Containers, images and volumes";
    }

    public void update (int containers, int running, bool installed) {
        if (!installed) {
            sub_label.label = "Not installed";
            set_running (false);
            return;
        }
        sub_label.label = containers == 0 ? "No containers yet" : "%d of %d containers running".printf (running, containers);
        set_running (running > 0);
    }
}
