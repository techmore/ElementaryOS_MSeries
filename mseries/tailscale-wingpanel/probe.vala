/* Shows the Tailscale menu inside a real popover, outside Wingpanel. */
int main (string[] args) {
    var app = new Gtk.Application ("io.github.techmore.TailscalePanelProbe", ApplicationFlags.NON_UNIQUE);
    app.activate.connect (() => {
        var window = new Gtk.ApplicationWindow (app) { title = "Tailscale probe", default_width = 380, default_height = 640 };
        var anchor = new Gtk.MenuButton () { label = "Tailscale", halign = Gtk.Align.CENTER, valign = Gtk.Align.START };
        var popover = new Gtk.Popover () { child = new MSeries.Tailscale.Panel (), autohide = false };
        anchor.popover = popover;
        window.child = anchor;
        window.present ();
        anchor.active = true;
    });
    return app.run (args);
}
