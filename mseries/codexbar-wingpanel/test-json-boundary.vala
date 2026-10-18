private void check (string input, bool expected) {
    bool accepted = false;
    try {
        var parser = new Json.Parser ();
        parser.load_from_data (input);
        MSeries.JsonBoundary.validate (parser.get_root ());
        accepted = true;
    } catch (Error e) { }
    assert (accepted == expected);
}
int main (string[] args) {
    Test.init (ref args);
    Test.add_func ("/boundary/optional-defaults", () => {
        var obj = new Json.Object ();
        assert (MSeries.JsonBoundary.text (obj, "missing", "fallback") == "fallback");
        assert (MSeries.JsonBoundary.array (obj, "missing") == null);
        assert (MSeries.JsonBoundary.object_member (obj, "missing") == null);
        obj.set_null_member ("email");
        obj.set_null_member ("busy");
        obj.set_string_member ("minutes", "bad");
        assert (MSeries.JsonBoundary.text (obj, "email", "fallback") == "fallback");
        assert (!MSeries.JsonBoundary.flag (obj, "busy"));
        assert (MSeries.JsonBoundary.integer (obj, "minutes", -1) == -1);
    });
    Test.add_func ("/boundary/valid", () => {
        check ("{\"entries\":[{\"provider\":\"codex\",\"windows\":[{\"remaining\":null}]}],\"future\":42}", true);
        check ("{\"available\":false,\"accounts\":[]}", true);
        check ("{\"resetCredits\":{\"available\":2}}", true);
    });
    Test.add_func ("/boundary/reject-malformed", () => {
        foreach (var input in new string[] {"null", "[]", "{\"accounts\":{}}", "{\"entries\":[null]}",
            "{\"windows\":[3]}", "{\"sessions\":[\"bad\"]}", "{\"periods\":[[]]}",
            "{\"ok\":\"true\"}", "{\"message\":{}}", "{\"email\":false}", "{\"remaining\":\"NaN\"}"}) check (input, false);
    });
    Test.add_func ("/boundary/depth", () => {
        string input = "{}";
        for (int i = 0; i < 30; i++) input = "{\"future\":" + input + "}";
        check (input, false);
    });
    Test.add_func ("/boundary/budget", () => {
        var input = new StringBuilder ("{\"accounts\":[{}");
        for (int i = 0; i < 20001; i++) input.append (",{}");
        input.append ("]}");
        check (input.str, false);
    });
    return Test.run ();
}
