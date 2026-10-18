/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Gala "hotkey drawers" plugin for Pantheon (elementary OS / M-series).
 *
 * A drawer is one global hotkey that pops a set of apps up or down and snaps
 * them into a fixed zone of a monitor. Think a Quake-style drop-down terminal,
 * but generic and plural: a terminal in the top 40% of the built-in panel, notes
 * on the right third of an external display, or a "series" of apps that come in
 * together and leave together.
 *
 * Why a Gala plugin and not a script:
 *   Gala is a Wayland compositor. It exposes no D-Bus method to move or resize a
 *   window (only GrabAccelerator/UngrabAccelerator/ShowOSD at /org/gnome/Shell),
 *   and it does not implement wlr-layer-shell. The only place that can both grab a
 *   global hotkey *and* place an arbitrary window is inside the compositor.
 *
 * Hotkeys live in the gsettings schema org.pantheon.gala.plugins.drawers:
 *   drawer-1 .. drawer-9  toggle a drawer (bound only for configured drawers)
 *   assign-1 .. assign-9  capture the focused window into that drawer
 * The apps, matches and zones live in ~/.config/mseries/gala-drawers.ini, which
 * this plugin watches so edits (from the settings app or by hand) apply live.
 */

namespace Gala.Plugins.Drawers {

    private const int MAX_DRAWERS = 9;

    /*
     * One app inside a drawer: what to launch if it is not open, and what to match
     * a window against (GTK application id or WM class, case-insensitive).
     */
    internal class AppEntry : Object {
        public string command;
        public string match;
        public bool has_zone = false;   // per-app zone override (a "series")
        public double x = 0.0;
        public double y = 0.0;
        public double w = 1.0;
        public double h = 1.0;
    }

    /* A drawer app that currently has a window on screen. */
    internal class Hit : Object {
        public AppEntry entry;
        public Meta.Window window;
    }

    /*
     * One drawer's content: a list of apps (a "series"), plus where to put them.
     * zone x/y/w/h are fractions (0..1) of the target monitor's geometry.
     */
    internal class DrawerConfig : Object {
        public Gee.ArrayList<AppEntry> apps;
        public int monitor = -1;   // -1 == primary monitor
        public double x = 0.0;
        public double y = 0.0;
        public double w = 1.0;
        public double h = 1.0;
    }

    /*
     * A bound drawer. Held by the plugin for its lifetime so the keybinding
     * delegates keep a live target (and so each index gets its own handler,
     * avoiding the classic loop-variable capture bug).
     */
    internal class Drawer : Object {
        public int index { get; construct; }

        private unowned Main plugin;

        public Drawer (Main plugin, int index) {
            Object (index: index);
            this.plugin = plugin;
        }

        public void handle (Meta.Display display, Meta.Window? window, Clutter.KeyEvent? event, Meta.KeyBinding binding) {
            plugin.toggle (index, display);
        }

        public void assign (Meta.Display display, Meta.Window? window, Clutter.KeyEvent? event, Meta.KeyBinding binding) {
            plugin.assign (index, display);
        }
    }

    public class Main : Gala.Plugin {
        private Gala.WindowManager? wm = null;
        private GLib.Settings settings;
        private HashTable<int, DrawerConfig> configs;
        private Gee.ArrayList<Drawer> drawers;
        private GLib.FileMonitor? monitor = null;
        private uint reload_source = 0;
        private string config_path;
        private string config_dir;

        construct {
            configs = new HashTable<int, DrawerConfig> (direct_hash, direct_equal);
            drawers = new Gee.ArrayList<Drawer> ();
        }

        public override void initialize (Gala.WindowManager wm) {
            this.wm = wm;

            settings = new GLib.Settings ("org.pantheon.gala.plugins.drawers");
            config_dir = Path.build_filename (Environment.get_user_config_dir (), "mseries");
            config_path = Path.build_filename (config_dir, "gala-drawers.ini");

            load_config ();
            bind_all ();
            watch_config ();

            message ("drawers: %d drawer(s) bound", drawers.size);
        }

        public override void destroy () {
            if (wm == null) {
                return;
            }

            unbind_all ();

            if (monitor != null) {
                monitor.cancel ();
                monitor = null;
            }
            if (reload_source != 0) {
                GLib.Source.remove (reload_source);
                reload_source = 0;
            }

            drawers.clear ();
        }

