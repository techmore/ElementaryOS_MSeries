// Minimal Incus REST client over the local unix socket.
// Socket: $INCUS_SOCKET, else /var/lib/incus/unix.socket.
public class IncusClient : Object {
    private Soup.Session session;
    private string socket_path;

    public IncusClient (uint timeout_seconds = 15) {
        var path = Environment.get_variable ("INCUS_SOCKET") ?? new Preferences ().read ("socket", "/var/lib/incus/unix.socket");
        socket_path = path;
        session = (Soup.Session) Object.new (typeof (Soup.Session),
            "remote-connectable", new UnixSocketAddress (path),
            "timeout", timeout_seconds);
    }

    public async Json.Object call (string method, string path, string? body = null, string? etag = null, uint timeout_override = 0) throws Error {
        var msg = new Soup.Message (method, "http://incus" + path);
        if (body != null) {
            msg.set_request_body_from_bytes ("application/json", new Bytes (body.data));
        }
        if (etag != null) msg.request_headers.replace ("If-Match", etag);
        var transport = timeout_override == 0 ? session : (Soup.Session) Object.new (typeof (Soup.Session), "remote-connectable", new UnixSocketAddress (socket_path), "timeout", timeout_override);
        var bytes = yield transport.send_and_read_async (msg, Priority.DEFAULT, null);
        var parser = new Json.Parser ();
        parser.load_from_data ((string) bytes.get_data (), (ssize_t) bytes.get_size ());
        if (parser.get_root ().get_node_type () != Json.NodeType.OBJECT) {
            throw new IOError.INVALID_DATA ("Incus returned an invalid response.");
        }
        var root = parser.get_root ().get_object ();
        if (msg.status_code >= 400) {
            throw new IOError.FAILED (root.get_string_member_with_default ("error", msg.reason_phrase ?? "Incus request failed"));
        }
        var response_etag = msg.response_headers.get_one ("ETag");
        if (response_etag != null) root.set_string_member ("_orchard_etag", response_etag);
        if (root.get_string_member_with_default ("type", "") == "error") {
            throw new IOError.FAILED (root.get_string_member_with_default ("error", "Incus error"));
        }
        return root;
    }

    public async Instance[] list_instances () throws Error {
        var root = yield call ("GET", "/1.0/instances?recursion=2");
        var out = new Instance[0];
        foreach (var n in root.get_array_member ("metadata").get_elements ()) {
            out += Instance.from_json (n.get_object ());
        }
        return out;
    }

    // action: start | stop | restart | freeze | unfreeze
    public async void change_state (string name, string action, bool force = false) throws Error {
        var body = """{"action":"%s","timeout":30,"force":%s}""".printf (action, force ? "true" : "false");
        var res = yield call ("PUT", "/1.0/instances/%s/state".printf (Uri.escape_string (name)), body);
        yield wait_operation (res);
    }

    public async void delete_instance (string name) throws Error {
        var res = yield call ("DELETE", "/1.0/instances/%s".printf (Uri.escape_string (name)));
        yield wait_operation (res);
    }

    public async void create_snapshot (string name, string snap) throws Error {
        var payload = new Json.Object ();
        payload.set_string_member ("name", snap);
        payload.set_boolean_member ("stateful", false);
        var body = json_string (payload);
        var res = yield call ("POST", "/1.0/instances/%s/snapshots".printf (Uri.escape_string (name)), body);
        yield wait_operation (res);
    }

    public async void create_instance (string name, string alias, bool vm, Json.Object? config = null, bool ephemeral = false, Json.Object? devices = null, bool without_profiles = false) throws Error {
        var b = new Json.Builder ();
        b.begin_object ();
        b.set_member_name ("name").add_string_value (name);
        b.set_member_name ("type").add_string_value (vm ? "virtual-machine" : "container");
        b.set_member_name ("start").add_boolean_value (true);
        b.set_member_name ("ephemeral").add_boolean_value (ephemeral);
        if (config != null) {
            var config_node = new Json.Node (Json.NodeType.OBJECT);
            config_node.set_object (config);
            b.set_member_name ("config").add_value (config_node);
        }
        if (devices != null) {
            var devices_node = new Json.Node (Json.NodeType.OBJECT); devices_node.set_object (devices);
            b.set_member_name ("devices").add_value (devices_node);
        }
        if (without_profiles) b.set_member_name ("profiles").begin_array ().end_array ();
        b.set_member_name ("source").begin_object ();
        b.set_member_name ("type").add_string_value ("image");
        if (alias.has_prefix ("local:")) {
            b.set_member_name ("fingerprint").add_string_value (alias.substring (6));
        } else {
            b.set_member_name ("mode").add_string_value ("pull");
            b.set_member_name ("protocol").add_string_value ("simplestreams");
            b.set_member_name ("server").add_string_value ("https://images.linuxcontainers.org");
            b.set_member_name ("alias").add_string_value (alias);
        }
        b.end_object ();
        b.end_object ();
        var gen = new Json.Generator ();
        gen.root = b.get_root ();
        var res = yield call ("POST", "/1.0/instances", gen.to_data (null));
        yield wait_operation (res, 600);
    }

