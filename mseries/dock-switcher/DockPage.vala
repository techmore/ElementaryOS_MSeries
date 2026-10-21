/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Settings -> Personal -> Dock & Taskbar: choose between the Windows 11 taskbar
 * and the elementary dock. The dock reads the setting live, so a choice applies
 * at once; the page re-reads it afterwards before claiming success, offers Undo,
 * and follows changes made elsewhere (Work Mode, gsettings). */
namespace MSeriesDockSwitcher {
    public class StyleCard : Gtk.ToggleButton {
        public Style style { get; construct; }

        public StyleCard (Style style, string detail) {
            Object (style: style);
            add_css_class ("msd-card");

            var picture = new Illustration (style);
            var title = new Gtk.Label (style_name (style)) {
                halign = Gtk.Align.START,
                xalign = 0
            };
            title.add_css_class ("msd-card-title");
            var info = new Gtk.Label (detail) {
                halign = Gtk.Align.START,
                xalign = 0,
                wrap = true,
                max_width_chars = 30
            };
            info.add_css_class ("msd-card-detail");
            info.add_css_class ("caption");

            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
            box.append (picture);
            box.append (title);
            box.append (info);

            var badge = new Gtk.Image.from_icon_name ("object-select-symbolic") {
                halign = Gtk.Align.END,
                valign = Gtk.Align.START,
                visible = false
            };
            badge.add_css_class ("msd-badge");
            bind_property ("active", badge, "visible", GLib.BindingFlags.SYNC_CREATE);

            var overlay = new Gtk.Overlay ();
            overlay.child = box;
            overlay.add_overlay (badge);
            child = overlay;

            update_property (Gtk.AccessibleProperty.LABEL, style_name (style), -1);
            update_property (Gtk.AccessibleProperty.DESCRIPTION, detail, -1);
        }
    }

    public class DockPage : Gtk.Box {
        private DockModel model;
        private Adw.ToastOverlay overlay = new Adw.ToastOverlay ();
        private Adw.Banner banner = new Adw.Banner ("");
        private StyleCard taskbar_card;
        private StyleCard dock_card;
        private Adw.ComboRow autohide_row;
        private Adw.ActionRow running_row;
        private Adw.ActionRow build_row;
        private Adw.Toast? last_toast = null;
        private bool updating = false;
        private bool dock_running = false;
        private uint watch_id = 0;

        public DockPage (DockModel? injected = null) {
            Object (orientation: Gtk.Orientation.VERTICAL, spacing: 0);
            Stylesheet.ensure ();
            model = injected ?? new DockModel ();

            banner.button_label = null;
            append (banner);

            var page = new Adw.PreferencesPage ();
            overlay.child = page;
            overlay.vexpand = true;
            append (overlay);

            /* Style. */
            var style_group = new Adw.PreferencesGroup () {
                title = "Style",
                description = "How your apps, windows and status icons are shown along the bottom of the screen. Changes apply immediately."
            };
            taskbar_card = new StyleCard (Style.TASKBAR,
                "A full-width bar with a Start button, centred apps, status icons and a clock.");
            dock_card = new StyleCard (Style.DOCK,
                "A floating dock with your pinned apps. It can hide until you need it.");
            taskbar_card.set_group (dock_card);
            var cards = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 16) {
                homogeneous = true,
                margin_top = 6
            };
            cards.append (taskbar_card);
            cards.append (dock_card);
            style_group.add (cards);
            page.add (style_group);

            /* Options that only exist for one style. */
            var options = new Adw.PreferencesGroup () { title = "elementary dock" };
            var labels = new Gtk.StringList (null);
            foreach (var label in AUTOHIDE_LABELS) {
                labels.append (label);
            }
            autohide_row = new Adw.ComboRow () {
                title = "Hide automatically",
                model = labels
            };
            options.add (autohide_row);
            page.add (options);