        // ----- binding -------------------------------------------------------

        private void bind_all () {
            var display = wm.get_display ();
            unbind_all ();

            for (int i = 1; i <= MAX_DRAWERS; i++) {
                if (!configs.contains (i)) {
                    continue;
                }

                var drawer = new Drawer (this, i);
                drawers.add (drawer);
                display.add_keybinding (
                    @"drawer-$i",
                    settings,
                    Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
                    drawer.handle
                );
                display.add_keybinding (
                    @"assign-$i",
                    settings,
                    Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
                    drawer.assign
                );
            }
        }

        private void unbind_all () {
            var display = wm.get_display ();
            for (int i = 1; i <= MAX_DRAWERS; i++) {
                display.remove_keybinding (@"drawer-$i");
                display.remove_keybinding (@"assign-$i");
            }
            drawers.clear ();
        }

        private void watch_config () {
            // Watch the directory, not the file: editors and the settings app often
            // replace the file atomically (write temp + rename), which a file watch
            // on the old inode would miss.
            try {
                var dir = GLib.File.new_for_path (config_dir);
                monitor = dir.monitor_directory (GLib.FileMonitorFlags.WATCH_MOVES, null);
                monitor.changed.connect (on_config_changed);
            } catch (Error e) {
                warning ("drawers: cannot watch %s: %s", config_dir, e.message);
            }
        }

        private void on_config_changed (GLib.File file, GLib.File? other, GLib.FileMonitorEvent event) {
            var name = file.get_basename ();
            if (name != "gala-drawers.ini") {
                return;
            }

            // Debounce: a single save can emit several events.
            if (reload_source != 0) {
                GLib.Source.remove (reload_source);
            }
            reload_source = GLib.Timeout.add (250, () => {
                reload_source = 0;
                load_config ();
                bind_all ();
                message ("drawers: reloaded config, %d drawer(s) bound", drawers.size);
                return false;
            });
        }

        // ----- actions -------------------------------------------------------

        /*
         * The whole feature: up if it's down, down if it's up, and into its zone.
         */
        internal void toggle (int index, Meta.Display display) {
            if (!configs.contains (index)) {
                return;
            }

            var config = configs.get (index);
            var hits = new Gee.ArrayList<Hit> ();
            var missing = new Gee.ArrayList<AppEntry> ();

            foreach (var entry in config.apps) {
                var win = find_window (display, entry.match);
                if (win != null) {
                    var hit = new Hit ();
                    hit.entry = entry;
                    hit.window = win;
                    hits.add (hit);
                } else {
                    missing.add (entry);
                }
            }

            var focused = display.get_focus_window ();
            bool focused_here = false;
            bool any_up = false;
            foreach (var hit in hits) {
                if (hit.window == focused && !hit.window.minimized) {
                    focused_here = true;
                }
                if (!hit.window.minimized) {
                    any_up = true;
                }
            }

            // Focused and up -> put the whole series away. Otherwise bring it in.
            if (focused_here && any_up) {
                foreach (var hit in hits) {
                    hit.window.minimize ();
                }
                return;
            }

            foreach (var hit in hits) {
                place (display, hit.window, config, hit.entry);
            }
            foreach (var entry in missing) {
                launch (entry.command);
            }
        }

        /*
         * Capture the focused window into a drawer: write it to the INI, reload,
         * and confirm on screen. This is the "open the app, then assign it" flow.
         */
        internal void assign (int index, Meta.Display display) {
            var win = display.get_focus_window ();
            if (win == null) {
                osd ("No focused window", "dialog-warning-symbolic");
                return;
            }

            var match = derive_match (win);
            if (match == "") {
                osd ("Can't identify this window", "dialog-warning-symbolic");
                return;
            }

            var command = derive_command (match);
            upsert (index, command, match);
            load_config ();
            bind_all ();
            osd (@"Drawer %d ← %s".printf (index, friendly_name (match)), "input-dialpad-symbolic");
        }

        // ----- window helpers ------------------------------------------------

        private Meta.Window? find_window (Meta.Display display, string match) {
            var needle = match.down ();

            foreach (var win in display.list_all_windows ()) {
                if (win.get_window_type () != Meta.WindowType.NORMAL) {
                    continue;
                }

                var gtk_id = win.get_gtk_application_id ();
                if (gtk_id != null && gtk_id.down () == needle) {
                    return win;
                }

                var wm_class = win.get_wm_class ();
                if (wm_class != null && wm_class.down () == needle) {
                    return win;
                }
            }

            return null;
        }

