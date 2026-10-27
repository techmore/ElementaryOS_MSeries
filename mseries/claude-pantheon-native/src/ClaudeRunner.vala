/* Runs the claude CLI in print mode with stream-json output and turns its
 * events into signals. One runner per in-flight prompt. */

public class ClaudeRunner : Object {
    public signal void session_started (string session_id);
    public signal void text_delta (string delta);
    public signal void text_done (string full_text);
    public signal void tool_use (Block block);
    public signal void tool_result (string tool_id);
    public signal void finished (bool ok, string note);

    private Subprocess? process;
    private StringBuilder current_text = new StringBuilder ();
    private HashTable<string, Block> blocks = new HashTable<string, Block> (str_hash, str_equal);
    private bool cancelled = false;
    private StringBuilder stderr_text = new StringBuilder ();
    private bool debug = Environment.get_variable ("CLAUDE_PANTHEON_DEBUG") != null;

    public static string? find_binary () {
        var env = Environment.get_variable ("CLAUDE_BIN");
        if (env != null && FileUtils.test (env, FileTest.IS_EXECUTABLE)) return env;
        var found = Environment.find_program_in_path ("claude");
        if (found != null) return found;
        string? best = null;
        int64 best_time = 0;
        var root = Path.build_filename (Environment.get_home_dir (), ".config", "Claude", "claude-code");
        try {
            var versions = Dir.open (root);
            string? version;
            while ((version = versions.read_name ()) != null) {
                var vdir = Path.build_filename (root, version);
                Dir builds;
                try { builds = Dir.open (vdir); } catch (Error e) { continue; }
                string? build;
                while ((build = builds.read_name ()) != null) {
                    var candidate = Path.build_filename (vdir, build, "claude");
                    if (!FileUtils.test (candidate, FileTest.IS_EXECUTABLE)) continue;
                    Posix.Stat st;
                    if (Posix.stat (candidate, out st) != 0) continue;
                    if (best == null || (int64) st.st_mtime > best_time) { best = candidate; best_time = (int64) st.st_mtime; }
                }
            }
        } catch (Error e) { }
        if (best != null) return best;
        string[] fallbacks = {
            Path.build_filename (Environment.get_home_dir (), ".local", "bin", "claude"),
            "/usr/lib/claude-desktop/resources/claude",
            "/usr/local/bin/claude"
        };
        foreach (var path in fallbacks) if (FileUtils.test (path, FileTest.IS_EXECUTABLE)) return path;
        return null;
    }