    public async string[] list_snapshots (string name) throws Error {
        var root = yield call ("GET", "/1.0/instances/%s/snapshots?recursion=1".printf (Uri.escape_string (name)));
        var names = new string[0];
        foreach (var n in root.get_array_member ("metadata").get_elements ()) {
            // Snapshot names come back as "<instance>/<snapshot>"; keep the short part.
            var full = n.get_object ().get_string_member ("name");
            var slash = full.last_index_of_char ('/');
            names += slash >= 0 ? full.substring (slash + 1) : full;
        }
        return names;
    }

    public async void restore_snapshot (string name, string snap) throws Error {
        var payload = new Json.Object ();
        payload.set_string_member ("restore", snap);
        var body = json_string (payload);
        var res = yield call ("PUT", "/1.0/instances/%s".printf (Uri.escape_string (name)), body);
        yield wait_operation (res);
    }

    public async void delete_snapshot (string name, string snap) throws Error {
        var res = yield call ("DELETE", "/1.0/instances/%s/snapshots/%s".printf (Uri.escape_string (name), Uri.escape_string (snap)));
        yield wait_operation (res);
    }

    public async void wait_operation (Json.Object res, int timeout = 60) throws Error {
        if (res.get_string_member_with_default ("type", "") != "async") return;
        var op = res.get_string_member ("operation");
        var done = yield call ("GET", op + "/wait?timeout=%d".printf (timeout), null, null, (uint) timeout + 15);
        var meta = done.get_object_member ("metadata");
        if (meta.get_int_member_with_default ("status_code", 0) != 200) {
            throw new IOError.FAILED (meta.get_string_member_with_default ("err", "Operation failed"));
        }
    }
    public static string json_string (Json.Object value) {
        var node = new Json.Node (Json.NodeType.OBJECT);
        node.set_object (value);
        var generator = new Json.Generator () { root = node, pretty = true };
        return generator.to_data (null);
    }

    public async Json.Object inspect_instance (string name) throws Error {
        return yield call ("GET", "/1.0/instances/" + Uri.escape_string (name, null, false));
    }

    public async void update_instance (string name, Json.Object config, string etag) throws Error {
        var body = new Json.Object ();
        body.set_object_member ("config", config);
        var result = yield call ("PATCH", "/1.0/instances/" + Uri.escape_string (name, null, false), json_string (body), etag);
        yield wait_operation (result);
    }

    public async string read_log (string name, string filename) throws Error {
        var path = "/1.0/instances/%s/logs/%s".printf (Uri.escape_string (name, null, false), Uri.escape_string (filename, null, false));
        var message = new Soup.Message ("GET", "http://incus" + path);
        message.request_headers.replace ("Range", "bytes=-1048576");
        var input = yield session.send_async (message, Priority.DEFAULT, null);
        if (message.status_code >= 400) throw new IOError.FAILED ("Cannot read %s: HTTP %u".printf (filename, message.status_code));
        var tail = new ByteArray ();
        while (true) {
            var chunk = yield input.read_bytes_async (65536, Priority.DEFAULT, null);
            if (chunk.get_size () == 0) break;
            uint extra = tail.len + (uint) chunk.get_size ();
            if (extra > 1048576) tail.remove_range (0, extra - 1048576);
            tail.append (chunk.get_data ());
        }
        yield input.close_async (Priority.DEFAULT, null);
        if (tail.len == 0) return "";
        return ((string) tail.data).make_valid (tail.len);
    }

    public async void clone_instance (string name, string target) throws Error {
        var source = new Json.Object ();
        source.set_string_member ("type", "copy");
        source.set_string_member ("source", name);
        var body = new Json.Object ();
        body.set_string_member ("name", target);
        body.set_object_member ("source", source);
        var result = yield call ("POST", "/1.0/instances", json_string (body));
        yield wait_operation (result, 600);
    }

    public async void patch_resource (string path, Json.Object patch, string etag) throws Error {
        var response = yield call ("PATCH", path, json_string (patch), etag);
        yield wait_operation (response);
    }

