/* Run by test_audio_output_model.sh. */
int failures = 0;
void check (bool ok, string what) {
    if (!ok) { failures++; stderr.printf ("FAIL: %s\n", what); } else { print ("ok: %s\n", what); }
}
string load (string path) {
    string text;
    try { FileUtils.get_contents (path, out text); } catch (Error e) { Process.exit (2); }
    return text;
}
int main (string[] args) {
    try {
        var builtin = QuickSettings.AudioOutputModel.parse (load (args[1] + "/pw-dump-builtin.json"));
        check (builtin.length == 1, "unplugged headphone jack hidden (%u outputs)".printf (builtin.length));
        foreach (var o in builtin) {
            check (o.transport == QuickSettings.Transport.BUILTIN, "%s is Built-in".printf (o.description));
            check (o.id != 61, "headphone jack is not listed");
            if (o.id == 81) check (o.icon_name == "audio-speakers-symbolic", "speaker filter-chain icon");
        }

        var mixed = QuickSettings.AudioOutputModel.parse (load (args[1] + "/pw-dump-mixed.json"));
        check (mixed.length == 5, "null sink skipped, five outputs (%u)".printf (mixed.length));
        QuickSettings.AudioOutputInfo? bt = null, air = null, usb = null, hdmi = null;
        foreach (var o in mixed) {
            if (o.id == 90) bt = o;
            if (o.id == 91) air = o;
            if (o.id == 92) usb = o;
            if (o.id == 93) hdmi = o;
        }
        check (bt != null && bt.transport == QuickSettings.Transport.BLUETOOTH, "Bluetooth classified");
        check (bt != null && bt.icon_name == "audio-headphones-symbolic", "Bluetooth headphones icon");
        check (air != null && air.transport == QuickSettings.Transport.AIRPLAY, "AirPlay classified");
        check (usb != null && usb.transport == QuickSettings.Transport.USB, "USB classified");
        check (hdmi != null && hdmi.transport == QuickSettings.Transport.DISPLAY, "Display classified");
        check (mixed[0].transport == QuickSettings.Transport.BUILTIN && mixed[mixed.length - 1].transport != QuickSettings.Transport.BUILTIN,
            "sorted built-in first");
        int defaults = 0;
        foreach (var o in mixed) if (o.is_default) defaults++;
        check (defaults == 1, "exactly one default (%d)".printf (defaults));
        check (QuickSettings.AudioOutputModel.parse ("[]").length == 0, "empty graph");
    } catch (Error e) {
        failures++; stderr.printf ("error: %s\n", e.message);
    }
    return failures == 0 ? 0 : 1;
}
