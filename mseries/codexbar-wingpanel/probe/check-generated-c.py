#!/usr/bin/env python3
"""Reject a valac code-generation shape that reads freed memory.

A nested conditional that mixes an unowned value (a literal) with an owned one
(a call or concatenation), assigned to `var`, makes valac 0.56 emit:

    _tmpA_ = _tmpB_;
    _g_free0 (_tmpB_);
    ... g_strdup (_tmpA_)        /* _tmpA_ now points at freed memory */

That printed garbage reset countdowns and quota captions in the live panel
(fixed 2026-10-19). Write such values with an explicit `string` and if/else.

Usage: check-generated-c.py BUILD_DIR   (scans every *.p/*.c that valac wrote)
"""

import pathlib
import re
import sys

ASSIGN = re.compile(r"^\s*(_tmp\d+_) = (_tmp\d+_);\s*$")


def offences(path: pathlib.Path) -> list[str]:
    found = []
    previous = None
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if line.startswith("#line ") or not line.strip():
            continue  # debug builds interleave source-position directives between statements
        if previous and re.match(r"^\s*_g_free0 \(" + re.escape(previous[1]) + r"\);\s*$", line):
            found.append(f"{path.parent.name}/{path.name}:{previous[2]}: {previous[0]} borrows {previous[1]}, "
                         "which is freed next")
        match = ASSIGN.match(line)
        previous = (match.group(1), match.group(2), number) if match else None
    return found


def main(arguments: list[str]) -> int:
    if len(arguments) != 1:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    sources = sorted(pathlib.Path(arguments[0]).glob("*.p/*.c"))
    if not sources:
        print(f"No valac-generated C under {arguments[0]}", file=sys.stderr)
        return 1
    problems = [problem for source in sources for problem in offences(source)]
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"Checked {len(sources)} generated C files: {len(problems)} borrowed-then-freed temporaries")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
