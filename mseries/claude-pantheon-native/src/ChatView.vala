/* Renders a Transcript as a vertical chat. Messages are appended in idle
 * batches so a long transcript never blocks the frame; tool results are only
 * turned into widgets when a row is expanded. */

public class ToolRow : Gtk.Box {
    private Gtk.Revealer revealer;
    private Gtk.Box details;
    private Block block;
    private bool built = false;
    private Gtk.Image chevron;
    private Gtk.Label label;

    public ToolRow (Block block) {
        Object (orientation: Gtk.Orientation.VERTICAL, spacing: 0);
        this.block = block;
        add_css_class ("tool-row");
        var button = new Gtk.Button () { has_frame = false };
        button.add_css_class ("tool-row-button");
        var header = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        chevron = new Gtk.Image.from_icon_name ("pan-end-symbolic") { pixel_size = 16 };
        chevron.add_css_class ("dim-label");
        var icon = new Gtk.Image.from_icon_name (Transcript.icon_for_tool (block.tool_name)) { pixel_size = 16 };
        label = new Gtk.Label (block.summary) { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END, single_line_mode = true };
        header.append (chevron); header.append (icon); header.append (label);
        button.child = header;
        button.tooltip_text = block.summary;
        button.update_property (Gtk.AccessibleProperty.LABEL, block.summary, -1);
        append (button);
        details = new Gtk.Box (Gtk.Orientation.VERTICAL, 6) { margin_start = 30, margin_end = 8, margin_bottom = 8 };
        revealer = new Gtk.Revealer () { child = details, transition_type = Gtk.RevealerTransitionType.SLIDE_DOWN, reveal_child = false };
        append (revealer);
        button.clicked.connect (toggle);
    }

    public void refresh () {
        label.label = block.summary;
        if (built) { built = false; while (details.get_first_child () != null) details.remove (details.get_first_child ()); if (revealer.reveal_child) build (); }
    }

    private void toggle () {
        if (!built) build ();
        revealer.reveal_child = !revealer.reveal_child;
        chevron.icon_name = revealer.reveal_child ? "pan-down-symbolic" : "pan-end-symbolic";
    }

    private void build () {
        built = true;
        if (block.input_detail != "" && block.input_detail != "{}") details.append (ChatView.code_widget (clip (block.input_detail), "Input"));
        if (block.result != "") {
            var result = ChatView.code_widget (clip (block.result), block.result_is_error ? "Error" : "Result");
            if (block.result_is_error) result.add_css_class ("tool-error");
            details.append (result);
        } else {
            var pending = new Gtk.Label ("No result recorded") { xalign = 0 };
            pending.add_css_class ("dim-label");
            details.append (pending);
        }
    }

    private static string clip (string text) {
        const int LIMIT = 12000;
        if (text.length <= LIMIT) return text;
        return text.substring (0, text.index_of_nth_char (LIMIT < text.char_count () ? LIMIT : text.char_count ())) + "\n… (%s more)".printf (format_size (text.length - LIMIT));
    }
}

public class ChatView : Gtk.Box {
    private Gtk.Box list;
    private Gtk.ScrolledWindow scroller;
    private uint render_source = 0;
    private unowned List<Message>? pending = null;
    private Transcript? transcript;
    private Gtk.Label? live_label = null;     // assistant text that is still streaming
    private Gtk.Box? live_group = null;
    private Gtk.Label empty;
    private Gtk.Box empty_box;
    private HashTable<string, ToolRow> tool_rows = new HashTable<string, ToolRow> (str_hash, str_equal);
    public bool follow_tail = false;

    public ChatView () {
        Object (orientation: Gtk.Orientation.VERTICAL, spacing: 0);
        list = new Gtk.Box (Gtk.Orientation.VERTICAL, 14) { margin_top = 18, margin_bottom = 18, margin_start = 20, margin_end = 20, valign = Gtk.Align.START };
        var clamp = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { halign = Gtk.Align.FILL };
        list.hexpand = true;
        list.add_css_class ("chat-list");
        clamp.append (list);
        scroller = new Gtk.ScrolledWindow () { child = clamp, vexpand = true, hexpand = true, hscrollbar_policy = Gtk.PolicyType.NEVER };
        append (scroller);
        empty_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { valign = Gtk.Align.CENTER, halign = Gtk.Align.CENTER, vexpand = true };
        var art = new Gtk.Image.from_icon_name ("io.github.techmore.ClaudePantheon") { pixel_size = 96 };
        empty = new Gtk.Label ("Pick a chat from the sidebar or start a new one.") { justify = Gtk.Justification.CENTER, wrap = true };
        empty.add_css_class ("h3");
        var hint = new Gtk.Label ("Ctrl+N starts a new chat, Ctrl+F finds one.");
        hint.add_css_class ("dim-label");
        empty_box.append (art); empty_box.append (empty); empty_box.append (hint);
        list.append (empty_box);
    }

