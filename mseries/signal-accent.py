#!/usr/bin/env python3
"""Recolour Signal Desktop's blue UI accent to the elementary OS accent colour.

Signal has no accent setting: its blue ("ultramarine", #2c6bed and a few tints) is compiled into the
stylesheets inside resources/app.asar. This rewrites that colour family in place. Every replacement has
the same byte length, so file offsets stay put and only the per-file integrity hashes in the asar header
change (recomputed here). Chat-colour and avatar palettes are left alone.

  signal-accent.py                    apply the current system accent (AccountsService, then gsettings)
  signal-accent.py --accent '#68b723' apply a specific colour (#rrggbb or an elementary accent name)
  signal-accent.py --restore          put the original app.asar back
  signal-accent.py --check            report what would change, write nothing

The first run keeps the original as app.asar.orig and every later run patches from that copy, so
changing accent never compounds. Restart Signal to see the change.
"""
import argparse
import colorsys
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

DEFAULT_APPDIR = os.path.expanduser("~/.local/lib/signal-desktop-beta")

# elementary OS accents (Granite palette), indexed like io.elementary.pantheon.AccountsService PrefersAccentColor.
ACCENTS = {
    "red": "#c6262e", "orange": "#f37329", "yellow": "#d48e15", "green": "#68b723", "mint": "#28bca3",
    "blue": "#3689e6", "purple": "#a56de2", "pink": "#de3e80", "brown": "#8a715e", "slate": "#667885",
}
ACCOUNTS_ORDER = [None, "red", "orange", "yellow", "green", "mint", "blue", "purple", "pink", "brown", "slate"]
GNOME_NAMES = {"teal": "mint", "gray": "slate", "grey": "slate"}

# Signal's ultramarine family -> elementary Blueberry-style ramp around the accent.
# Each entry: Signal colour, lightness it should take relative to the accent (None = exactly the accent).
REFERENCE = "#2c6bed"
FAMILY = {
    "#2c6bed": None,     # primary: buttons, links, outgoing bubbles, focus rings
    "#3b45fd": None,     # 2024 brand blue: the Signal logo and a few brand accents
    "#1851b4": -0.16,    # pressed / dark variant
    "#6191f3": +0.12,    # dark-theme accent, links on dark
    "#abc4f8": +0.28,    # pale tints (selection, hover backgrounds)
    "#b0c8f9": +0.29,
    "#d2dffb": +0.35,
    "#dde7fc": +0.38,
}
RGB_REFERENCE = re.compile(rb"rgba?\(\s*44\s*,\s*107\s*,\s*237\s*(?=[,)])")


def log(message):
    print(message, file=sys.stderr)


def system_accent():
    try:
        out = subprocess.run(
            ["gdbus", "call", "--system", "--dest", "org.freedesktop.Accounts", "--object-path",
             f"/org/freedesktop/Accounts/User{os.getuid()}", "--method", "org.freedesktop.DBus.Properties.Get",
             "io.elementary.pantheon.AccountsService", "PrefersAccentColor"],
            capture_output=True, text=True, timeout=3).stdout
        index = int(re.search(r"(\d+)", out).group(1))
        if 0 < index < len(ACCOUNTS_ORDER):
            return ACCENTS[ACCOUNTS_ORDER[index]]
    except (OSError, subprocess.SubprocessError, AttributeError, ValueError):
        pass
    try:
        name = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "accent-color"],
                              capture_output=True, text=True, timeout=3).stdout.strip().strip("'")
        return ACCENTS.get(GNOME_NAMES.get(name, name), ACCENTS["blue"])
    except (OSError, subprocess.SubprocessError):
        return ACCENTS["blue"]


def parse_colour(value):
    value = ACCENTS.get(value.lower(), value).lower()
    if not re.fullmatch(r"#[0-9a-f]{6}", value):
        raise SystemExit(f"not a colour or accent name: {value}")
    return value


def hex_to_hls(value):
    return colorsys.rgb_to_hls(*(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)))


def hls_to_hex(h, l, s):
    return "#" + "".join(f"{round(max(0, min(1, c)) * 255):02x}" for c in colorsys.hls_to_rgb(h, max(0, min(1, l)), s))


# Granite palette stops (100 light, 300 dark-theme, 700 pressed) keyed by the 500 accent.
RAMPS = {
    "#c6262e": ("#ff8c82", "#ed5353", "#a10705"), "#f37329": ("#ffc27d", "#ffa154", "#cc3b02"),
    "#d48e15": ("#fff394", "#ffe16b", "#ad5f00"), "#68b723": ("#d1ff82", "#9bdb4d", "#3a9104"),
    "#28bca3": ("#89ffdd", "#43d6b5", "#0e9a83"), "#3689e6": ("#8cd5ff", "#64baff", "#0d52bf"),
    "#a56de2": ("#e4c6fa", "#cd9ef7", "#7239b3"), "#de3e80": ("#fe9ab8", "#f4679d", "#bc245d"),
}
# Pale tints: how far the 100 stop is mixed toward white.
TINT_MIX = {"#abc4f8": 0.25, "#b0c8f9": 0.3, "#d2dffb": 0.6, "#dde7fc": 0.7}


