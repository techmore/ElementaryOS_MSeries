/* Headless render probe: shows the real MainWindow / ConsentPrompt against a
 * canned service and saves PNGs. Run via probe/run-probe.sh (Xvfb). */
using MSeries.Remote;

class FixtureService : Service {
    public override void start () {
    }

    public void unavailable_now () {
        status = Status.unavailable ();
        settled = true;
        changed ();
    }

    public void show (string json) {
        status = Status.parse (json);
        settled = true;
        changed ();
    }

    public override async Invite? create_invite (bool allow_control) {
        var rows = new string[0];
        var n = 29;
        for (int y = 0; y < n; y++) {
            var sb = new StringBuilder ();
            for (int x = 0; x < n; x++) {
                bool finder = (x < 8 && y < 8) || (x >= n - 8 && y < 8) || (x < 8 && y >= n - 8);
                sb.append (finder ? ((x + y) % 2 == 0 ? "1" : "0") : (((x * 7 + y * 13) % 5 < 2) ? "1" : "0"));
            }
            rows += sb.str;
        }
        var i = new Invite () { qr = rows, expires_ms = get_real_time () / 1000 + 272000, control_offered = allow_control };
        i.links = { new Link () { label = "Tailnet", url = "http://100.64.0.9:8484/#i=Zk3aT9mPq1xL0vBn7cWd2A" },
                    new Link () { label = "Local network", url = "http://192.168.1.23:8484/#i=Zk3aT9mPq1xL0vBn7cWd2A" } };
        return i;
    }
}

const string S_OFF = """{"enabled":false,"listen":null,"backend":"mutter","phase":"idle","pending":null,"session":null,"grace_until_ms":null,"invites_pending":0}""";
const string S_IDLE = """{"enabled":true,"listen":"0.0.0.0:8484","backend":"mutter","phase":"idle","pending":null,"session":null,"grace_until_ms":null,"invites_pending":0}""";
const string S_PENDING = """{"enabled":true,"listen":"0.0.0.0:8484","backend":"mutter","phase":"pending","pending":{"id":"r1","device":"Pixel 8 (Chrome)","control_offered":true,"requested_ms":0,"expires_ms":0},"session":null,"grace_until_ms":null,"invites_pending":0}""";
const string S_VIEW = """{"enabled":true,"listen":"0.0.0.0:8484","backend":"mutter","phase":"active","pending":null,"session":{"id":"s1","device":"Pixel 8 (Chrome)","control":false,"control_permitted":true,"connected":true},"grace_until_ms":null,"invites_pending":0}""";
const string S_CTRL = """{"enabled":true,"listen":"0.0.0.0:8484","backend":"mutter","phase":"active","pending":null,"session":{"id":"s1","device":"Pixel 8 (Chrome)","control":true,"control_permitted":true,"connected":true},"grace_until_ms":null,"invites_pending":0}""";
const string S_GRACE = """{"enabled":true,"listen":null,"backend":"mutter","phase":"grace","pending":null,"session":{"id":"s1","device":"Pixel 8 (Chrome)","control":false,"control_permitted":true,"connected":false},"grace_until_ms":9,"invites_pending":0}""";

void save (Gtk.Window w, string path) {
    var paintable = new Gtk.WidgetPaintable (w);
    var snap = new Gtk.Snapshot ();
    paintable.snapshot (snap, paintable.get_intrinsic_width (), paintable.get_intrinsic_height ());
    var node = snap.to_node ();
    var renderer = w.get_native ().get_renderer ();
    var texture = renderer.render_texture (node, null);
    texture.save_to_png (path);
}

int main (string[] args) {
    // usage: render-probe OUT_DIR
    var out_dir = args.length > 1 ? args[1] : ".";
    var app = new Gtk.Application ("io.github.techmore.RemoteDesktopProbe", ApplicationFlags.NON_UNIQUE);
    app.startup.connect (() => { Granite.init (); });
    app.activate.connect (() => {
        var svc = new FixtureService ();
        var win = new MainWindow (app, svc);
        win.present ();
        string[,] scenes = { { "unavailable", "" }, { "off", S_OFF }, { "idle", S_IDLE }, { "invite", S_IDLE }, { "pending", S_PENDING },
                              { "viewing", S_VIEW }, { "controlling", S_CTRL }, { "grace", S_GRACE } };
        int i = 0;
        Timeout.add (500, () => {
            if (i >= 8) {
                var req = new PendingRequest () { id = "r1", device = "Pixel 8 (Chrome)", control_offered = true, expires_ms = get_real_time () / 1000 + 54000 };
                var p = new ConsentPrompt (req, null);
                p.present ();
                Timeout.add (700, () => {
                    save (p, Path.build_filename (out_dir, "consent.png"));
                    app.quit ();
                    return Source.REMOVE;
                });
                return Source.REMOVE;
            }
            string name = scenes[i, 0];
            if (name == "unavailable") {
                svc.unavailable_now ();
            } else {
                svc.show (scenes[i, 1]);
            }
            if (name == "invite") {
                win.create_invite.begin ();
            }
            Timeout.add (300, () => {
                save (win, Path.build_filename (out_dir, "%s.png".printf (name)));
                return Source.REMOVE;
            });
            i++;
            return Source.CONTINUE;
        });
    });
    return app.run ({ args[0] });
}
