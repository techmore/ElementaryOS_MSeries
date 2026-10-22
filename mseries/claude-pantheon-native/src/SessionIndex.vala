/* Scans ~/.claude/projects for transcripts and extracts enough metadata for
 * the sidebar without parsing whole files: head bytes for the first prompt
 * and cwd, tail bytes for a custom title. */

public class Session : Object {
    public string path = "";     // transcript file
    public string id = "";       // session uuid
    public string project = "";  // working directory
    public string title = "";
    public int64 modified = 0;   // unix seconds
    public int64 size = 0;

    public string project_name {
        owned get {
            var name = Path.get_basename (project);
            return name == "" || name == "/" ? project : name;
        }
    }
}

public class SessionIndex : Object {
    public const int HEAD_BYTES = 65536;
    public const int TAIL_BYTES = 32768;

    public static string projects_dir () {
        return Path.build_filename (Environment.get_home_dir (), ".claude", "projects");
    }

    public static string cache_dir () {
        var dir = Path.build_filename (Environment.get_user_cache_dir (), "claude-pantheon");
        DirUtils.create_with_parents (dir, 0700);
        return dir;
    }

    /* Blocking scan; call from a worker thread. */
    public static List<Session> scan () {
        var sessions = new List<Session> ();
        var cache = load_cache ();
        var fresh = new Json.Object ();
        try {
            var root = File.new_for_path (projects_dir ());
            var projects = root.enumerate_children ("standard::name,standard::type", FileQueryInfoFlags.NONE);
            FileInfo? project_info;
            while ((project_info = projects.next_file ()) != null) {
                if (project_info.get_file_type () != FileType.DIRECTORY) continue;
                var slug = project_info.get_name ();
                var dir = root.get_child (slug);
                FileEnumerator files;
                try { files = dir.enumerate_children ("standard::name,standard::size,time::modified", FileQueryInfoFlags.NONE); } catch (Error e) { continue; }
                FileInfo? info;
                while ((info = files.next_file ()) != null) {
                    var name = info.get_name ();
                    if (!name.has_suffix (".jsonl")) continue;
                    var session = new Session ();
                    session.path = dir.get_child (name).get_path ();
                    session.id = name.substring (0, name.length - 6);
                    session.modified = (int64) info.get_attribute_uint64 ("time::modified");
                    session.size = info.get_size ();
                    session.project = slug_to_path (slug);
                    var key = session.path;
                    var cached = cache != null && cache.has_member (key) ? cache.get_object_member (key) : null;
                    if (cached != null && cached.get_int_member ("modified") == session.modified && cached.get_int_member ("size") == session.size) {
                        session.title = Transcript.str_member (cached, "title");
                        var cwd = Transcript.str_member (cached, "project");
                        if (cwd != "") session.project = cwd;
                    } else {
                        inspect (session);
                    }
                    if (session.title == "") continue; // nothing a person typed
                    var entry = new Json.Object ();
                    entry.set_int_member ("modified", session.modified);
                    entry.set_int_member ("size", session.size);
                    entry.set_string_member ("title", session.title);
                    entry.set_string_member ("project", session.project);
                    fresh.set_object_member (key, entry);
                    sessions.append (session);
                }
            }
        } catch (Error e) {
            warning ("Could not scan %s: %s", projects_dir (), e.message);
        }
        save_cache (fresh);
        sessions.sort ((a, b) => a.modified > b.modified ? -1 : a.modified < b.modified ? 1 : 0);
        return sessions;
    }

    public static string slug_to_path (string slug) {
        // Slugs replace '/' with '-' which is lossy; this is only a fallback when the
        // transcript does not carry its cwd.
        if (slug.has_prefix ("-")) return slug.replace ("-", "/");
        return slug;
    }

    private static void inspect (Session session) {
        var stream = FileStream.open (session.path, "r");
        if (stream == null) return;
        var parser = new Json.Parser ();
        string? line = null;
        int64 consumed = 0;
        string first_prompt = "";
        while (consumed < HEAD_BYTES && (line = stream.read_line ()) != null) {
            consumed += line.length + 1;
            if (!line.contains ("\"type\":\"user\"") && !line.contains ("\"custom-title\"") && !line.contains ("\"summary\"")) continue;
            Json.Object? record = parse_line (parser, line);
            if (record == null) continue;
            var type = Transcript.str_member (record, "type");
            if (type == "custom-title") { session.title = Transcript.str_member (record, "customTitle"); }
            else if (type == "summary" && session.title == "") { session.title = Transcript.str_member (record, "summary"); }
            else if (type == "user" && first_prompt == "") {
                if (record.has_member ("isMeta") && record.get_boolean_member ("isMeta")) continue;
                var cwd = Transcript.str_member (record, "cwd");
                if (cwd != "") session.project = cwd;
                first_prompt = user_text (record);
            }
            if (session.title != "" && first_prompt != "") break;
        }
        if (session.title == "" && session.size > HEAD_BYTES) {
            // Custom titles are appended as the chat goes; look at the tail too.
            stream.seek (-(long) TAIL_BYTES, FileSeek.END);
            stream.read_line (); // discard partial line
            while ((line = stream.read_line ()) != null) {
                if (!line.contains ("\"custom-title\"") && !line.contains ("\"summary\"")) continue;
                Json.Object? record = parse_line (parser, line);
                if (record == null) continue;
                var type = Transcript.str_member (record, "type");
                if (type == "custom-title") session.title = Transcript.str_member (record, "customTitle");
                else if (type == "summary" && session.title == "") session.title = Transcript.str_member (record, "summary");
            }
        }
        if (session.title == "") session.title = Transcript.first_line (first_prompt);
    }

    private static Json.Object? parse_line (Json.Parser parser, string line) {
        try { parser.load_from_data (line, -1); } catch (Error e) { return null; }
        var root = parser.get_root ();
        if (root == null || root.get_node_type () != Json.NodeType.OBJECT) return null;
        return root.get_object ();
    }

    private static string user_text (Json.Object record) {
        if (!record.has_member ("message") || record.get_member ("message").get_node_type () != Json.NodeType.OBJECT) return "";
        var message = record.get_object_member ("message");
        if (!message.has_member ("content")) return "";
        var content = message.get_member ("content");
        if (content.get_node_type () == Json.NodeType.VALUE && content.get_value_type () == typeof (string)) return Transcript.clean_user_text (content.get_string ());
        if (content.get_node_type () != Json.NodeType.ARRAY) return "";
        var array = content.get_array ();
        for (uint i = 0; i < array.get_length (); i++) {
            var element = array.get_element (i);
            if (element.get_node_type () != Json.NodeType.OBJECT) continue;
            var block = element.get_object ();
            if (Transcript.str_member (block, "type") == "text") {
                var text = Transcript.clean_user_text (Transcript.str_member (block, "text"));
                if (text != "") return text;
            }
        }
        return "";
    }

    private static string cache_file () { return Path.build_filename (cache_dir (), "sessions.json"); }

    private static Json.Object? load_cache () {
        try {
            var parser = new Json.Parser ();
            parser.load_from_file (cache_file ());
            var root = parser.get_root ();
            if (root != null && root.get_node_type () == Json.NodeType.OBJECT) return root.get_object ();
        } catch (Error e) { }
        return null;
    }

    private static void save_cache (Json.Object entries) {
        try {
            var node = new Json.Node (Json.NodeType.OBJECT); node.set_object (entries);
            var generator = new Json.Generator () { root = node };
            FileUtils.set_contents (cache_file (), generator.to_data (null));
        } catch (Error e) { }
    }
}
