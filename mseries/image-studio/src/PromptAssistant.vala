public class PromptAssistant : Object {
    private Soup.Session session = new Soup.Session () { timeout = 30 };
    private string endpoint;

    public PromptAssistant (string? endpoint = null) {
        this.endpoint = endpoint ?? Environment.get_variable ("M_SERIES_LLM_API") ?? "http://127.0.0.1:8766/v1";
    }

    private async Json.Object request (string path, Json.Object? body = null) throws Error {
        var message = new Soup.Message (body == null ? "GET" : "POST", endpoint + path);
        if (body != null) {
            var node = new Json.Node (Json.NodeType.OBJECT);
            node.set_object (body);
            var generator = new Json.Generator ();
            generator.set_root (node);
            message.set_request_body_from_bytes ("application/json", new Bytes (generator.to_data (null).data));
        }

        var bytes = yield session.send_and_read_async (message, Priority.DEFAULT, null);
        if (message.status_code < 200 || message.status_code >= 300) {
            throw new IOError.FAILED ("Local prompt service returned HTTP %u.".printf (message.status_code));
        }
        var parser = new Json.Parser ();
        parser.load_from_data ((string) bytes.get_data (), (ssize_t) bytes.get_size ());
        if (parser.get_root () == null || parser.get_root ().get_node_type () != Json.NodeType.OBJECT) {
            throw new IOError.INVALID_DATA ("Local prompt service returned invalid JSON.");
        }
        return parser.get_root ().get_object ();
    }

    public async string suggest (string intent, string original_prompt) throws Error {
        var host = HostCapabilities.capture ();
        if (!host.desktop_reserve_met ()) {
            throw new IOError.NO_SPACE ("Prompt help is paused until the 6 GiB desktop memory reserve is available.");
        }

        var model_response = yield request ("/models");
        if (!model_response.has_member ("data") || model_response.get_member ("data").get_node_type () != Json.NodeType.ARRAY || model_response.get_array_member ("data").get_length () == 0) {
            throw new IOError.NOT_FOUND ("No model is currently available from the M-Series local assistant.");
        }
        var model_entry = model_response.get_array_member ("data").get_element (0);
        if (model_entry.get_node_type () != Json.NodeType.OBJECT || !model_entry.get_object ().has_member ("id")) {
            throw new IOError.INVALID_DATA ("The local assistant returned an invalid model list.");
        }
        var model_id = model_entry.get_object ().get_string_member ("id");

        var messages = new Json.Array ();
        var system = new Json.Object ();
        system.set_string_member ("role", "system");
        system.set_string_member ("content", "Help the user shape a concise image-generation prompt. Preserve their subject and intent. If they describe a college-age person, keep them clearly adult. Do not add nudity or sexualization. Return a suggested prompt and one short reason; do not change model settings or submit a generation.");
        messages.add_object_element (system);
        var user = new Json.Object ();
        user.set_string_member ("role", "user");
        user.set_string_member ("content", "Prompt type: %s\nOriginal prompt: %s".printf (intent, original_prompt));
        messages.add_object_element (user);
        var body = new Json.Object ();
        body.set_string_member ("model", model_id);
        body.set_array_member ("messages", messages);
        body.set_boolean_member ("stream", false);
        body.set_double_member ("temperature", 0.25);

        var response = yield request ("/chat/completions", body);
        if (!response.has_member ("choices") || response.get_member ("choices").get_node_type () != Json.NodeType.ARRAY || response.get_array_member ("choices").get_length () == 0) {
            throw new IOError.INVALID_DATA ("The local assistant returned no prompt suggestion.");
        }
        var choice = response.get_array_member ("choices").get_element (0);
        if (choice.get_node_type () != Json.NodeType.OBJECT || !choice.get_object ().has_member ("message")) {
            throw new IOError.INVALID_DATA ("The local assistant returned an invalid response.");
        }
        var message = choice.get_object ().get_object_member ("message");
        if (!message.has_member ("content") || message.get_member ("content").get_value_type () != typeof (string)) {
            throw new IOError.INVALID_DATA ("The local assistant returned an empty suggestion.");
        }
        var suggestion = message.get_string_member ("content").strip ();
        if (suggestion == "") throw new IOError.INVALID_DATA ("The local assistant returned an empty suggestion.");
        return suggestion;
    }
}
