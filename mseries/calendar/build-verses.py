#!/usr/bin/env python3
"""Build daily-verses.tsv and titus-study.tsv from the WEB verse-per-line text.

Usage: build-verses.py path/to/engwebp_vpl.txt path/to/20-PSAengwebp.usfm

Both files come from https://ebible.org/Scriptures/ (engwebp_vpl.zip and
engwebp_usfm.zip). The verse-per-line text runs Psalm headings into verse 1;
the USFM marks them (\\d), so they are split into their own column and shown
as a caption. No words are added, removed or reordered.

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
REFERENCE = re.compile(r"^(.+) (\d+):(\d+)(?:-(\d+))?(?: @([a-z-]+))?$")
SEASONS = {
    "christmas-eve", "christmas", "new-year", "epiphany", "ash-wednesday",
    "palm-sunday", "good-friday", "easter", "pentecost", "thanksgiving",
}
MINIMUM = 366
MARKUP = re.compile(r"\\f .*?\\f\*|\\x .*?\\x\*|\\\+?w ([^|\\]*)(?:\|[^\\]*)?\\\+?w\*|\\[a-z0-9+]+\*?")


def paired(text: str, opening: str, closing: str) -> bool:
    depth = 0
    for i, ch in enumerate(text):
        if ch == opening:
            depth += 1
        elif ch == closing:
            before = text[i - 1] if i else ""
            after = text[i + 1] if i + 1 < len(text) else ""
            # ’ is also the apostrophe (don’t, LORD’s) and plural possessive (brothers’).
            if closing == "’" and before.isalpha() and (after.isalpha() or depth == 0):
                continue
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def trim_edges(text: str) -> str:
    """Drop a quotation mark at the very start or end whose partner lies outside
    the excerpt. Marks inside the passage and all words are kept."""
    for opening, closing in (("“", "”"), ("‘", "’")):
        if paired(text, opening, closing):
            continue
        if text.startswith(opening) and paired(text[1:], opening, closing):
            text = text[1:]
        elif text.endswith(closing) and paired(text[:-1], opening, closing):
            text = text[:-1]
    return text


def psalm_headings(path: Path) -> dict:
    headings, chapter = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("\\c "):
            chapter = line.split()[1]
        elif line.startswith("\\d ") and chapter:
            text = MARKUP.sub(lambda m: m.group(1) or "", line[3:])
            headings[chapter] = " ".join(text.split())
    return headings


def build_study(here: Path, text: dict) -> None:
    """titus-study.tsv: reference, title, insight, reflect, passage. The passage
    marks each verse number as {n}; the overview entry has no passage."""
    blocks, current = [], None
    for line in (here / "titus-study.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if line.startswith("[") and line.endswith("]"):
            current = {"reference": line[1:-1]}
            blocks.append(current)
            continue
        key, _, value = line.partition(": ")
        if current is None or key not in ("title", "insight", "reflect") or not value:
            sys.exit(f"bad study line: {line}")
        current[key] = value.strip()
    rows, covered = [], []
    for block in blocks:
        if any(k not in block for k in ("title", "insight", "reflect")):
            sys.exit(f"incomplete study entry: {block['reference']}")
        passage = ""
        match = REFERENCE.match(block["reference"])
        if match:
            chapter, first, last = match[2], int(match[3]), int(match[4] or match[3])
            verses = []
            for number in range(first, last + 1):
                verse = text.get(f"{BOOKS[match[1]]} {chapter}:{number}")
                if not verse:
                    sys.exit(f"missing study verse: {block['reference']} ({number})")
                verses.append(f"{{{number}}} {verse}")
                covered.append(f"{chapter}:{number}")
            passage = " ".join(verses)
        fields = [block["reference"], block["title"], block["insight"], block["reflect"], passage]
        # Tabs separate columns; braces are reserved for the passage's verse markers.
        if any("\t" in f for f in fields) or any("{" in f for f in fields[:4]):
            sys.exit(f"unexpected tab or brace in {block['reference']}")
        rows.append("\t".join(fields).rstrip("\t"))
    book = [k for k in text if k.startswith("TIT ")]
    if sorted(covered) != sorted(k.split()[1] for k in book) or len(covered) != len(set(covered)):
        sys.exit("study sections must cover every verse of Titus exactly once")
    header = ("# Titus study: World English Bible text (public domain); notes from titus-study.txt\n"
              "# reference, title, insight, reflect, passage ({n} marks verse numbers)\n")
    (here / "titus-study.tsv").write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} study entries covering {len(covered)} verses")


def main() -> int:
    here = Path(__file__).resolve().parent
    text = {}
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        key, _, verse = line.partition(" ")
        key2, _, verse = verse.partition(" ")
        text[f"{key} {key2}"] = verse.strip()

    headings = psalm_headings(Path(sys.argv[2]))
    rows, seen, seasons, trims = [], set(), set(), []
    for line in (here / "verse-references.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = REFERENCE.match(line)
        if not match or match[1] not in BOOKS:
            sys.exit(f"bad reference: {line}")
        season = match[5] or ""
        line = line.split(" @")[0]
        if line in seen:
            sys.exit(f"duplicate reference: {line}")
        seen.add(line)
        if season:
            if season not in SEASONS or season in seasons:
                sys.exit(f"unknown or repeated season: {season}")
            seasons.add(season)
        first = int(match[3])
        last = int(match[4] or first)
        parts = []
        for number in range(first, last + 1):
            verse = text.get(f"{BOOKS[match[1]]} {match[2]}:{number}")
            if not verse:
                sys.exit(f"missing verse text: {line} ({number})")
            parts.append(verse)
        joined = " ".join(parts)
        heading = ""
        if match[1] == "Psalm" and first == 1 and match[2] in headings:
            heading = headings[match[2]]
            if not joined.startswith(heading + " "):
                sys.exit(f"heading does not prefix verse text: {line}")
            joined = joined[len(heading) + 1:]
        trimmed = trim_edges(joined)
        if trimmed != joined:
            trims.append(line)
        joined = trimmed
        if "\t" in joined + heading or "\n" in joined + heading:
            sys.exit(f"unexpected whitespace in {line}")
        # Empty trailing columns are dropped; readers treat them as empty.
        rows.append(f"{line}\t{joined}\t{heading}\t{season}".rstrip("\t"))

    if seasons != SEASONS:
        sys.exit(f"missing seasons: {sorted(SEASONS - seasons)}")
    if len(rows) - len(seasons) < MINIMUM:
        sys.exit(f"{len(rows) - len(seasons)} unreserved references; need at least {MINIMUM}")
    header = ("# Verse of the Day: World English Bible (public domain, https://ebible.org/web/)\n"
              "# reference, text, Psalm heading (may be empty), season (may be empty)\n")
    (here / "daily-verses.tsv").write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} verses; trimmed an edge quotation mark in {len(trims)}")
    build_study(here, text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