    public void clear () {
        if (render_source != 0) { Source.remove (render_source); render_source = 0; }
        pending = null;
        transcript = null;
        live_label = null; live_group = null;
        tool_rows.remove_all ();
        while (list.get_first_child () != null) list.remove (list.get_first_child ());
    }

    public void show_empty (string text) {
        clear ();
        empty.label = text;
        list.append (empty_box);
    }

    public void show_transcript (Transcript transcript) {
        clear ();
        this.transcript = transcript;
        pending = transcript.messages;
        render_batch ();
        if (pending != null) render_source = Idle.add (render_batch, Priority.DEFAULT_IDLE);
    }

    private bool render_batch () {
        int count = 0;
        while (pending != null && count < 40) {
            append_message (pending.data);
            pending = pending.next;
            count++;
        }
        if (pending == null) { render_source = 0; if (follow_tail) scroll_to_end (); return Source.REMOVE; }
        return Source.CONTINUE;
    }

    public void scroll_to_end () {
        Idle.add (() => { scroller.vadjustment.value = scroller.vadjustment.upper; return Source.REMOVE; });
    }

    public Message append_message (Message message) {
        if (message.role == "user") {
            foreach (var block in message.blocks) {
                if (block.kind == BlockKind.TEXT && block.text.strip () != "") list.append (user_bubble (block.text));
            }
            return message;
        }
        var group = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { halign = Gtk.Align.FILL };
        group.add_css_class ("assistant-turn");
        foreach (var block in message.blocks) {
            if (block.kind == BlockKind.TEXT) { if (block.text.strip () != "") append_markdown (group, block.text); }
            else append_tool (group, block);
        }
        list.append (group);
        return message;
    }

    private Gtk.Widget user_bubble (string text) {
        var label = new Gtk.Label (text) { wrap = true, wrap_mode = Pango.WrapMode.WORD_CHAR, xalign = 0, selectable = true, max_width_chars = 70 };
        label.add_css_class ("user-bubble");
        var wrapper = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { halign = Gtk.Align.END, margin_start = 60 };
        wrapper.append (label);
        return wrapper;
    }

    private void append_markdown (Gtk.Box group, string markdown) {
        foreach (var segment in Markdown.render (markdown)) {
            if (segment.is_code) group.append (code_widget (segment.text, segment.language));
            else {
                var label = new Gtk.Label (segment.text) { use_markup = true, wrap = true, wrap_mode = Pango.WrapMode.WORD_CHAR, xalign = 0, selectable = true, hexpand = true };
                label.add_css_class ("assistant-text");
                group.append (label);
            }
        }
    }

    private void append_tool (Gtk.Box group, Block block) {
        var row = new ToolRow (block);
        if (block.tool_id != "") tool_rows.insert (block.tool_id, row);
        group.append (row);
    }

    public static Gtk.Widget code_widget (string code, string caption) {
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        box.add_css_class ("code-block");
        if (caption != "") {
            var cap = new Gtk.Label (caption) { xalign = 0 };
            cap.add_css_class ("code-caption");
            box.append (cap);
        }
        var label = new Gtk.Label (code) { wrap = true, wrap_mode = Pango.WrapMode.WORD_CHAR, xalign = 0, selectable = true, hexpand = true };
        label.add_css_class ("monospace");
        label.add_css_class ("code-text");
        box.append (label);
        return box;
    }

    /* ---- live streaming support (milestone 2) ---- */

    public void begin_live_turn () {
        live_group = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        live_group.add_css_class ("assistant-turn");
        list.append (live_group);
        live_label = null;
    }

    public void append_user (string text) { list.append (user_bubble (text)); scroll_to_end (); }

    public void live_text_delta (string delta) {
        if (live_group == null) begin_live_turn ();
        if (live_label == null) {
            live_label = new Gtk.Label ("") { wrap = true, wrap_mode = Pango.WrapMode.WORD_CHAR, xalign = 0, selectable = true, hexpand = true };
            live_label.add_css_class ("assistant-text");
            live_group.append (live_label);
        }
        live_label.label = live_label.label + delta;
        scroll_to_end ();
    }

    /* Replaces the raw streamed label with the rendered markdown. */
    public void live_text_done (string full_text) {
        if (live_group == null) begin_live_turn ();
        if (live_label != null) { live_group.remove (live_label); live_label = null; }
        if (full_text.strip () != "") append_markdown (live_group, full_text);
        scroll_to_end ();
    }

    public void live_tool_use (Block block) {
        if (live_group == null) begin_live_turn ();
        append_tool (live_group, block);
        scroll_to_end ();
    }

    public void live_tool_result (string tool_id) {
        var row = tool_rows.lookup (tool_id);
        if (row != null) row.refresh ();
    }

    public void live_status (string text, bool error) {
        var label = new Gtk.Label (text) { xalign = 0, wrap = true };
        label.add_css_class (error ? "error-note" : "dim-label");
        (live_group ?? list).append (label);
        scroll_to_end ();
    }

    public void end_live_turn () { live_group = null; live_label = null; }
}
