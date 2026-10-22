public class ModelService : Object {
    private bool use_keyring;
    public ModelService (bool keyring = true) { use_keyring = keyring; }
    private Soup.Session session = new Soup.Session () { timeout = 15 };
    private Secret.Schema schema = new Secret.Schema ("com.github.techmore.orchard-incus.models", Secret.SchemaFlags.NONE, "endpoint", Secret.SchemaAttributeType.STRING, null);

    public static string validate_endpoint (string value) throws Error {
        var text = value.strip ();
        while (text.has_suffix ("/")) text = text.substring (0, text.length - 1);
        var uri = Uri.parse (text, UriFlags.NONE);
        if ((uri.get_scheme () != "http" && uri.get_scheme () != "https") || uri.get_host () == null || uri.get_userinfo () != null || uri.get_query () != null || uri.get_fragment () != null) throw new IOError.INVALID_ARGUMENT ("Use an http(s) model API base URL without credentials, a query or fragment.");
        return text;
    }
    public async void save_key (string endpoint, string key) throws Error {
        if (key == "") yield Secret.password_clear (schema, null, "endpoint", endpoint, null);
        else if (!(yield Secret.password_store (schema, Secret.COLLECTION_DEFAULT, "Orchard model server: " + endpoint, key, null, "endpoint", endpoint, null))) throw new IOError.FAILED ("The desktop keyring did not store the API key.");
    }
    private async Json.Object request (string endpoint, string path, Json.Object? body = null) throws Error {
        var base_url = validate_endpoint (endpoint);
        var message = new Soup.Message (body == null ? "GET" : "POST", base_url + path);
        string? key = null;
        if (use_keyring) key = yield Secret.password_lookup (schema, null, "endpoint", base_url, null);
        if (key != null && key != "") message.request_headers.replace ("Authorization", "Bearer " + key);
        if (body != null) message.set_request_body_from_bytes ("application/json", new Bytes (IncusClient.json_string (body).data));
        var bytes = yield session.send_and_read_async (message, Priority.DEFAULT, null);
        if (message.status_code == 401 || message.status_code == 403) throw new IOError.PERMISSION_DENIED ("The model server requires a valid API key.");
        if (message.status_code >= 400) throw new IOError.FAILED ("Model server returned HTTP %u.".printf (message.status_code));
        var parser = new Json.Parser ();
        parser.load_from_data ((string) bytes.get_data (), (ssize_t) bytes.get_size ());
        if (parser.get_root ().get_node_type () != Json.NodeType.OBJECT) throw new IOError.INVALID_DATA ("Model server returned an invalid document.");
        return parser.get_root ().get_object ();
    }
    public async string[] list_models (string endpoint) throws Error {
        var response = yield request (endpoint, "/models");
        if (!response.has_member ("data") || response.get_member ("data").get_node_type () != Json.NodeType.ARRAY) throw new IOError.INVALID_DATA ("This endpoint does not return an OpenAI-compatible model list.");
        string[] models = {};
        foreach (var node in response.get_array_member ("data").get_elements ()) {
            if (node.get_node_type () != Json.NodeType.OBJECT || !node.get_object ().has_member ("id") || node.get_object ().get_member ("id").get_value_type () != typeof (string)) throw new IOError.INVALID_DATA ("Model server returned an invalid model entry.");
            var model = node.get_object ().get_string_member_with_default ("id", "");
            if (model != "") models += model;
        }
        return models;
    }
    public async string chat (string endpoint, string model, string prompt) throws Error {
        var messages = new Json.Array ();
        var message = new Json.Object ();
        message.set_string_member ("role", "user"); message.set_string_member ("content", prompt);
        messages.add_object_element (message);
        var body = new Json.Object ();
        body.set_string_member ("model", model); body.set_array_member ("messages", messages); body.set_boolean_member ("stream", false);
        var response = yield request (endpoint, "/chat/completions", body);
        if (!response.has_member ("choices") || response.get_member ("choices").get_node_type () != Json.NodeType.ARRAY || response.get_array_member ("choices").get_length () == 0) throw new IOError.INVALID_DATA ("Model server returned no completion.");
        var choice = response.get_array_member ("choices").get_element (0);
        if (choice.get_node_type () != Json.NodeType.OBJECT || !choice.get_object ().has_member ("message") || choice.get_object ().get_member ("message").get_node_type () != Json.NodeType.OBJECT) throw new IOError.INVALID_DATA ("Model server returned an invalid message.");
        var result = choice.get_object ().get_object_member ("message");
        if (!result.has_member ("content") || result.get_member ("content").get_value_type () != typeof (string)) throw new IOError.INVALID_DATA ("Model server did not return a text completion.");
        return result.get_string_member ("content");
    }
}