        private void place (Meta.Display display, Meta.Window win, DrawerConfig config, AppEntry entry) {
            int monitor = config.monitor;
            if (monitor < 0 || monitor >= display.get_n_monitors ()) {
                monitor = display.get_primary_monitor ();
            }

            var geo = display.get_monitor_geometry (monitor);
            double fx = entry.has_zone ? entry.x : config.x;
            double fy = entry.has_zone ? entry.y : config.y;
            double fw = entry.has_zone ? entry.w : config.w;
            double fh = entry.has_zone ? entry.h : config.h;

            int x = geo.x + (int) Math.round (geo.width * fx);
            int y = geo.y + (int) Math.round (geo.height * fy);
            int w = (int) Math.round (geo.width * fw);
            int h = (int) Math.round (geo.height * fh);

            win.unminimize ();
            win.move_resize_frame (false, x, y, w, h);
            win.activate (display.get_current_time ());
            win.raise ();
        }

        private void launch (string command) {
            try {
                resolve (command).launch (null, null);
            } catch (Error e) {
                warning ("drawers: failed to launch '%s': %s", command, e.message);
            }
        }

        /*
         * Prefer a desktop entry (the stable id the assign flow stores), then fall
         * back to treating the string as an ordinary command line.
         */
        private GLib.AppInfo resolve (string command) throws Error {
            foreach (var app in GLib.AppInfo.get_all ()) {
                var id = app.get_id ();
                if (id != null && id == command) {
                    return app;
                }
            }
            return GLib.AppInfo.create_from_commandline (command, null, GLib.AppInfoCreateFlags.NONE);
        }

        private string derive_match (Meta.Window win) {
            var id = win.get_gtk_application_id ();
            if (id != null && id != "") {
                return id.down ();
            }

            var wm_class = win.get_wm_class ();
            if (wm_class != null && wm_class != "") {
                return wm_class.down ();
            }

            return "";
        }

        /*
         * Find the desktop entry for a match and return its id (a stable launch
         * handle). Falls back to the match string itself.
         */
        private string derive_command (string match) {
            foreach (var app in GLib.AppInfo.get_all ()) {
                var id = app.get_id ();
                if (id != null && strip_desktop (id).down () == match) {
                    return id;
                }
            }

            foreach (var app in GLib.AppInfo.get_all ()) {
                var exe = app.get_executable ();
                if (exe != null && Path.get_basename (exe).down () == match) {
                    var id = app.get_id ();
                    return id ?? match;
                }
            }

            return match;
        }

        private string friendly_name (string match) {
            foreach (var app in GLib.AppInfo.get_all ()) {
                var id = app.get_id ();
                if (id != null && strip_desktop (id).down () == match) {
                    return app.get_name ();
                }
            }
            return match;
        }

        private static string strip_desktop (string id) {
            return id.has_suffix (".desktop") ? id.substring (0, id.length - ".desktop".length) : id;
        }

        // ----- config --------------------------------------------------------

        private void load_config () {
            configs.remove_all ();

            var file = new GLib.KeyFile ();
            try {
                file.load_from_file (config_path, GLib.KeyFileFlags.NONE);
            } catch (Error e) {
                message ("drawers: no config at %s (%s)", config_path, e.message);
                return;
            }

            for (int i = 1; i <= MAX_DRAWERS; i++) {
                var group = @"drawer-$i";
                if (!file.has_group (group)) {
                    continue;
                }

                try {
                    var config = parse_drawer (file, group);
                    if (config.apps.size > 0) {
                        configs.set (i, config);
                    }
                } catch (Error e) {
                    warning ("drawers: bad config for %s: %s", group, e.message);
                }
            }
        }

        /*
         * Zone numbers are written space-separated (e.g. "0.0 0.0 1.0 0.4"),
         * which GLib's list helpers cannot read (they split on ';' only), so
         * split on any of space, comma or semicolon here.
         */
        private static double[] parse_numbers (string raw) {
            double[] numbers = {};
            foreach (var token in raw.split_set (" \t,;")) {
                if (token == "") {
                    continue;
                }
                double value;
                if (double.try_parse (token, out value)) {
                    numbers += value;
                }
            }
            return numbers;
        }

