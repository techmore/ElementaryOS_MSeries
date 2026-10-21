/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Scoped stylesheet for the Touch ID page. Every selector starts with .mst- so
 * nothing leaks into the host (Settings loads this inside its own process). */
namespace MSeriesTouchId {
    namespace Style {
        private const string CSS = """
            .mst-hero {
                border-radius: 20px;
                padding: 22px 24px 18px 24px;
                background-image: linear-gradient(160deg, alpha(@accent_color, 0.16), alpha(@accent_color, 0.03) 70%);
                box-shadow: inset 0 0 0 1px alpha(@accent_color, 0.18);
            }
            .mst-hero-title { font-weight: 800; font-size: 26px; }
            .mst-status { font-weight: 600; }
            .mst-card {
                border-radius: 16px;
                padding: 14px 12px 12px 12px;
            }
            .mst-card-name { font-weight: 700; }
            .mst-remove { opacity: 0.55; min-width: 28px; min-height: 28px; padding: 0; }
            .mst-card:hover .mst-remove, .mst-remove:focus-visible, .mst-remove:hover { opacity: 1; }
            .mst-add-tile {
                border-radius: 16px;
                border: 2px dashed alpha(currentColor, 0.24);
                background: transparent;
                box-shadow: none;
                min-height: 112px;
                padding: 12px;
            }
            .mst-add-tile:hover, .mst-add-tile:focus-visible {
                border-color: @accent_color;
                background: alpha(@accent_color, 0.07);
                color: @accent_color;
            }
            .mst-step {
                padding: 5px 14px;
                border-radius: 999px;
                background: alpha(currentColor, 0.07);
                color: alpha(currentColor, 0.62);
                font-weight: 600;
                transition: background 180ms ease, color 180ms ease;
            }
            .mst-step.mst-active {
                background: alpha(@accent_color, 0.20);
                color: @accent_color;
            }
            .mst-sheet-title { font-weight: 800; font-size: 20px; }
            .mst-mono { font-family: monospace; }
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
