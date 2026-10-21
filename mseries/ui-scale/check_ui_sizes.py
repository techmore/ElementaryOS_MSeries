#!/usr/bin/env python3
"""Fail on hard-coded UI sizes that should come from the M-Series size system (#332).

Scans the size-bearing sources listed in SOURCES and groups what it finds by
(file, rule, matched text). Every group must be listed in ui-size-allowlist.json,
with a reason, and may not occur more often than the allowlist says. New
hard-coded sizes therefore fail; removing one only needs its allowlist entry trimmed.

Rules
  font-abs    font-size in pt or px: use a Granite ramp class or em/rem (SIZE-SYSTEM.md)
  dock-size   dock icon size literals: read `mseries-ui-scale --dock-size MODE`
  icon-px     fixed icon pixel sizes (pixel_size, -gtk-icon-size)
  panel-scale fixed Wingpanel content scale (phase 2 derives it from the ladder)

Patch files are scanned on their added lines only.
"""

import argparse
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ALLOWLIST = HERE / "ui-size-allowlist.json"

# Glob patterns relative to the repository root; EXCLUDE removes files again.
SOURCES = (
    "mseries/display-space/dock_profile.py",
    "mseries/dock-policy/*.sh",
    "mseries/dock-policy/*.py",
    "mseries/dock-trial/dock-trial.py",
    "mseries/work-mode/mseries-work-mode",
    "mseries/dock-taskbar/*.css",
    "mseries/dock-taskbar/*.vala",
    "mseries/patches/dock-taskbar*.patch",
    "mseries/patches/wingpanel-content-scale.patch",
    "mseries/codexbar-wingpanel/*.vala",
    "mseries/codexbar-wingpanel/settings/*.vala",
    "mseries/repobar-wingpanel/*.vala",
    "mseries/repobar-wingpanel/settings/*.vala",
    "mseries/machine-lab/data/*.css",
    "mseries/orchard-incus/orchard_incus/ui.py",
    "mseries/orchard-incus-native/src/*.vala",
    "mseries/battery/mseries-battery-app.py",
    "mseries/screenshot-shelf/mseries-screenshot-shelf",
    "mseries/codexbar-opencode-login.py",
)
EXCLUDE = re.compile(r"(^|/)(test[-_][^/]*|probe/.*)$")

NUMBER = r"\d+(?:\.\d+)?"
RULES = OrderedDict([
    ("font-abs", re.compile(rf"font-size\s*[:=]\s*[\"']?{NUMBER}\s*(?:pt|px)\b")),
    ("dock-size", re.compile(
        r"set_int\s*\(\s*['\"]icon-size['\"]\s*,\s*\d+"          # settings.set_int('icon-size', 40)
        r"|icon-size\s+\d+"                                      # gsettings set ... icon-size 48
        r"|\b\w*ICON_SIZE\s*=\s*\d+"                             # DEFAULT_ICON_SIZE = 48
        r"|\bicon_size=\d+"                                      # shell fallback
        r"|\b\d+ if taskbar else \d+")),                         # Work Mode fallback pair
    ("icon-px", re.compile(rf"pixel_size\s*=\s*\d+|-gtk-icon-size\s*:\s*\d+px")),
    ("panel-scale", re.compile(r"CONTENT_SCALE\s*=\s*[\d.]+f?")),
])


def sources(root):
    seen = set()
    for pattern in SOURCES:
        for path in sorted(root.glob(pattern)):
            relative = path.relative_to(root).as_posix()
            if path.is_file() and relative not in seen and not EXCLUDE.search(relative):
                seen.add(relative)
                yield relative, path


def lines_of(relative, text):
    """Yield the lines worth scanning: added lines for patches, everything otherwise."""
    for line in text.splitlines():
        if relative.endswith(".patch"):
            if not line.startswith("+") or line.startswith("+++"):
                continue
            line = line[1:]
        yield line


def scan(root=REPO):
    """Return Counter {(file, rule, matched text): occurrences}."""
    found = Counter()
    for relative, path in sources(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in lines_of(relative, text):
            for rule, pattern in RULES.items():
                for match in pattern.finditer(line):
                    found[(relative, rule, " ".join(match.group(0).split()))] += 1
    return found


def load_allowlist(path=ALLOWLIST):
    entries = json.loads(Path(path).read_text(encoding="utf-8"))["allowed"]
    allowed = {}
    for entry in entries:
        key = (entry["file"], entry["rule"], entry["match"])
        if key in allowed:
            raise ValueError(f"duplicate allowlist entry: {key}")
        if not entry.get("reason", "").strip():
            raise ValueError(f"allowlist entry needs a reason: {key}")
        if entry["rule"] not in RULES:
            raise ValueError(f"unknown rule {entry['rule']!r} in allowlist: {key}")
        allowed[key] = entry["count"]
    return allowed


def compare(found, allowed):
    """Return (violations, slack): new/excess groups, and allowlist entries that can shrink."""
    violations = [(key, count, allowed.get(key, 0)) for key, count in sorted(found.items())
                  if count > allowed.get(key, 0)]
    slack = [(key, found.get(key, 0), count) for key, count in sorted(allowed.items())
             if found.get(key, 0) < count]
    return violations, slack


def main(argv=None, root=REPO, allowlist=ALLOWLIST):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print every hard-coded size, ignoring the allowlist")
    parser.add_argument("--strict", action="store_true",
                        help="also fail when an allowlist entry is larger than what the sources still contain")
    args = parser.parse_args(argv)

    found = scan(root)
    if args.list:
        for (relative, rule, match), count in sorted(found.items()):
            print(f"{relative}: {rule}: {match} x{count}")
        print(f"{sum(found.values())} hard-coded sizes in {len({k[0] for k in found})} files")
        return 0

    violations, slack = compare(found, load_allowlist(allowlist))
    for (relative, rule, match), count, allowed in violations:
        print(f"{relative}: {rule}: {match!r} x{count} (allowlisted: {allowed}). Use the size system "
              f"(mseries/ui-scale/SIZE-SYSTEM.md) or add a justified entry to {Path(allowlist).name}.",
              file=sys.stderr)
    for (relative, rule, match), count, allowed in slack:
        print(f"{'error' if args.strict else 'note'}: {relative}: {rule}: {match!r} now occurs {count}x; "
              f"trim its allowlist entry from {allowed}.", file=sys.stderr)
    total = sum(found.values())
    if violations or (args.strict and slack):
        print(f"check-ui-sizes: FAIL ({len(violations)} new or increased)", file=sys.stderr)
        return 1
    print(f"check-ui-sizes: ok ({total} hard-coded sizes, all allowlisted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
