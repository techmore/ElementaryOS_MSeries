public class ImagePullWindow : Gtk.Window {
    private IncusClient client;
    private Gtk.Entry server;
    private Gtk.Entry alias;
    private Gtk.CheckButton vm;
    private Gtk.Label status;
    private Gtk.Button pull;
    private Gtk.Button cancel;
    private string operation = "";
    private uint timer = 0;
    private bool polling = false;
    private bool closed = false;
    public signal void completed ();
    public ImagePullWindow (Gtk.Window parent, IncusClient api) {
        Object (transient_for: parent, title: "Download system image", default_width: 460);
        client = api;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
        server = new Gtk.Entry () { text = "https://images.linuxcontainers.org", placeholder_text = "Simplestreams image server" };
        alias = new Gtk.Entry () { text = "alpine/edge", placeholder_text = "System image alias" };
        vm = new Gtk.CheckButton.with_label ("Virtual-machine image");
        box.append (server); box.append (alias); box.append (vm);
        status = new Gtk.Label ("Downloads a native Incus system image. OCI registry images and Dockerfile builds are outside this app's Incus 6.0.5 target.") { wrap = true, xalign = 0 }; box.append (status);
        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        pull = new Gtk.Button.with_label ("Download"); pull.clicked.connect (() => begin_pull.begin ()); actions.append (pull);
        cancel = new Gtk.Button.with_label ("Cancel download") { sensitive = false }; cancel.clicked.connect (() => cancel_pull.begin ()); actions.append (cancel);
        box.append (actions); child = box;
        close_request.connect (() => { closed = true; if (timer != 0) { Source.remove (timer); timer = 0; } return false; });
    }
    private async void begin_pull () {
        pull.sensitive = false;
        try {
            var url = Uri.parse (server.text.strip (), UriFlags.NONE);
            if ((url.get_scheme () != "http" && url.get_scheme () != "https") || url.get_host () == null || url.get_userinfo () != null || alias.text.strip () == "") throw new IOError.INVALID_ARGUMENT ("Enter an HTTP(S) simplestreams server and a system-image alias.");
            var source = new Json.Object ();
            source.set_string_member ("type", "image"); source.set_string_member ("mode", "pull");
            source.set_string_member ("server", server.text.strip ()); source.set_string_member ("protocol", "simplestreams");
            source.set_string_member ("alias", alias.text.strip ()); source.set_string_member ("image_type", vm.active ? "virtual-machine" : "container");
            var body = new Json.Object (); body.set_object_member ("source", source); body.set_boolean_member ("public", false);
            var response = yield client.call ("POST", "/1.0/images", IncusClient.json_string (body));
            if (closed) return;
            if (response.get_string_member_with_default ("type", "") != "async") { status.label = "Image cached."; completed (); pull.sensitive = true; return; }
            operation = response.get_string_member ("operation");
            status.label = "Downloading… You may close this window; Incus keeps the operation running.";
            timer = Timeout.add_seconds (2, () => { poll.begin (); return Source.CONTINUE; });
            yield poll ();
        } catch (Error e) { status.label = e.message; pull.sensitive = true; }
    }
    private async void poll () {
        if (polling || operation == "") return;
        polling = true;
        try {
            var response = yield client.call ("GET", operation);
            var data = response.get_object_member ("metadata");
            int64 state = data.get_int_member ("status_code");
            cancel.sensitive = data.get_boolean_member_with_default ("may_cancel", false);
            if (state == 200 || state >= 400) {
                if (timer != 0) { Source.remove (timer); timer = 0; }
                status.label = state == 200 ? "Image cached successfully." : data.get_string_member_with_default ("err", "Image download failed.");
                operation = ""; pull.sensitive = true; cancel.sensitive = false;
                if (state == 200) completed ();
            } else {
                var metadata = data.get_member ("metadata");
                status.label = metadata != null && metadata.get_node_type () == Json.NodeType.OBJECT ? metadata.get_object ().get_string_member_with_default ("download_progress", data.get_string_member_with_default ("status", "Downloading…")) : data.get_string_member_with_default ("status", "Downloading…");
            }
        } catch (Error e) { status.label = e.message; }
        polling = false;
    }
    private async void cancel_pull () {
        try { yield client.call ("DELETE", operation); status.label = "Cancellation requested."; yield poll (); }
        catch (Error e) { status.label = e.message; }
    }
}