    public bool start (string prompt, string cwd, string? resume_id, string permission_mode) {
        var binary = find_binary ();
        if (binary == null) { finished (false, "The claude command line tool was not found."); return false; }
        string[] argv = { binary, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages" };
        if (resume_id != null && resume_id != "") { argv += "--resume"; argv += resume_id; }
        if (permission_mode != "" && permission_mode != "default") { argv += "--permission-mode"; argv += permission_mode; }
        argv += prompt;
        var launcher = new SubprocessLauncher (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE | SubprocessFlags.STDIN_PIPE);
        if (cwd != "" && FileUtils.test (cwd, FileTest.IS_DIR)) launcher.set_cwd (cwd);
        try {
            process = launcher.spawnv (argv);
        } catch (Error e) {
            finished (false, "Could not start claude: " + e.message);
            return false;
        }
        try { process.get_stdin_pipe ().close (); } catch (Error e) { }
        read_stdout.begin ();
        read_stderr.begin ();
        return true;
    }

    public void stop () {
        cancelled = true;
        if (process != null) process.send_signal (Posix.Signal.TERM);
        Timeout.add (1500, () => { if (process != null) process.force_exit (); return Source.REMOVE; });
    }

    private async void read_stderr () {
        var stream = new DataInputStream (process.get_stderr_pipe ());
        try {
            string? line;
            while ((line = yield stream.read_line_async (Priority.LOW)) != null) {
                if (stderr_text.len < 4000) { stderr_text.append (line); stderr_text.append_c ('\n'); }
            }
        } catch (Error e) { }
    }

    private async void read_stdout () {
        var stream = new DataInputStream (process.get_stdout_pipe ());
        var parser = new Json.Parser ();
        bool got_result = false;
        string note = "";
        try {
            string? line;
            while ((line = yield stream.read_line_async (Priority.DEFAULT)) != null) {
                if (line.strip () == "") continue;
                try { parser.load_from_data (line, -1); } catch (Error e) { continue; }
                var root = parser.get_root ();
                if (root == null || root.get_node_type () != Json.NodeType.OBJECT) continue;
                var record = root.get_object ();
                var type = Transcript.str_member (record, "type");
                if (debug) stderr.printf ("claude> %s\n", line.length > 300 ? line.substring (0, 300) : line);
                if (type == "system") {
                    if (Transcript.str_member (record, "subtype") == "init") session_started (Transcript.str_member (record, "session_id"));
                } else if (type == "stream_event") {
                    handle_stream_event (record);
                } else if (type == "assistant") {
                    handle_assistant (record);
                } else if (type == "user") {
                    handle_user (record);
                } else if (type == "result") {
                    got_result = true;
                    var subtype = Transcript.str_member (record, "subtype");
                    if (subtype != "success") note = Transcript.str_member (record, "result");
                    if (note == "" && record.has_member ("is_error") && record.get_boolean_member ("is_error")) note = "Claude reported an error.";
                    if (subtype != "success" && note == "") note = subtype.replace ("_", " ");
                }
            }
        } catch (Error e) { note = e.message; }
        try { yield process.wait_async (); } catch (Error e) { }
        if (cancelled) { finished (true, "Stopped."); return; }
        if (!got_result && note == "") {
            note = process.get_if_exited () && process.get_exit_status () != 0 ? "claude exited with status %d".printf (process.get_exit_status ()) : "";
            if (stderr_text.len > 0) note = (note == "" ? "" : note + "\n") + stderr_text.str.strip ();
        }
        finished (note == "", note);
    }

    private void handle_stream_event (Json.Object record) {
        if (!record.has_member ("event") || record.get_member ("event").get_node_type () != Json.NodeType.OBJECT) return;
        var event = record.get_object_member ("event");
        var kind = Transcript.str_member (event, "type");
        if (kind == "content_block_delta" && event.has_member ("delta")) {
            var delta = event.get_object_member ("delta");
            if (Transcript.str_member (delta, "type") == "text_delta") {
                var text = Transcript.str_member (delta, "text");
                current_text.append (text);
                text_delta (text);
            }
        } else if (kind == "content_block_stop") {
            if (current_text.len > 0) { text_done (current_text.str); current_text.truncate (0); }
        }
    }

    private void handle_assistant (Json.Object record) {
        if (!record.has_member ("message") || record.get_member ("message").get_node_type () != Json.NodeType.OBJECT) return;
        var message = record.get_object_member ("message");
        if (!message.has_member ("content") || message.get_member ("content").get_node_type () != Json.NodeType.ARRAY) return;
        var array = message.get_array_member ("content");
        for (uint i = 0; i < array.get_length (); i++) {
            var node = array.get_element (i);
            if (node.get_node_type () != Json.NodeType.OBJECT) continue;
            var part = node.get_object ();
            var kind = Transcript.str_member (part, "type");
            if (kind == "text") {
                // Text already arrived through deltas; only emit if streaming was unavailable.
                if (current_text.len > 0) { text_done (current_text.str); current_text.truncate (0); }
            } else if (kind == "tool_use") {
                var block = new Block () { kind = BlockKind.TOOL_USE };
                block.tool_name = Transcript.str_member (part, "name");
                block.tool_id = Transcript.str_member (part, "id");
                Json.Object? input = part.has_member ("input") && part.get_member ("input").get_node_type () == Json.NodeType.OBJECT ? part.get_object_member ("input") : null;
                block.summary = Transcript.describe_tool (block.tool_name, input);
                if (part.has_member ("input")) block.input_detail = Json.to_string (part.get_member ("input"), true);
                if (block.tool_id != "" && blocks.lookup (block.tool_id) != null) continue;
                blocks.insert (block.tool_id, block);
                tool_use (block);
            }
        }
    }

    private void handle_user (Json.Object record) {
        if (!record.has_member ("message") || record.get_member ("message").get_node_type () != Json.NodeType.OBJECT) return;
        var message = record.get_object_member ("message");
        if (!message.has_member ("content") || message.get_member ("content").get_node_type () != Json.NodeType.ARRAY) return;
        var array = message.get_array_member ("content");
        for (uint i = 0; i < array.get_length (); i++) {
            var node = array.get_element (i);
            if (node.get_node_type () != Json.NodeType.OBJECT) continue;
            var part = node.get_object ();
            if (Transcript.str_member (part, "type") != "tool_result") continue;
            var id = Transcript.str_member (part, "tool_use_id");
            var block = blocks.lookup (id);
            if (block == null) continue;
            block.result = Transcript.result_text (part);
            block.result_is_error = part.has_member ("is_error") && part.get_member ("is_error").get_node_type () == Json.NodeType.VALUE && part.get_boolean_member ("is_error");
            tool_result (id);
        }
    }
}