            /* Honest status. */
            var status = new Adw.PreferencesGroup () { title = "Status" };
            running_row = new Adw.ActionRow () { title = "Dock", subtitle = "Checking…" };
            running_row.add_css_class ("property");
            build_row = new Adw.ActionRow () { title = "Build" };
            build_row.add_css_class ("property");
            status.add (running_row);
            status.add (build_row);
            page.add (status);

            taskbar_card.toggled.connect (() => on_card_toggled (taskbar_card));
            dock_card.toggled.connect (() => on_card_toggled (dock_card));
            autohide_row.notify["selected"].connect (on_autohide_selected);
            model.changed.connect (() => sync_ui ());

            sync_ui ();
        }

        /* Called when Settings shows the page: re-read what may have changed
         * while it was hidden and start watching the dock process. */
        public void refresh () {
            model.refresh_marker ();
            sync_ui ();
            if (watch_id == 0) {
                watch_id = GLib.Bus.watch_name (GLib.BusType.SESSION, "io.elementary.dock",
                    GLib.BusNameWatcherFlags.NONE,
                    () => { dock_running = true; sync_ui (); },
                    () => { dock_running = false; sync_ui (); });
            }
        }

        /* Select a style as if its card had been clicked (used by the preview host). */
        public void choose (Style style) {
            (style == Style.TASKBAR ? taskbar_card : dock_card).active = true;
        }

        public void pause () {
            if (watch_id != 0) {
                GLib.Bus.unwatch_name (watch_id);
                watch_id = 0;
            }
        }

        private void sync_ui () {
            var available = model.availability ();
            var choosable = can_choose (available);
            var current = model.style;

            updating = true;
            taskbar_card.active = current == Style.TASKBAR;
            dock_card.active = current == Style.DOCK;
            updating = false;

            taskbar_card.sensitive = choosable;
            dock_card.sensitive = choosable;

            var message = banner_for (available);
            banner.title = message;
            banner.revealed = message != "";

            var dock_options = choosable && current == Style.DOCK;
            autohide_row.sensitive = dock_options;
            autohide_row.subtitle = current == Style.TASKBAR
                ? "The taskbar is always visible."
                : "Slide the dock out of the way until you point at the screen edge.";
            var index = autohide_index (model.autohide);
            updating = true;
            if (index >= 0) {
                autohide_row.selected = index;
            }
            updating = false;

            if (available == Availability.DOCK_OFF) {
                running_row.subtitle = "Turned off for this account";
            } else if (available == Availability.NO_DOCK) {
                running_row.subtitle = "Not installed";
            } else {
                running_row.subtitle = dock_running ? "Running" : "Not running";
            }
            build_row.subtitle = model.has_taskbar_key
                ? "M-Series dock (Windows 11 taskbar available)"
                : "Stock elementary dock";
        }

        private void on_card_toggled (StyleCard card) {
            if (updating || !card.active) {
                return;
            }
            var previous = model.style;
            if (card.style == previous) {
                return;
            }
            if (!model.set_style (card.style)) {
                sync_ui ();
                toast ("Couldn't change the dock style", null, null);
                return;
            }
            sync_ui ();
            toast (switched_message (card.style), "Undo", () => {
                if (model.set_style (previous)) {
                    sync_ui ();
                }
            });
        }

        private void on_autohide_selected () {
            if (updating) {
                return;
            }
            var nick = autohide_nick_at ((int) autohide_row.selected);
            if (nick == null || nick == model.autohide) {
                return;
            }
            if (!model.set_autohide (nick)) {
                sync_ui ();
                toast ("Couldn't change when the dock hides", null, null);
            }
        }

        private delegate void UndoFunc ();

        private void toast (string message, string? undo_label, owned UndoFunc? undo) {
            if (last_toast != null) {
                last_toast.dismiss ();
            }
            var t = new Adw.Toast (message) { timeout = 6 };
            if (undo_label != null && undo != null) {
                t.button_label = undo_label;
                t.button_clicked.connect (() => undo ());
            }
            last_toast = t;
            overlay.add_toast (t);
        }
    }
}
