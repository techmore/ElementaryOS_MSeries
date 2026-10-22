/* A deliberately small Markdown renderer: fenced code blocks become separate
 * widgets; paragraphs get Pango markup for bold, italics, inline code,
 * headings and bullets. Enough for chat, cheap to run. */

public class MarkdownSegment : Object {
    public bool is_code;
    public string language = "";
    public string text;   // code: raw; prose: Pango markup
}

public class Markdown : Object {
    private static Regex? bold;
    private static Regex? italics;
    private static Regex? code;
    private static Regex? link;

    private static void ensure () {
        if (bold != null) return;
        try {
            bold = new Regex ("\\*\\*(.+?)\\*\\*");
            italics = new Regex ("(?<![\\w*])[*_]([^*_\\n]+?)[*_](?![\\w*])");
            code = new Regex ("`([^`\\n]+)`");
            link = new Regex ("\\[([^\\]]+)\\]\\(([^)\\s]+)\\)");
        } catch (Error e) { }
    }

    public static List<MarkdownSegment> render (string source) {
        ensure ();
        var segments = new List<MarkdownSegment> ();
        var prose = new StringBuilder ();
        StringBuilder? fenced = null;
        string language = "";
        foreach (var raw_line in source.split ("\n")) {
            var line = raw_line.chomp ();
            var trimmed = line.strip ();
            if (trimmed.has_prefix ("```")) {
                if (fenced == null) {
                    flush_prose (ref segments, prose);
                    fenced = new StringBuilder ();
                    language = trimmed.substring (3).strip ();
                } else {
                    segments.append (new MarkdownSegment () { is_code = true, language = language, text = fenced.str.chomp () });
                    fenced = null;
                }
                continue;
            }
            if (fenced != null) { fenced.append (line); fenced.append_c ('\n'); continue; }
            prose.append (format_line (line));
            prose.append_c ('\n');
        }
        if (fenced != null) segments.append (new MarkdownSegment () { is_code = true, language = language, text = fenced.str.chomp () });
        flush_prose (ref segments, prose);
        return segments;
    }

    private static void flush_prose (ref List<MarkdownSegment> segments, StringBuilder prose) {
        var text = prose.str.strip ();
        prose.truncate (0);
        if (text == "") return;
        // Collapse runs of more than one blank line.
        while (text.contains ("\n\n\n")) text = text.replace ("\n\n\n", "\n\n");
        segments.append (new MarkdownSegment () { is_code = false, text = text });
    }

    public static string format_line (string line) {
        var text = line;
        var stripped = text.strip ();
        string prefix = "";
        string open = "", close = "";
        if (stripped.has_prefix ("#")) {
            int level = 0;
            while (level < stripped.length && stripped[level] == '#') level++;
            if (level <= 6 && level < stripped.length && stripped[level] == ' ') {
                text = stripped.substring (level).strip ();
                open = level == 1 ? "<span weight=\"bold\" size=\"x-large\">" : level == 2 ? "<span weight=\"bold\" size=\"large\">" : "<span weight=\"bold\">";
                close = "</span>";
            }
        } else if (stripped.has_prefix ("- ") || stripped.has_prefix ("* ") || stripped.has_prefix ("• ")) {
            int indent = (text.length - text.chug ().length) / 2;
            prefix = string.nfill (indent * 4, ' ') + "  •  ";
            text = stripped.substring (2);
        } else if (stripped.has_prefix ("> ")) {
            prefix = "  ";
            open = "<span alpha=\"70%\" style=\"italic\">"; close = "</span>";
            text = stripped.substring (2);
        } else if (stripped.length > 2 && stripped[0].isdigit ()) {
            int dot = stripped.index_of (". ");
            if (dot > 0 && dot < 4) {
                bool numeric = true;
                for (int i = 0; i < dot; i++) if (!stripped[i].isdigit ()) numeric = false;
                if (numeric) { prefix = "  " + stripped.substring (0, dot + 1) + " "; text = stripped.substring (dot + 2); }
            }
        }
        if (stripped == "---" || stripped == "***") return "<span alpha=\"35%\">────────────</span>";
        var escaped = Markup.escape_text (text);
        try {
            escaped = code.replace (escaped, -1, 0, "<tt>\\1</tt>");
            escaped = bold.replace (escaped, -1, 0, "<b>\\1</b>");
            escaped = italics.replace (escaped, -1, 0, "<i>\\1</i>");
            escaped = link.replace (escaped, -1, 0, "<a href=\"\\2\">\\1</a>");
        } catch (Error e) { }
        return prefix + open + escaped + close;
    }
}
