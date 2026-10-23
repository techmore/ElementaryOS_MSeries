#!/usr/bin/env python3
"""Recolour Signal Desktop's blue UI accent to the elementary palette.

Signal has no accent setting: its blue ("ultramarine", #2c6bed and a few tints) is compiled into the
stylesheets inside resources/app.asar. This updates only Signal's application stylesheet, startup
window accent, and embedded Signal logo marks. Palette data in chats, avatars, QR art, stickers, and
other images is not edited. Every replacement has the same byte length, so file offsets stay put and
only the per-file integrity hashes in the asar header change (recomputed here).

  signal-accent.py                    apply the current accent (AccountsService, then gsettings)
  signal-accent.py --accent '#68b723' apply a specific colour (#rrggbb or an elementary accent name)
  signal-accent.py --sync             apply the system accent only when it changed
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

# elementary stylesheet palette stops, indexed like AccountsService PrefersAccentColor:
# 100 (light), 300 (dark-mode accent), 500 (system accent), 700 (pressed), 900 (high-contrast fill).
PALETTES = {
    "red":    ("#ff8c82", "#ed5353", "#c6262e", "#a10705", "#7a0000"),
    "orange": ("#ffc27d", "#ffa154", "#f37329", "#cc3b02", "#a62100"),
    "yellow": ("#fff394", "#ffe16b", "#f9c440", "#d48e15", "#ad5f00"),
    "green":  ("#d1ff82", "#9bdb4d", "#68b723", "#3a9104", "#206b00"),
    "mint":   ("#89ffdd", "#43d6b5", "#28bca3", "#0e9a83", "#007367"),
    "blue":   ("#8cd5ff", "#64baff", "#3689e6", "#0d52bf", "#002e99"),
    "purple": ("#e4c6fa", "#cd9ef7", "#a56de2", "#7239b3", "#452981"),
    "pink":   ("#fe9ab8", "#f4679d", "#de3e80", "#bc245d", "#910e38"),
    "brown":  ("#a3907c", "#8a715e", "#715344", "#57392d", "#3d211b"),
    "slate":  ("#95a3ab", "#667885", "#485a6c", "#273445", "#0e141f"),
}
ACCENTS = {name: stops[2] for name, stops in PALETTES.items()}
ACCOUNTS_ORDER = [None, "red", "orange", "yellow", "green", "mint", "blue", "purple", "pink", "brown", "slate"]
GNOME_NAMES = {"teal": "mint", "gray": "slate", "grey": "slate"}

FAMILY = {
    "#2c6bed": "accent",   # legacy UI accent; mapped by CSS role for readable foregrounds
    "#3b45fd": "accent",   # Signal logo / brand accent
    "#1851b4": "pressed",
    "#6191f3": "dark",
    "#abc4f8": "tint-25",
    "#b0c8f9": "tint-30",
    "#d2dffb": "tint-60",
    "#dde7fc": "tint-70",
}


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


# Pale tints: how far the 100 stop is mixed toward white.
TINT_MIX = {"#abc4f8": 0.25, "#b0c8f9": 0.3, "#d2dffb": 0.6, "#dde7fc": 0.7}


def mix_white(value, amount):
    return "#" + "".join(f"{round(int(value[i:i + 2], 16) * (1 - amount) + 255 * amount):02x}" for i in (1, 3, 5))


def build_map(accent):
    palette = palette_for(accent)
    mapping = {
        "#2c6bed": palette["accent"], "#3b45fd": palette["accent"],
        "#1851b4": palette["pressed"], "#6191f3": palette["dark"],
    }
    mapping.update({k: mix_white(palette["light"], v) for k, v in TINT_MIX.items()})
    return mapping


def palette_for(accent):
    for stops in PALETTES.values():
        if stops[2] == accent:
            return dict(zip(("light", "dark", "accent", "pressed", "deep"), stops))
    h, l, s = hex_to_hls(accent)
    return {
        "light": hls_to_hex(h, l + 0.28, s), "dark": hls_to_hex(h, l + 0.12, s),
        "accent": accent, "pressed": hls_to_hex(h, l - 0.16, s),
        "deep": hls_to_hex(h, l - 0.28, s),
    }


def contrast_ratio(foreground, background):
    def luminance(value):
        channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def text_stops(palette):
    # elementary's official palette has a few 300/700 stops that are too muted
    # for ordinary text. Select the nearest brighter/darker semantic stop that
    # retains 4.5:1 contrast in the standard light/dark window surfaces.
    light = palette["deep"]
    dark = palette["dark"] if contrast_ratio(palette["dark"], "#1a1a1a") >= 4.5 else palette["light"]
    return light, dark


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


def _replace(data, old, new):
    old, new = old.encode(), new.encode()
    if len(old) != len(new):
        raise ValueError(f"replacement changes asset width: {old!r} -> {new!r}")
    return data.replace(old, new), data.count(old)


def _oklab_components(hex_colour, widths):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    r, g, b = linear
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    values = (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )
    lightness_width, a_width, b_width = widths
    lightness_decimals = lightness_width - 4
    a_decimals, b_decimals = a_width - 2, b_width - 2
    lightness = f"{values[0] * 100:.{lightness_decimals}f}%"
    def signed(value, decimals):
        sign = "-" if value < 0 else "+"
        return sign + f"{abs(value):.{decimals}f}"[1:]
    components = (lightness, signed(values[1], a_decimals), signed(values[2], b_decimals))
    if tuple(len(part) for part in components) != widths:
        raise ValueError(f"unable to preserve OKLab width for {hex_colour}: {components}")
    return " ".join(components)


OKLAB_SOURCES = (
    ("45.3524% -.0303155 -.305089", "accent"),
    ("74.1051% .0208054 -.133796", "dark"),
    ("43.9994% -.0306593 -.297556", "deep"),
    ("81.455% .0165944 -.0931004", "light"),
)


def patch_stylesheet(data, palette):
    count = 0
    light_text, dark_text = text_stops(palette)

    # Signal's semantic tokens have distinct jobs. Foreground labels and text
    # use readable Pantheon ramp stops; white-on-accent actions and message
    # bubbles use the deep stop, while decorative accents use the standard 500.
    token_map = {
        "--axo-color-brand-primary:#3b45fd": f"--axo-color-brand-primary:{palette['accent']}",
        "--axo-color-label-accent:light-dark(#030ffc,#99a1ff)":
            f"--axo-color-label-accent:light-dark({light_text},{dark_text})",
        "--axo-color-label-accent:light-dark(#000cf3,#b6bcff)":
            f"--axo-color-label-accent:light-dark({palette['deep']},{palette['light']})",
        "--axo-color-fill-accent:light-dark(#4655ff,#5563ff)":
            f"--axo-color-fill-accent:light-dark({palette['deep']},{palette['deep']})",
        "--axo-color-fill-accent:light-dark(#1f31ff,#2536f9)":
            f"--axo-color-fill-accent:light-dark({palette['deep']},{palette['deep']})",
        "--axo-color-fill-accent-pressed:light-dark(#3b4af4,#616eff)":
            f"--axo-color-fill-accent-pressed:light-dark({palette['deep']},{palette['deep']})",
        "--axo-color-fill-accent-pressed:light-dark(#0519ff,#2e3ffa)":
            f"--axo-color-fill-accent-pressed:light-dark({palette['deep']},{palette['deep']})",
        "--axo-color-border-selected:light-dark(#4655ff,#c9ceff)":
            f"--axo-color-border-selected:light-dark({palette['accent']},{palette['dark']})",
        "--axo-color-border-selected:light-dark(#3243ff,#c9ceff)":
            f"--axo-color-border-selected:light-dark({palette['pressed']},{palette['light']})",
        "--axo-color-surface-message-outgoing:light-dark(#2267f5,#2267f5)":
            f"--axo-color-surface-message-outgoing:light-dark({palette['deep']},{palette['deep']})",
        "--axo-color-surface-message-outgoing:light-dark(#0842b9,#0842b9)":
            f"--axo-color-surface-message-outgoing:light-dark({palette['deep']},{palette['deep']})",
        "--axo-color-fill-accent-bright:light-dark(#b2b9ff,#b2b9ff)":
            f"--axo-color-fill-accent-bright:light-dark({palette['light']},{palette['light']})",
        "--axo-color-fill-accent-bright-pressed:light-dark(#a8b0ff,#a8b0ff)":
            f"--axo-color-fill-accent-bright-pressed:light-dark({palette['dark']},{palette['dark']})",
    }
    for old, new in token_map.items():
        data, n = _replace(data, old, new)
        count += n

    # Signal emits Oklab channel tuples for subtle accent tints and disabled
    # labels. Keep their alpha values and asset widths while swapping the hue.
    for source, stop in OKLAB_SOURCES:
        widths = tuple(len(part) for part in source.split())
        target = _oklab_components(palette[stop], widths)
        data, n = _replace(data, source, target)
        count += n

    # Recolour only genuine legacy accent literals in the application CSS.
    # Chat palettes, sticker colors, avatars, and artwork live in other assets.
    matches = list(re.finditer(rb"#(?:2c6bed|3b45fd|6191f3|0552f0|abc4f8|b0c8f9|d2dffb|dde7fc)", data, re.I))
    output = bytearray()
    cursor = 0
    for match in matches:
        original = match.group(0).decode().lower()
        if original == "#3b45fd":
            target = palette["accent"]
        elif original in TINT_MIX:
            target = mix_white(palette["light"], TINT_MIX[original])
        else:
            brace = data.rfind(b"{", 0, match.start())
            selector_start = data.rfind(b"}", 0, brace) + 1
            selector = data[selector_start:brace].lower()
            decl_start = max(data.rfind(b";", 0, match.start()), brace) + 1
            colon = data.find(b":", decl_start, match.start())
            prop = data[decl_start:colon].strip().lower() if colon >= 0 else b""
            end = data.find(b"}", match.end())
            rule = data[brace + 1:end if end >= 0 else len(data)].lower()
            dark = b".dark-theme" in selector
            white_text = any(token in rule for token in (
                b"color:#fff", b"color:#ffffff", b"color:white", b"--tooltip-text-color:#ffffff",
                b"color:var(--axo-color-label-primary-oncolor)",
            ))
            if prop in (b"color", b"--tooltip-text-color"):
                target = dark_text if dark else light_text
            elif original == "#6191f3":
                target = palette["dark"]
            elif prop == b"background-image" or b"module-message__container--outgoing-ultramarine" in selector:
                target = palette["deep"]
            elif prop in (b"background", b"background-color", b"--tooltip-background-color"):
                if white_text or b"checkbox" in selector or b"__button" in selector:
                    target = palette["deep"]
                else:
                    target = palette["dark"] if dark else palette["accent"]
            else:
                target = palette["dark"] if dark else palette["accent"]
        replacement = target.encode()
        if len(replacement) != len(match.group(0)):
            raise ValueError(f"replacement changes CSS width: {match.group(0)!r} -> {replacement!r}")
        output.extend(data[cursor:match.start()])
        output.extend(replacement)
        cursor = match.end()
        count += 1
    output.extend(data[cursor:])
    return bytes(output), count


def recolour_asset(path, data, palette):
    if path in ("stylesheets/manifest.css", "stylesheets/tailwind.css"):
        return patch_stylesheet(data, palette)
    if path == "bundles/main.js":
        # Signal's optional color logo is used as the loading-window background.
        return _replace(data, "e?.signalColors?`#3b45fd`:`#fafafa`",
                        f"e?.signalColors?`{palette['accent']}`:`#fafafa`")
    if path == "bundles/preload/main.js":
        # The uppercase paths here are the embedded Signal logo SVG fills.
        return _replace(data, "#3B45FD", palette["accent"].upper())
    return data, 0


def integrity(data, block_size):
    blocks = [hashlib.sha256(data[i:i + block_size]).hexdigest() for i in range(0, max(len(data), 1), block_size)]
    return {"algorithm": "SHA256", "hash": hashlib.sha256(data).hexdigest(), "blockSize": block_size, "blocks": blocks}


def patch(original, target, accent, write=True):
    palette = palette_for(accent)
    with open(original, "rb") as handle:
        header, raw_header, base = read_header(handle)
        handle.seek(0)
        blob = bytearray(handle.read())
    changed = {}
    for path, entry in walk(header):
        if entry.get("unpacked") or path not in (
            "stylesheets/manifest.css", "stylesheets/tailwind.css",
            "bundles/main.js", "bundles/preload/main.js",
        ):
            continue
        start, size = base + int(entry["offset"]), entry["size"]
        data, count = recolour_asset(path, bytes(blob[start:start + size]), palette)
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
    return build_map(accent), changed


def sync_stamp(accent, asar, original):
    """Invalidate cached theme work when the helper or either archive changes."""
    def identity(path):
        stat = os.stat(path)
        return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]
    with open(__file__, "rb") as helper:
        helper_digest = hashlib.sha256(helper.read()).hexdigest()
    return json.dumps({"accent": accent, "helper": helper_digest,
                       "asar": identity(asar), "original": identity(original)},
                      sort_keys=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--appdir", default=os.environ.get("MSERIES_SIGNAL_APPDIR", DEFAULT_APPDIR))
    parser.add_argument("--accent", help="#rrggbb or an elementary accent name (default: the system accent)")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--sync", action="store_true", help="apply the system accent only when it changed")
    args = parser.parse_args()

    asar = os.path.join(args.appdir, "resources", "app.asar")
    original = asar + ".orig"
    stamp_path = os.path.join(args.appdir, "resources", ".mseries-accent")
    if not os.path.isfile(asar):
        raise SystemExit(f"no Signal install at {args.appdir}")
    if args.restore:
        if os.path.isfile(original):
            os.replace(original, asar)
            try:
                os.unlink(stamp_path)
            except FileNotFoundError:
                pass
            log("restored the original Signal colours")
        return
    if args.sync and args.check:
        raise SystemExit("--sync and --check cannot be used together")
    if not os.path.isfile(original) and not args.check:
        shutil.copy2(asar, original)
    accent = parse_colour(args.accent) if args.accent else system_accent()
    if args.sync:
        try:
            with open(stamp_path, encoding="ascii") as stamp:
                if stamp.read().strip() == sync_stamp(accent, asar, original):
                    log(f"Signal already uses the system accent {accent}")
                    return
        except OSError:
            pass
    mapping, changed = patch(original if os.path.isfile(original) else asar, asar, accent, write=not args.check)
    for source, target in mapping.items():
        log(f"  {source} -> {target}")
    log(f"{'would recolour' if args.check else 'recoloured'} {sum(changed.values())} uses in {len(changed)} files "
        f"to accent {accent}")
    if not args.check:
        with open(stamp_path, "w", encoding="ascii") as stamp:
            stamp.write(sync_stamp(accent, asar, original) + "\n")


if __name__ == "__main__":
    main()
