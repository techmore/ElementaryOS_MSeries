/* SPDX-License-Identifier: GPL-3.0
 * Work Mode hides Wingpanel, so the taskbar clock hosts the same datetime indicator
 * (month grid, Events, Tasks, GitHub, Bible) in a popover above the clock. The
 * indicator library is the one Wingpanel loads; nothing is copied or forked. */
public delegate Wingpanel.Indicator? DockDatetimeIndicatorFactory (Module module, Wingpanel.ServerType server_type);

public class Dock.TaskbarCalendar : Object {
    private const string[] INDICATOR_DIRS = {
        "/usr/lib/aarch64-linux-gnu/wingpanel-9",
        "/usr/lib/x86_64-linux-gnu/wingpanel-9",
        "/usr/lib64/wingpanel-9",
        "/usr/lib/wingpanel-9"
    };

    // One indicator per process: the module stays resident once loaded.
    private static Module? module = null;
    private static Wingpanel.Indicator? indicator = null;
    private static bool load_failed = false;

    public unowned Gtk.Widget anchor { get; construct; }
    private Gtk.Popover? popover = null;

    public TaskbarCalendar (Gtk.Widget anchor) {
        Object (anchor: anchor);
    }

    public bool is_open {
        get { return popover != null && popover.visible; }
    }

    /* Opens or closes the calendar. Returns false when the indicator is unavailable,
     * so the caller can fall back to the Calendar app. */
    public bool toggle () {
        if (is_open) {
            popover.popdown ();
            return true;
        }
        var widget = load_widget ();
        if (widget == null) {
            return false;
        }
        if (popover == null) {
            popover = new Gtk.Popover () {
                child = widget,
                position = Gtk.PositionType.TOP,
                autohide = true
            };
            popover.add_css_class ("mseries-taskbar-calendar");
            popover.set_parent (anchor);
            popover.closed.connect (() => indicator.closed ());
            indicator.close.connect (() => {
                if (popover != null) {
                    popover.popdown ();
                }
            });
            anchor.destroy.connect (() => {
                if (popover != null) {
                    popover.unparent ();
                    popover = null;
                }
            });
        }
        indicator.opened ();
        popover.popup ();
        return true;
    }

    private static string? library_path () {
        var override_path = Environment.get_variable ("MSERIES_DATETIME_INDICATOR");
        if (override_path != null && override_path != "") {
            return override_path;
        }
        foreach (unowned var dir in INDICATOR_DIRS) {
            var path = Path.build_filename (dir, "libdatetime.so");
            if (FileUtils.test (path, FileTest.EXISTS)) {
                return path;
            }
        }
        return null;
    }

    private static Gtk.Widget? load_widget () {
        if (indicator != null) {
            return indicator.get_widget ();
        }
        if (load_failed) {
            return null;
        }
        load_failed = true;
        var path = library_path ();
        if (path == null) {
            warning ("Work Mode calendar: datetime indicator not installed");
            return null;
        }
        var opened = Module.open (path, ModuleFlags.LAZY | ModuleFlags.LOCAL);
        if (opened == null) {
            warning ("Work Mode calendar: %s", Module.error ());
            return null;
        }
        void* symbol;
        if (!opened.symbol ("get_indicator", out symbol) || symbol == null) {
            warning ("Work Mode calendar: %s has no get_indicator", path);
            return null;
        }
        var created = ((DockDatetimeIndicatorFactory) symbol) (opened, Wingpanel.ServerType.SESSION);
        if (created == null) {
            return null;
        }
        var widget = created.get_widget ();
        if (widget == null) {
            return null;
        }
        opened.make_resident ();
        module = (owned) opened;
        indicator = created;
        load_failed = false;
        return widget;
    }
}
