/* In-memory model of one Claude Code JSONL transcript plus the parser.
 * Parsing never touches GTK, so it can run on a worker thread. */

public enum BlockKind { TEXT, TOOL_USE }

public class Block : Object {
    public BlockKind kind;
    public string text = "";          // TEXT: markdown body
    public string tool_name = "";     // TOOL_USE
    public string tool_id = "";
    public string summary = "";       // one-line description of the call
    public string input_detail = ""; // pretty-printed input
    public string result = "";        // tool result text, filled in later
    public bool result_is_error = false;
}

public class Message : Object {
    public string role;               // "user" or "assistant"
    public string timestamp = "";
    public List<Block> blocks = new List<Block> ();
    public bool has_visible_content () {
        foreach (var block in blocks) {
            if (block.kind == BlockKind.TOOL_USE || block.text.strip () != "") return true;
        }
        return false;
    }
}

public class Transcript : Object {
    public string session_id = "";
    public string cwd = "";
    public string title = "";
    public List<Message> messages = new List<Message> ();
    private HashTable<string, Block> tool_blocks = new HashTable<string, Block> (str_hash, str_equal);

    /* Strips harness-injected tags that are not the user's own words. */
    public static string clean_user_text (string raw) {
        var text = raw;
        try {
            text = new Regex ("<system-reminder[^>]*>.*?</system-reminder>", RegexCompileFlags.DOTALL).replace (text, -1, 0, "");
            text = new Regex ("<(command-name|command-message|command-args|local-command-stdout|local-command-stderr)>.*?</\\1>", RegexCompileFlags.DOTALL).replace (text, -1, 0, "");
        } catch (Error e) { }
        return text.strip ();
    }

    public static string first_line (string text, int max_chars = 90) {
        var line = text.strip ();
        int nl = line.index_of_char ('\n');
        if (nl >= 0) line = line.substring (0, nl).strip ();
        if (line.char_count () > max_chars) line = line.substring (0, line.index_of_nth_char (max_chars)).strip () + "…";
        return line;
    }

    public static Transcript load (string path) {
        var transcript = new Transcript ();
        var stream = FileStream.open (path, "r");
        if (stream == null) return transcript;
        var parser = new Json.Parser ();
        string? line;
        while ((line = stream.read_line ()) != null) {
            if (line.length < 2) continue;
            try {
                parser.load_from_data (line, -1);
            } catch (Error e) { continue; }
            var root = parser.get_root ();
            if (root == null || root.get_node_type () != Json.NodeType.OBJECT) continue;
            transcript.ingest (root.get_object ());
        }
        return transcript;
    }

    /* Feeds one JSON record (from disk or from the live stream). Returns the
     * message that was appended, or null when the record was not a chat turn. */
    public Message? ingest (Json.Object record) {
        var type = str_member (record, "type");
        if (type == "custom-title") { title = str_member (record, "customTitle"); return null; }
        if (type == "summary" && title == "") { title = str_member (record, "summary"); return null; }
        if (type != "user" && type != "assistant") return null;
        if (record.has_member ("isSidechain") && record.get_boolean_member ("isSidechain")) return null;
        if (record.has_member ("isMeta") && record.get_boolean_member ("isMeta")) return null;
        if (session_id == "") session_id = str_member (record, "sessionId");
        if (cwd == "") cwd = str_member (record, "cwd");
        if (!record.has_member ("message") || record.get_member ("message").get_node_type () != Json.NodeType.OBJECT) return null;
        var message = record.get_object_member ("message");
        var role = str_member (message, "role");
        if (role != "user" && role != "assistant") role = type;
        var turn = new Message ();
        turn.role = role;
        turn.timestamp = str_member (record, "timestamp");
        if (!message.has_member ("content")) return null;
        var content = message.get_member ("content");
        if (content.get_node_type () == Json.NodeType.VALUE && content.get_value_type () == typeof (string)) {
            var block = new Block () { kind = BlockKind.TEXT, text = role == "user" ? clean_user_text (content.get_string ()) : content.get_string () };
            turn.blocks.append (block);
        } else if (content.get_node_type () == Json.NodeType.ARRAY) {
            var array = content.get_array ();
            for (uint i = 0; i < array.get_length (); i++) {
                var element = array.get_element (i);
                if (element.get_node_type () != Json.NodeType.OBJECT) continue;
                ingest_block (turn, element.get_object ());
            }
        }
        if (!turn.has_visible_content ()) return null;
        // Merge consecutive assistant records (the CLI writes one per content block).
        unowned List<Message> last = messages.last ();
        if (last != null && last.data.role == "assistant" && turn.role == "assistant" && turn.timestamp != "" && last.data.timestamp != ""
            && turn.timestamp.substring (0, 16) == last.data.timestamp.substring (0, 16)) {
            foreach (var block in turn.blocks) last.data.blocks.append (block);
            return last.data;
        }
        messages.append (turn);
        return turn;
    }

