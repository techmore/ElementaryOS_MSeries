/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Scoped stylesheet for the Dock & Taskbar page. Every selector starts with
 * .msd- so nothing leaks into the host (Settings loads this in its own process). */
namespace MSeriesDockSwitcher {
    namespace Stylesheet {
        private const string CSS = """
            .msd-card {
                border-radius: 18px;
                padding: 12px 12px 14px 12px;
                border: 2px solid alpha(currentColor, 0.12);
                background: alpha(currentColor, 0.03);
                transition: background 160ms ease, border-color 160ms ease;
            }
            .msd-card:hover { background: alpha(currentColor, 0.06); }
            .msd-card:checked {
                border-color: @accent_color;
                background: alpha(@accent_color, 0.09);
            }
            .msd-card:focus-visible { outline: 2px solid @accent_color; outline-offset: 2px; }
            .msd-card:disabled { opacity: 0.55; }
            .msd-card-title { font-weight: 700; }
            .msd-card-detail { opacity: 0.68; }
            .msd-badge {
                background: @accent_bg_color;
                color: @accent_fg_color;
                border-radius: 999px;
                padding: 3px;
                margin: 8px;
            }
            .msd-preview { border-radius: 12px; }
        """;

        private bool loaded = false;

        public void ensure () {
            if (loaded) {
                return;
            }
            var display = Gdk.Display.get_default ();
            if (display == null) {
                return;
            }
            var provider = new Gtk.CssProvider ();
            provider.load_from_string (CSS);
            Gtk.StyleContext.add_provider_for_display (display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
            loaded = true;
        }
    }
}
