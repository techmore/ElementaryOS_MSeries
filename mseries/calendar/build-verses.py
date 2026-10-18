#!/usr/bin/env python3
"""Build daily-verses.tsv from verse-references.txt and the WEB verse-per-line text.

Usage: build-verses.py path/to/engwebp_vpl.txt

The World English Bible is public domain (https://ebible.org/web/). Its text is
copied unchanged, as eBible.org asks of anything still called the WEB.
"""
import re
import sys
from pathlib import Path

BOOKS = {
    "Genesis": "GEN", "Exodus": "EXO", "Leviticus": "LEV", "Numbers": "NUM",
    "Deuteronomy": "DEU", "Joshua": "JOS", "Judges": "JDG", "Ruth": "RUT",
    "1 Samuel": "1SA", "2 Samuel": "2SA", "1 Kings": "1KI", "2 Kings": "2KI",
    "1 Chronicles": "1CH", "2 Chronicles": "2CH", "Ezra": "EZR", "Nehemiah": "NEH",
    "Esther": "EST", "Job": "JOB", "Psalm": "PSA", "Proverbs": "PRO",
    "Ecclesiastes": "ECC", "Song of Songs": "SOL", "Isaiah": "ISA", "Jeremiah": "JER",
    "Lamentations": "LAM", "Ezekiel": "EZE", "Daniel": "DAN", "Hosea": "HOS",
    "Joel": "JOE", "Amos": "AMO", "Obadiah": "OBA", "Jonah": "JON", "Micah": "MIC",
    "Nahum": "NAH", "Habakkuk": "HAB", "Zephaniah": "ZEP", "Haggai": "HAG",
    "Zechariah": "ZEC", "Malachi": "MAL", "Matthew": "MAT", "Mark": "MAR",
    "Luke": "LUK", "John": "JOH", "Acts": "ACT", "Romans": "ROM",
    "1 Corinthians": "1CO", "2 Corinthians": "2CO", "Galatians": "GAL",
    "Ephesians": "EPH", "Philippians": "PHI", "Colossians": "COL",
    "1 Thessalonians": "1TH", "2 Thessalonians": "2TH", "1 Timothy": "1TI",
    "2 Timothy": "2TI", "Titus": "TIT", "Philemon": "PHM", "Hebrews": "HEB",
    "James": "JAM", "1 Peter": "1PE", "2 Peter": "2PE", "1 John": "1JO",
    "2 John": "2JO", "3 John": "3JO", "Jude": "JUD", "Revelation": "REV",
}
REFERENCE = re.compile(r"^(.+) (\d+):(\d+)(?:-(\d+))?$")
MINIMUM = 366


def main() -> int:
    here = Path(__file__).resolve().parent
    text = {}
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        key, _, verse = line.partition(" ")
        key2, _, verse = verse.partition(" ")
        text[f"{key} {key2}"] = verse.strip()

    rows, seen = [], set()
    for line in (here / "verse-references.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = REFERENCE.match(line)
        if not match or match[1] not in BOOKS:
            sys.exit(f"bad reference: {line}")
        if line in seen:
            sys.exit(f"duplicate reference: {line}")
        seen.add(line)
        first = int(match[3])
        last = int(match[4] or first)
        parts = []
        for number in range(first, last + 1):
            verse = text.get(f"{BOOKS[match[1]]} {match[2]}:{number}")
            if not verse:
                sys.exit(f"missing verse text: {line} ({number})")
            parts.append(verse)
        joined = " ".join(parts)
        if "\t" in joined or "\n" in joined:
            sys.exit(f"unexpected whitespace in {line}")
        rows.append(f"{line}\t{joined}")

    if len(rows) < MINIMUM:
        sys.exit(f"{len(rows)} references; need at least {MINIMUM}")
    header = "# Verse of the Day: World English Bible (public domain, https://ebible.org/web/)\n"
    (here / "daily-verses.tsv").write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} verses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
