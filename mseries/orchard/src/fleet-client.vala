/* HTTP client for the TM-Remote control plane. Only the public admin API is used (bearer token);
 * none of the server's code lives in this repository. The token is kept in the Secret Service. */

public class FleetClient : Object {
    private static Secret.Schema schema = new Secret.Schema (
        "io.github.mseries.MachineLab.Fleet", Secret.SchemaFlags.NONE,
        "server", Secret.SchemaAttributeType.STRING);

    public string server_url { get; private set; default = ""; }
    private string token = "";
    private Soup.Session session = new Soup.Session ();
    private string config_path = Path.build_filename (Environment.get_user_config_dir (), "machine-lab", "fleet.ini");

    public bool configured { get { return server_url != "" && token != ""; } }

    public FleetClient () {
        session.timeout = 10;
    }

    /* Load the saved server and token. Call off the startup path: the keyring may prompt. */
    public async void load () {
        var keyfile = new KeyFile ();
        try {
            keyfile.load_from_file (config_path, KeyFileFlags.NONE);
            server_url = keyfile.get_string ("server", "url");
            token = (yield Secret.password_lookup (schema, null, "server", server_url)) ?? "";
        } catch (Error e) {
            // Nothing saved yet, or the keyring is locked: the Fleet section just asks to connect.
        }
    }

    public async void save (string typed_url, string new_token) throws Error {
        var url = Fleet.clean_server_url (typed_url);
        if (url == null) {
            throw new IOError.INVALID_ARGUMENT ("The server address must start with https://");
        }
        var tok = new_token.strip ();
        if (tok == "") {
            throw new IOError.INVALID_ARGUMENT ("Enter the API token.");
        }
        yield Secret.password_store (schema, Secret.COLLECTION_DEFAULT, "Machine Lab fleet token", tok, null, "server", url);
        var keyfile = new KeyFile ();
        keyfile.set_string ("server", "url", url);
        DirUtils.create_with_parents (Path.get_dirname (config_path), 0700);
        FileUtils.set_contents (config_path, keyfile.to_data ());
        server_url = url;
        token = tok;
    }

    private async Json.Node request (string method, string path) throws Error {
        var msg = new Soup.Message (method, server_url + path);
        msg.request_headers.append ("Authorization", "Bearer " + token);
        var bytes = yield session.send_and_read_async (msg, Priority.DEFAULT, null);
        if (msg.status_code == 401) {
            throw new IOError.PERMISSION_DENIED ("The server rejected the API token.");
        }
        if (msg.status_code < 200 || msg.status_code >= 300) {
            throw new IOError.FAILED ("The server answered HTTP %u.".printf (msg.status_code));
        }
        var parser = new Json.Parser ();
        parser.load_from_data ((string) bytes.get_data (), (ssize_t) bytes.get_size ());
        return parser.get_root ();
    }

    public async GenericArray<FleetDevice> list_devices () throws Error {
        var root = yield request ("GET", "/api/agents");
        var result = new GenericArray<FleetDevice> ();
        root.get_object ().get_array_member ("agents").foreach_element ((a, i, node) => {
            result.add (FleetDevice.from_json (node.get_object ()));
        });
        return result;
    }

    /* A one-time install command for a new machine. The server makes the code single-use and
     * expires it after 15 minutes. */
    public async string enrollment_command (bool mac) throws Error {
        var root = yield request ("POST", "/api/agents/enrollment-token");
        var cmd = Fleet.enroll_command (server_url, root.get_object ().get_string_member ("token"), mac);
        if (cmd == null) {
            throw new IOError.FAILED ("The server returned a code or address this app refuses to put in a shell command.");
        }
        return cmd;
    }
}