def mix_white(value, amount):
    return "#" + "".join(f"{round(int(value[i:i + 2], 16) * (1 - amount) + 255 * amount):02x}" for i in (1, 3, 5))


def build_map(accent):
    if accent in RAMPS:
        light, dark, pressed = RAMPS[accent]
        mapping = {"#2c6bed": accent, "#1851b4": pressed, "#6191f3": dark}
        mapping.update({k: mix_white(light, v) for k, v in TINT_MIX.items()})
        return mapping
    h, l, s = hex_to_hls(accent)
    mapping = {}
    for source, offset in FAMILY.items():
        mapping[source] = accent if offset is None else hls_to_hex(h, l + offset, s)
    return mapping


def read_header(handle):
    _, header_size, _, json_size = struct.unpack("<4I", handle.read(16))
    raw = handle.read(json_size)
    return json.loads(raw), raw, 8 + header_size


def walk(node, prefix=""):
    for name, entry in node.get("files", {}).items():
        path = prefix + name
        if "files" in entry:
            yield from walk(entry, path + "/")
        else:
            yield path, entry


def recolour(data, mapping, rgb):
    count = 0
    for source, target in mapping.items():
        for variant in (source, source.upper()):
            n = data.count(variant.encode())
            if n:
                data = data.replace(variant.encode(), target.encode())
                count += n

    def rgb_sub(match):
        # Same width as the original so offsets never move: pad inside the parenthesis.
        head = match.group(0)[:match.group(0).index(b"(") + 1]
        body = rgb.encode()
        width = len(match.group(0)) - len(head)
        return head + body.rjust(width) if len(body) <= width else match.group(0)

    data, n = RGB_REFERENCE.subn(rgb_sub, data)
    return data, count + n


def integrity(data, block_size):
    blocks = [hashlib.sha256(data[i:i + block_size]).hexdigest() for i in range(0, max(len(data), 1), block_size)]
    return {"algorithm": "SHA256", "hash": hashlib.sha256(data).hexdigest(), "blockSize": block_size, "blocks": blocks}


def patch(original, target, accent, write=True):
    mapping = build_map(accent)
    r, g, b = (int(accent[i:i + 2], 16) for i in (1, 3, 5))
    rgb = f"{r},{g},{b}"
    with open(original, "rb") as handle:
        header, raw_header, base = read_header(handle)
        handle.seek(0)
        blob = bytearray(handle.read())
    changed = {}
    for path, entry in walk(header):
        if entry.get("unpacked") or not path.endswith((".css", ".js", ".html", ".svg")):
            continue
        start, size = base + int(entry["offset"]), entry["size"]
        data, count = recolour(bytes(blob[start:start + size]), mapping, rgb)
        if count:
            assert len(data) == size, path
            blob[start:start + size] = data
            if "integrity" in entry:
                entry["integrity"] = integrity(data, entry["integrity"].get("blockSize", 4 * 1024 * 1024))
            changed[path] = count
    new_header = json.dumps(header, separators=(",", ":")).encode()
    if len(new_header) != len(raw_header):
        raise SystemExit("asar header changed size; refusing to write (unexpected header layout)")
    blob[16:16 + len(raw_header)] = new_header
    if write:
        tmp = target + ".tmp"
        with open(tmp, "wb") as handle:
            handle.write(blob)
        shutil.copymode(original, tmp)
        os.replace(tmp, target)
    return mapping, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--appdir", default=os.environ.get("MSERIES_SIGNAL_APPDIR", DEFAULT_APPDIR))
    parser.add_argument("--accent", help="#rrggbb or an elementary accent name (default: the system accent)")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    asar = os.path.join(args.appdir, "resources", "app.asar")
    original = asar + ".orig"
    if not os.path.isfile(asar):
        raise SystemExit(f"no Signal install at {args.appdir}")
    if args.restore:
        if os.path.isfile(original):
            os.replace(original, asar)
            log("restored the original Signal colours")
        return
    if not os.path.isfile(original) and not args.check:
        shutil.copy2(asar, original)
    accent = parse_colour(args.accent) if args.accent else system_accent()
    mapping, changed = patch(original if os.path.isfile(original) else asar, asar, accent, write=not args.check)
    for source, target in mapping.items():
        log(f"  {source} -> {target}")
    log(f"{'would recolour' if args.check else 'recoloured'} {sum(changed.values())} uses in {len(changed)} files "
        f"to accent {accent}")
    with open(os.path.join(args.appdir, "resources", ".mseries-accent"), "w") if not args.check else open(os.devnull, "w") as stamp:
        stamp.write(accent + "\n")


if __name__ == "__main__":
    main()
