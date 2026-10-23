// Keep cloud-init and other multiline Incus values intact in the line editor.
public class ConfigText : Object {
    public static string render (Json.Object values, bool omit_volatile = false) {
        var text = new StringBuilder ();
        foreach (var key in values.get_members ()) {
            if (omit_volatile && key.has_prefix ("volatile.")) continue;
            var node = new Json.Node (Json.NodeType.VALUE);
            node.set_string (values.get_string_member (key));
            var generator = new Json.Generator (); generator.set_root (node);
            text.append (key + "=" + generator.to_data (null) + "\n");
        }
        return text.str;
    }

    public static Json.Object parse (string text, bool reject_volatile = false) throws Error {
        var values = new Json.Object ();
        foreach (var line in text.split ("\n")) {
            if (line.strip () == "") continue;
            int separator = line.index_of_char ('=');
            if (separator <= 0) throw new IOError.INVALID_ARGUMENT ("Use key=value on every line.");
            var key = line.substring (0, separator).strip ();
            if (key == "" || values.has_member (key)) throw new IOError.INVALID_ARGUMENT ("Keys must be nonempty and unique: " + key);
            if (reject_volatile && key.has_prefix ("volatile.")) throw new IOError.INVALID_ARGUMENT ("Volatile settings are managed by Incus.");
            var value = line.substring (separator + 1);
            if (value.strip ().has_prefix ("\"")) {
                try {
                    var parser = new Json.Parser (); parser.load_from_data (value);
                    var node = parser.get_root ();
                    if (node.get_node_type () != Json.NodeType.VALUE || node.get_value_type () != typeof (string))
                        throw new IOError.INVALID_ARGUMENT ("Expected a quoted string.");
                    value = node.get_string ();
                } catch (Error e) { throw new IOError.INVALID_ARGUMENT ("Invalid quoted value for " + key + ". Use JSON string escapes for quotes and newlines."); }
            }
            values.set_string_member (key, value);
        }
        return values;
    }
}