    public async void export_instance (string name, File destination) throws Error {
        var backup = "orchard-export-" + Uuid.string_random ();
        var base_path = "/1.0/instances/" + Uri.escape_string (name, null, false) + "/backups";
        var body = new Json.Object ();
        body.set_string_member ("name", backup);
        body.set_string_member ("expires_at", new DateTime.now_utc ().add_hours (1).format ("%Y-%m-%dT%H:%M:%SZ"));
        var response = yield call ("POST", base_path, json_string (body));
        yield wait_operation (response, 600);
        Error? failure = null;
        File? temporary = null;
        try {
            temporary = destination.get_parent ().get_child (".orchard-export-" + Uuid.string_random ());
            var message = new Soup.Message ("GET", "http://incus" + base_path + "/" + backup + "/export");
            var input = yield session.send_async (message, Priority.DEFAULT, null);
            if (message.status_code >= 400) throw new IOError.FAILED ("Backup download failed: HTTP %u".printf (message.status_code));
            var output = yield temporary.create_async (FileCreateFlags.PRIVATE, Priority.DEFAULT, null);
            yield output.splice_async (input, OutputStreamSpliceFlags.CLOSE_SOURCE | OutputStreamSpliceFlags.CLOSE_TARGET, Priority.DEFAULT, null);
            temporary.move (destination, FileCopyFlags.OVERWRITE, null, null);
        } catch (Error e) { failure = e; }
        try { var cleanup = yield call ("DELETE", base_path + "/" + backup); yield wait_operation (cleanup); } catch (Error e) {
            if (failure == null) failure = new IOError.FAILED ("Archive saved, but temporary backup cleanup failed: " + e.message);
        }
        if (temporary != null) { try { temporary.delete (); } catch (Error e) { } }
        if (failure != null) throw failure;
    }

    public async string journal (string name) throws Error {
        var command = new Json.Array ();
        command.add_string_element ("journalctl"); command.add_string_element ("--no-pager");
        command.add_string_element ("-n"); command.add_string_element ("500");
        var body = new Json.Object ();
        body.set_array_member ("command", command);
        body.set_boolean_member ("wait-for-websocket", false);
        body.set_boolean_member ("record-output", true);
        body.set_boolean_member ("interactive", false);
        var response = yield call ("POST", "/1.0/instances/" + Uri.escape_string (name, null, false) + "/exec", json_string (body));
        yield wait_operation (response);
        var operation = yield call ("GET", response.get_string_member ("operation"));
        var metadata = operation.get_object_member ("metadata").get_object_member ("metadata");
        var output = metadata.get_object_member ("output");
        var text = new StringBuilder ();
        foreach (var stream in output.get_members ()) {
            var message = new Soup.Message ("GET", "http://incus" + output.get_string_member (stream));
            var bytes = yield session.send_and_read_async (message, Priority.DEFAULT, null);
            if (message.status_code >= 400) throw new IOError.FAILED ("Cannot read recorded journal output.");
            text.append (((string) bytes.get_data ()).make_valid ((ssize_t) bytes.get_size ()));
        }
        foreach (var stream in output.get_members ()) {
            try { yield call ("DELETE", output.get_string_member (stream)); } catch (Error e) { /* Incus may already have rotated the captured log. */ }
        }
        if (metadata.get_int_member_with_default ("return", 1) != 0) throw new IOError.FAILED (text.str == "" ? "This image does not provide journalctl." : text.str);
        return text.str;
    }

    public static bool same_user_config (Json.Object before, Json.Object after) {
        foreach (var key in before.get_members ()) {
            if (key.has_prefix ("volatile.")) continue;
            if (!after.has_member (key) || before.get_string_member (key) != after.get_string_member (key)) return false;
        }
        foreach (var key in after.get_members ()) if (!key.has_prefix ("volatile.") && !before.has_member (key)) return false;
        return true;
    }

    public async void update_with_restart (string name, Json.Object config, string expected_etag) throws Error {
        var before = yield inspect_instance (name);
        if (expected_etag == "" || before.get_string_member_with_default ("_orchard_etag", "") != expected_etag) throw new IOError.FAILED ("Configuration changed elsewhere. Refresh before restarting.");
        var original = before.get_object_member ("metadata").get_object_member ("config");
        if (before.get_object_member ("metadata").get_boolean_member_with_default ("ephemeral", false) && before.get_object_member ("metadata").get_string_member ("status") != "Stopped") throw new IOError.FAILED ("This instance is ephemeral: stopping it deletes it. Clone it to a persistent instance before applying a restart.");
        if (before.get_object_member ("metadata").get_string_member ("status") != "Stopped") yield change_state (name, "stop");
        var stopped = yield inspect_instance (name);
        if (!same_user_config (original, stopped.get_object_member ("metadata").get_object_member ("config"))) throw new IOError.FAILED ("Configuration changed while stopping. The instance stays stopped; refresh before applying.");
        yield update_instance (name, config, stopped.get_string_member ("_orchard_etag"));
        yield change_state (name, "start");
    }

}