        private DrawerConfig parse_drawer (GLib.KeyFile file, string group) throws GLib.Error {
            var config = new DrawerConfig ();
            config.apps = new Gee.ArrayList<AppEntry> ();

            var commands = file.get_string_list (group, "command");
            string[] matches = file.has_key (group, "match")
                ? file.get_string_list (group, "match")
                : commands;

            for (int k = 0; k < commands.length; k++) {
                var entry = new AppEntry ();
                entry.command = commands[k].strip ();
                entry.match = (k < matches.length ? matches[k].strip () : entry.command);
                if (entry.match == "") {
                    entry.match = entry.command;
                }
                if (entry.command != "") {
                    config.apps.add (entry);
                }
            }

            if (file.has_key (group, "monitor")) {
                config.monitor = int.parse (file.get_string (group, "monitor"));
            }

            double[] zone = {};
            if (file.has_key (group, "zone")) {
                zone = parse_numbers (file.get_string (group, "zone"));
            }
            if (zone.length == 4) {
                // One zone for the whole drawer.
                config.x = zone[0];
                config.y = zone[1];
                config.w = zone[2];
                config.h = zone[3];
            } else if (config.apps.size > 0 && zone.length == 4 * config.apps.size) {
                // A zone per app, in the same order as `command` — lets a series
                // sit side by side instead of stacking.
                for (int k = 0; k < config.apps.size; k++) {
                    var entry = config.apps[k];
                    entry.has_zone = true;
                    entry.x = zone[k * 4];
                    entry.y = zone[k * 4 + 1];
                    entry.w = zone[k * 4 + 2];
                    entry.h = zone[k * 4 + 3];
                }
            }

            return config;
        }

        private void upsert (int index, string command, string match) {
            var file = new GLib.KeyFile ();
            try {
                file.load_from_file (config_path, GLib.KeyFileFlags.NONE);
            } catch (Error e) {
                // No file yet: start a fresh one.
            }

            var group = @"drawer-$index";
            bool have_zone = false;
            try {
                have_zone = file.has_key (group, "zone");
            } catch (Error e) {
                have_zone = false;
            }
            file.set_string (group, "command", command);
            file.set_string (group, "match", match);
            if (!have_zone) {
                file.set_string (group, "zone", "0.0 0.0 1.0 0.5");
            }

            try {
                DirUtils.create_with_parents (config_dir, 0755);
                size_t length;
                var data = file.to_data (out length);
                FileUtils.set_contents (config_path, data, (ssize_t) length);
            } catch (Error e) {
                warning ("drawers: failed to write %s: %s", config_path, e.message);
            }
        }

        // ----- feedback ------------------------------------------------------

        /*
         * A transient on-screen confirmation through Gala's built-in OSD (the same
         * one volume/brightness use). It appears and disappears on its own.
         */
        private void osd (string label, string icon) {
            try {
                var connection = GLib.Bus.get_sync (GLib.BusType.SESSION, null);
                var builder = new GLib.VariantBuilder (new GLib.VariantType ("a{sv}"));
                builder.add ("{sv}", "icon", new GLib.Variant ("s", icon));
                builder.add ("{sv}", "label", new GLib.Variant ("s", label));
                // ShowOSD takes a single a{sv}, so the parameters must be a
                // (a{sv}) TUPLE. Building that from a format string while the
                // child variant is already built makes GVariant abort, which takes
                // the whole compositor down - Variant.tuple() is the correct way.
                var params = new GLib.Variant.tuple ({ builder.end () });
                connection.call_sync (
                    "org.gnome.Shell",
                    "/org/gnome/Shell",
                    "org.gnome.Shell",
                    "ShowOSD",
                    params,
                    null,
                    GLib.DBusCallFlags.NONE,
                    1000,
                    null
                );
            } catch (Error e) {
                warning ("drawers: OSD failed: %s", e.message);
            }
        }
    }
}

public Gala.PluginInfo register_plugin () {
    return {
        "drawers",
        "M-series / elementary-mseries",
        typeof (Gala.Plugins.Drawers.Main),
        Gala.PluginFunction.ADDITION,
        Gala.LoadPriority.IMMEDIATE
    };
}