    private void ingest_block (Message turn, Json.Object block) {
        var kind = str_member (block, "type");
        if (kind == "text") {
            var text = str_member (block, "text");
            if (turn.role == "user") text = clean_user_text (text);
            turn.blocks.append (new Block () { kind = BlockKind.TEXT, text = text });
        } else if (kind == "tool_use") {
            var item = new Block () { kind = BlockKind.TOOL_USE };
            item.tool_name = str_member (block, "name");
            item.tool_id = str_member (block, "id");
            Json.Object? input = block.has_member ("input") && block.get_member ("input").get_node_type () == Json.NodeType.OBJECT ? block.get_object_member ("input") : null;
            item.summary = describe_tool (item.tool_name, input);
            if (block.has_member ("input")) item.input_detail = Json.to_string (block.get_member ("input"), true);
            if (item.tool_id != "") tool_blocks.insert (item.tool_id, item);
            turn.blocks.append (item);
        } else if (kind == "tool_result") {
            var id = str_member (block, "tool_use_id");
            var target = tool_blocks.lookup (id);
            if (target == null) return;
            target.result_is_error = block.has_member ("is_error") && block.get_member ("is_error").get_node_type () == Json.NodeType.VALUE && block.get_boolean_member ("is_error");
            target.result = result_text (block);
        }
    }

    public static string result_text (Json.Object block) {
        if (!block.has_member ("content")) return "";
        var content = block.get_member ("content");
        if (content.get_node_type () == Json.NodeType.VALUE && content.get_value_type () == typeof (string)) return content.get_string ();
        if (content.get_node_type () != Json.NodeType.ARRAY) return "";
        var builder = new StringBuilder ();
        var array = content.get_array ();
        for (uint i = 0; i < array.get_length (); i++) {
            var element = array.get_element (i);
            if (element.get_node_type () != Json.NodeType.OBJECT) continue;
            var part = element.get_object ();
            var kind = str_member (part, "type");
            if (kind == "text") { if (builder.len > 0) builder.append_c ('\n'); builder.append (str_member (part, "text")); }
            else if (kind == "image") { if (builder.len > 0) builder.append_c ('\n'); builder.append ("[image]"); }
        }
        return builder.str;
    }

    public static string describe_tool (string name, Json.Object? input) {
        string detail = "";
        if (input != null) {
            switch (name) {
                case "Bash": detail = str_member (input, "description"); if (detail == "") detail = str_member (input, "command"); break;
                case "Edit": case "Write": case "Read": case "NotebookEdit": detail = str_member (input, "file_path"); break;
                case "Grep": case "Glob": detail = str_member (input, "pattern"); break;
                case "Agent": case "Task": detail = str_member (input, "description"); break;
                case "WebFetch": detail = str_member (input, "url"); break;
                case "WebSearch": detail = str_member (input, "query"); break;
                case "Skill": detail = str_member (input, "skill"); break;
                default:
                    foreach (var member in input.get_members ()) {
                        var node = input.get_member (member);
                        if (node.get_node_type () == Json.NodeType.VALUE && node.get_value_type () == typeof (string)) { detail = node.get_string (); break; }
                    }
                    break;
            }
        }
        string verb;
        switch (name) {
            case "Bash": verb = "Ran Bash"; break;
            case "Edit": verb = "Edited file"; break;
            case "Write": verb = "Wrote file"; break;
            case "Read": verb = "Read file"; break;
            case "Grep": verb = "Searched for"; break;
            case "Glob": verb = "Listed files"; break;
            case "Agent": case "Task": verb = "Started agent"; break;
            case "WebFetch": verb = "Fetched"; break;
            case "WebSearch": verb = "Searched the web"; break;
            default: verb = "Used " + name.replace ("mcp__", "").replace ("__", " · "); break;
        }
        detail = first_line (detail, 120);
        return detail == "" ? verb : verb + ": " + detail;
    }

    public static string str_member (Json.Object object, string name) {
        if (!object.has_member (name)) return "";
        var node = object.get_member (name);
        if (node.get_node_type () != Json.NodeType.VALUE || node.get_value_type () != typeof (string)) return "";
        return node.get_string ();
    }

    public static string icon_for_tool (string name) {
        switch (name) {
            case "Bash": return "utilities-terminal-symbolic";
            case "Edit": case "Write": case "NotebookEdit": return "document-edit-symbolic";
            case "Read": return "document-open-symbolic";
            case "Grep": case "Glob": return "system-search-symbolic";
            case "Agent": case "Task": return "system-users-symbolic";
            case "WebFetch": case "WebSearch": return "web-browser-symbolic";
            default: return "applications-utilities-symbolic";
        }
    }
}
