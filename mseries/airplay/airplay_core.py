"""Pure logic for choosing which AirPlay (RAOP) receivers are active.

PipeWire's RAOP discovery creates one sink per receiver on the network. Playing to several at
once is done by one combine-stream sink ("AirPlay Group") whose members are the receivers the
user switched on. No I/O here except the small state file helpers, so it is unit-testable.
"""
import json, os, re

GROUP_NODE_NAME = "mseries_airplay_group"
GROUP_DESCRIPTION = "AirPlay Group"
GROUP_UNIT = "mseries-airplay-group"
COMBINE_MODULE = "libpipewire-module-combine-stream"
STATE_PATH = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                          "mseries", "airplay.json")
_RAOP = re.compile(r"^raop_sink\.(.+?)\.local\.[0-9a-fA-F.:]+\.\d+$")


def destinations(pw_dump):
    """AirPlay receivers found in a pw-dump document, sorted by name.
    key is the mDNS host name (stable across IP changes)."""
    out = []
    for obj in pw_dump:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        props = (obj.get("info") or {}).get("props") or {}
        if props.get("media.class") != "Audio/Sink":
            continue
        m = _RAOP.match(props.get("node.name", ""))
        if not m:
            continue
        out.append({"key": m.group(1), "node_id": obj["id"], "node_name": props["node.name"],
                    "name": props.get("node.description") or m.group(1),
                    "state": (obj["info"].get("state") or "")})
    return sorted(out, key=lambda d: (d["name"].lower(), d["key"]))


def group_sink(pw_dump):
    for obj in pw_dump:
        props = (obj.get("info") or {}).get("props") or {}
        if obj.get("type") == "PipeWire:Interface:Node" and props.get("node.name") == GROUP_NODE_NAME:
            return obj["id"]
    return None


def group_members(pw_dump):
    """Keys of receivers whose sink currently has a link from the group sink's output."""
    sink = group_sink(pw_dump)
    if sink is None:
        return set()
    by_id = {d["node_id"]: d["key"] for d in destinations(pw_dump)}
    stream_nodes = set()
    for obj in pw_dump:
        props = (obj.get("info") or {}).get("props") or {}
        if obj.get("type") == "PipeWire:Interface:Node" and props.get("node.name", "").startswith("output." + GROUP_NODE_NAME):
            stream_nodes.add(obj["id"])
    members = set()
    for obj in pw_dump:
        if obj.get("type") != "PipeWire:Interface:Link":
            continue
        p = (obj.get("info") or {})
        if p.get("output-node-id") in stream_nodes and p.get("input-node-id") in by_id:
            members.add(by_id[p["input-node-id"]])
    return members


def module_args(enabled_keys):
    """SPA-JSON argument string for loading the combine-stream module with these members."""
    rules = ",\n".join(
        '      { matches = [ { media.class = "Audio/Sink" node.name = "~^raop_sink\\\\.%s\\\\.local\\\\..*" } ]\n'
        '        actions = { create-stream = { combine.audio.position = [ FL FR ] } } }' % re.escape(k).replace("\\", "\\\\")
        for k in sorted(set(enabled_keys)))
    return ('{\n  node.name = "%s"\n  node.description = "%s"\n  combine.mode = sink\n'
            '  combine.latency-compensate = false\n'
            '  node.virtual = true\n  media.class = Audio/Sink\n  audio.position = [ FL FR ]\n'
            '  stream.rules = [\n%s\n  ]\n}' % (GROUP_NODE_NAME, GROUP_DESCRIPTION, rules))


def client_conf(enabled_keys):
    """pipewire.conf for a small client process that owns the group sink. (A module loaded with
    `pw-cli load-module` lives in the pw-cli process and vanishes when it exits, so the group runs
    as its own long-lived client under a transient systemd user unit.)"""
    return (
        "context.properties = { log.level = 2 }\n"
        "context.spa-libs = {\n  audio.convert.* = audioconvert/libspa-audioconvert\n"
        "  support.* = support/libspa-support\n}\n"
        "context.modules = [\n"
        "  { name = libpipewire-module-rt args = { nice.level = -11 } flags = [ ifexists nofail ] }\n"
        "  { name = libpipewire-module-protocol-native }\n"
        "  { name = libpipewire-module-client-node }\n"
        "  { name = libpipewire-module-adapter }\n"
        "  { name = %s args = %s }\n]\n" % (COMBINE_MODULE, module_args(enabled_keys)))


def load_state(path=STATE_PATH):
    try:
        with open(path) as f:
            data = json.load(f)
        return [k for k in data.get("enabled", []) if isinstance(k, str)]
    except (OSError, ValueError, AttributeError):
        return []


def save_state(enabled_keys, path=STATE_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"enabled": sorted(set(enabled_keys))}, f, indent=1)
    os.replace(tmp, path)


def toggle(enabled_keys, key):
    s = set(enabled_keys)
    s.symmetric_difference_update({key})
    return sorted(s)
