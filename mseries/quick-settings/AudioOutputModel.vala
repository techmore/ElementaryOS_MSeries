/* SPDX-License-Identifier: GPL-3.0-or-later
 * Turns a `pw-dump` document into the list of sound outputs the Quick Settings menu shows, each
 * labelled with how it is connected (built-in, Bluetooth, AirPlay, USB, display). No GTK here, so
 * mseries/audio/test_audio_output_model.sh can run it against fixtures. */
public enum QuickSettings.Transport {
    BUILTIN,
    BLUETOOTH,
    AIRPLAY,
    USB,
    DISPLAY,
    OTHER;

    public string to_label () {
        switch (this) {
            case BUILTIN: return _("Built-in");
            case BLUETOOTH: return _("Bluetooth");
            case AIRPLAY: return _("AirPlay");
            case USB: return _("USB");
            case DISPLAY: return _("HDMI / DisplayPort");
            default: return _("Other");
        }
    }
}

public class QuickSettings.AudioOutputInfo : Object {
    public uint id { get; set; }
    public string node_name { get; set; default = ""; }
    public string description { get; set; default = ""; }
    public Transport transport { get; set; default = Transport.OTHER; }
    public string icon_name { get; set; default = "audio-speakers-symbolic"; }
    public bool is_default { get; set; default = false; }
}

namespace QuickSettings.AudioOutputModel {
    private string? str (Json.Object? props, string key) {
        if (props == null || !props.has_member (key)) {
            return null;
        }
        var node = props.get_member (key);
        if (node.get_node_type () != Json.NodeType.VALUE) {
            return null;
        }
        // strdup_contents () would quote strings, so only non-strings (booleans, numbers) use it.
        if (node.get_value_type () == typeof (string)) {
            return node.get_string ();
        }
        return node.get_value ().strdup_contents ();
    }

    public Transport classify (Json.Object props) {
        var node_name = str (props, "node.name") ?? "";
        var api = str (props, "device.api") ?? "";
        var bus = str (props, "device.bus") ?? "";
        var text = ((str (props, "alsa.card_name") ?? "") + " " + (str (props, "api.alsa.path") ?? "") + " "
            + (str (props, "device.profile.name") ?? "") + " " + node_name).down ();

        if (api == "bluez5" || node_name.has_prefix ("bluez_output") || props.has_member ("api.bluez5.address")) {
            return Transport.BLUETOOTH;
        }
        if (node_name.has_prefix ("raop_sink") || props.has_member ("raop.ip")) {
            return Transport.AIRPLAY;
        }
        if (text.contains ("hdmi") || text.contains ("displayport") || text.contains ("dp-")) {
            return Transport.DISPLAY;
        }
        if (bus == "usb") {
            return Transport.USB;
        }
        // asahi-audio hides the raw speaker array behind a filter-chain sink named audio_effect.*.
        if (api == "alsa" || node_name.has_prefix ("audio_effect.") || api == "dsp") {
            return Transport.BUILTIN;
        }
        return Transport.OTHER;
    }

    private string icon_for (Json.Object props, Transport transport) {
        var form = (str (props, "device.form-factor") ?? "").down ();
        var icon = (str (props, "device.icon-name") ?? "").down ();
        var name = (str (props, "node.name") ?? "").down ();
        if (form == "headphone" || form == "headset" || form == "hands-free" || icon.contains ("headphone")
            || icon.contains ("headset") || name.contains("headphones")) {
            return "audio-headphones-symbolic";
        }
        if (transport == Transport.DISPLAY) {
            return "video-display-symbolic";
        }
        return "audio-speakers-symbolic";
    }

    private void collect_unplugged (Json.Object device, GenericSet<string> unplugged) {
        var info = device.get_object_member ("info");
        if (info == null || !info.has_member ("params")) return;
        var params = info.get_object_member ("params");
        if (!params.has_member ("EnumRoute")) return;

        var seen = new GenericSet<string> (str_hash, str_equal);
        var available = new GenericSet<string> (str_hash, str_equal);
        foreach (var element in params.get_array_member ("EnumRoute").get_elements ()) {
            var route = element.get_object ();
            if (route == null || route.get_string_member_with_default ("direction", "") != "Output"
                || !route.has_member ("devices")) continue;
            foreach (var index in route.get_array_member ("devices").get_elements ()) {
                var key = "%lld:%lld".printf (device.get_int_member_with_default ("id", -1), index.get_int ());
                seen.add (key);
                if (route.get_string_member_with_default ("available", "unknown") != "no") {
                    available.add (key);
                }
            }
        }
        seen.foreach ((key) => {
            if (!available.contains (key)) unplugged.add (key);
        });
    }

    /* Real outputs only: hardware, Bluetooth, AirPlay and the speaker filter chain. Other
     * virtual sinks (null sinks, loopbacks) are skipped. */
    public GenericArray<AudioOutputInfo> parse (string json) throws Error {
        var parser = new Json.Parser ();
        parser.load_from_data (json);
        var root = parser.get_root ();
        var outputs = new GenericArray<AudioOutputInfo> ();
        var sorted = new List<AudioOutputInfo> ();
        if (root == null || root.get_node_type () != Json.NodeType.ARRAY) {
            return outputs;
        }

        string? default_name = null;
        // Sound-card outputs whose every route reports "no" (a headphone jack with nothing in it).
        // WirePlumber will not make such a sink the default, so listing it would only mislead.
        var unplugged = new GenericSet<string> (str_hash, str_equal);
        foreach (var element in root.get_array ().get_elements ()) {
            var object = element.get_object ();
            if (object == null) continue;
            var type = object.get_string_member_with_default ("type", "");
            if (type == "PipeWire:Interface:Device") {
                collect_unplugged (object, unplugged);
            }
            if (type == "PipeWire:Interface:Metadata" && object.has_member ("metadata")) {
                foreach (var entry in object.get_array_member ("metadata").get_elements ()) {
                    var item = entry.get_object ();
                    if (item == null || item.get_string_member_with_default ("key", "") != "default.audio.sink") continue;
                    var value = item.get_member ("value");
                    if (value != null && value.get_node_type () == Json.NodeType.OBJECT) {
                        default_name = value.get_object ().get_string_member_with_default ("name", "");
                    }
                }
            }
        }

        foreach (var element in root.get_array ().get_elements ()) {
            var object = element.get_object ();
            if (object == null || object.get_string_member_with_default ("type", "") != "PipeWire:Interface:Node") continue;
            var info = object.get_object_member ("info");
            if (info == null || !info.has_member ("props")) continue;
            var props = info.get_object_member ("props");
            if (str (props, "media.class") != "Audio/Sink") continue;

            var node_name = str (props, "node.name") ?? "";
            var route_key = "%s:%s".printf (str (props, "device.id") ?? "-", str (props, "card.profile.device") ?? "-");
            if (unplugged.contains (route_key)) continue;
            var transport = classify (props);
            if (transport == Transport.OTHER && str (props, "node.virtual") == "true") continue;

            var output = new AudioOutputInfo () {
                id = (uint) object.get_int_member_with_default ("id", 0),
                node_name = node_name,
                description = str (props, "node.description") ?? str (props, "node.nick") ?? node_name,
                transport = transport,
                is_default = node_name == default_name
            };
            output.icon_name = icon_for (props, transport);
            sorted.insert_sorted (output, (a, b) => {
                if (a.transport != b.transport) return (int) a.transport - (int) b.transport;
                return strcmp (a.description, b.description);
            });
        }

        foreach (var output in sorted) {
            outputs.add (output);
        }
        return outputs;
    }
}
