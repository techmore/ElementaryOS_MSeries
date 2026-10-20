#!/usr/bin/env python3
"""Check that the verse and study data bundled in the datetime patch match the
files in this directory. The patch adds them as new files under data/; this
reads them back out of the patch, so it runs offline.

Usage: check-bundled-data.py [path/to/datetime-agenda-tabs.patch]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLED = ("daily-verses.tsv", "titus-study.tsv")


def new_files(patch: str) -> dict:
    files, current, lines = {}, None, []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            if current:
                files[current] = lines
            current, lines = None, []
            name = line.split(" b/", 1)[1]
            if name.startswith("data/") and name[5:] in BUNDLED:
                current = name[5:]
        elif current and line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
        elif current and line.startswith("-") and not line.startswith("---"):
            sys.exit(f"{current} is modified, not added, in the patch")
    if current:
        files[current] = lines
    return files


def main() -> int:
    patch = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "patches" / "datetime-agenda-tabs.patch"
    bundled = new_files(patch.read_text(encoding="utf-8"))
    failed = False
    for name in BUNDLED:
        source = (HERE / name).read_text(encoding="utf-8").splitlines()
        if name not in bundled:
            print(f"FAIL {name}: not added by {patch.name}")
            failed = True
        elif bundled[name] != source:
            print(f"FAIL {name}: patch copy differs from mseries/calendar/{name}; regenerate the patch")
            failed = True
        else:
            print(f"ok   {name}: {len(source)} lines match")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