public class ModelsWindow : Gtk.Window {
    private ModelService service = new ModelService ();
    private Preferences preferences = new Preferences ();
    private Gtk.Entry endpoint;
    private Gtk.PasswordEntry api_key;
    private Gtk.DropDown model;
    private Gtk.TextView transcript;
    private Gtk.Entry prompt;
    private Gtk.Label status;
    private Gtk.Button send;
    private Gtk.CheckButton enabled;

    public ModelsWindow (Gtk.Window parent, string initial_endpoint = "") {
        Object (transient_for: parent, title: "Local AI models", default_width: 680, default_height: 560);
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
        endpoint = new Gtk.Entry () { text = initial_endpoint != "" ? initial_endpoint : preferences.read ("model-endpoint", "http://127.0.0.1:11434/v1"), placeholder_text = "Model API base URL including /v1" };
        box.append (endpoint);
        var bookmarks = new Gtk.DropDown.from_strings (preferences.read ("model-endpoints", "http://127.0.0.1:11434/v1\nhttp://127.0.0.1:1234/v1\nhttp://127.0.0.1:8080/v1").split ("\n"));
        bookmarks.notify["selected"].connect (() => {
            var item = (Gtk.StringObject) bookmarks.selected_item;
            if (item != null) {
                endpoint.text = item.string;
                enabled.active = preferences.read ("model-enabled-" + Checksum.compute_for_string (ChecksumType.SHA256, item.string), "true") == "true";
                send.sensitive = false;
            }
        });
        box.append (bookmarks);
        enabled = new Gtk.CheckButton.with_label ("Enable this model endpoint") { active = preferences.read ("model-enabled", "true") == "true" };
        box.append (enabled);
        api_key = new Gtk.PasswordEntry () { show_peek_icon = true, placeholder_text = "API key (optional, stored in desktop keyring)" };
        box.append (api_key);
        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var save = new Gtk.Button.with_label ("Save endpoint / key"); save.clicked.connect (() => save_endpoint.begin ()); actions.append (save);
        var discover = new Gtk.Button.with_label ("Discover models"); discover.clicked.connect (() => discover_models.begin ()); actions.append (discover);
        var scan = new Gtk.Button.with_label ("Find servers"); scan.clicked.connect (() => scan_servers.begin ()); actions.append (scan);
        var reset = new Gtk.Button.with_label ("Restore default"); reset.clicked.connect (() => { endpoint.text = "http://127.0.0.1:11434/v1"; enabled.active = true; }); actions.append (reset);
        var clear_key = new Gtk.Button.with_label ("Remove stored key");
        clear_key.clicked.connect (() => clear_stored_key.begin ()); actions.append (clear_key);
        box.append (actions);
        model = new Gtk.DropDown.from_strings ({ "Discover models first" }); box.append (model);
        transcript = new Gtk.TextView () { editable = false, wrap_mode = Gtk.WrapMode.WORD_CHAR, left_margin = 8, right_margin = 8 };
        box.append (new Gtk.ScrolledWindow () { child = transcript, vexpand = true });
        var chat_bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        prompt = new Gtk.Entry () { placeholder_text = "Test a prompt", hexpand = true };
        send = new Gtk.Button.with_label ("Send") { sensitive = false };
        send.clicked.connect (() => test_prompt.begin ()); prompt.activate.connect (() => { if (send.sensitive) test_prompt.begin (); });
        chat_bar.append (prompt); chat_bar.append (send); box.append (chat_bar);
        status = new Gtk.Label ("Connect to an existing Ollama, LM Studio or other OpenAI-compatible local server. Orchard does not start or install a model runtime.") { wrap = true, xalign = 0 };
        box.append (status); child = box;
        enabled.toggled.connect (() => { if (!enabled.active) send.sensitive = false; });
        endpoint.changed.connect (() => { api_key.text = ""; send.sensitive = false; });
    }
    private async void save_endpoint () {
        try {
            var base_url = ModelService.validate_endpoint (endpoint.text);
            if (api_key.text != "") { yield service.save_key (base_url, api_key.text); api_key.text = ""; }
            preferences.write ("model-endpoint", base_url);
            preferences.write ("model-enabled", enabled.active ? "true" : "false");
            preferences.write ("model-enabled-" + Checksum.compute_for_string (ChecksumType.SHA256, base_url), enabled.active ? "true" : "false");
            var bookmarks = preferences.read ("model-endpoints", "http://127.0.0.1:11434/v1\nhttp://127.0.0.1:1234/v1\nhttp://127.0.0.1:8080/v1");
            bool present = false;
            foreach (var item in bookmarks.split ("\n")) if (item == base_url) present = true;
            if (!present) preferences.write ("model-endpoints", bookmarks + "\n" + base_url);
            status.label = "Endpoint saved. API keys are retained only in the desktop keyring.";
        } catch (Error e) { status.label = e.message; }
    }
    private async void discover_models () {
        send.sensitive = false;
        try {
            if (!enabled.active) throw new IOError.FAILED ("Enable the model endpoint first.");
            status.label = "Discovering models…";
            var models = yield service.list_models (endpoint.text);
            model.model = new Gtk.StringList (models);
            send.sensitive = models.length > 0;
            status.label = "%d models available.".printf (models.length);
        } catch (Error e) { status.label = e.message; }
    }
    private async void test_prompt () {
        if (prompt.text.strip () == "") return;
        if (!enabled.active) { status.label = "Enable the endpoint before sending a prompt."; send.sensitive = false; return; }
        send.sensitive = false;
        try {
            var chosen = (Gtk.StringObject) model.selected_item;
            var question = prompt.text;
            var answer = yield service.chat (endpoint.text, chosen.string, question);
            transcript.buffer.text += "You: " + question + "\n\nModel: " + answer + "\n\n";
            prompt.text = ""; status.label = "Completion received.";
        } catch (Error e) { status.label = e.message; }
        send.sensitive = true;
    }
    private async void clear_stored_key () {
        try { yield service.save_key (ModelService.validate_endpoint (endpoint.text), ""); status.label = "Stored API key removed."; }
        catch (Error e) { status.label = e.message; }
    }
    private async void scan_servers () {
        send.sensitive = false;
        var results = new StringBuilder (); int found = 0;
        var sources = preferences.read ("model-endpoints", "http://127.0.0.1:11434/v1\nhttp://127.0.0.1:1234/v1\nhttp://127.0.0.1:8080/v1");
        foreach (var source in sources.split ("\n")) {
            if (preferences.read ("model-enabled-" + Checksum.compute_for_string (ChecksumType.SHA256, source), "true") != "true") continue;
            status.label = "Checking " + source + "…";
            try {
                var models = yield service.list_models (source); found++;
                results.append (source + " · " + models.length.to_string () + " models\n");
            } catch (Error e) {
                if (e is IOError.PERMISSION_DENIED) { found++; results.append (source + " · API key required\n"); }
            }
        }
        status.label = found == 0 ? "No configured model servers responded. Start your chosen local model server, then try again." : results.str + "Select an endpoint above and discover its models.";
    }
}
