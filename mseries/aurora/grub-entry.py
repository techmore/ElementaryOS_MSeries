#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Update only the Aurora 20 GRUB block, retaining legacy and unrelated entries."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import tempfile

BEGIN = "# BEGIN elementary aurora20 (managed)"
END = "# END elementary aurora20"


def update(text, replacement):
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise ValueError("malformed Aurora 20 block; refusing to edit GRUB")
    if BEGIN in text:
        before, rest = text.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        return before + replacement + after
    return text.rstrip("\n") + "\n\n" + replacement + "\n" if replacement else text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    block = "" if args.remove else sys.stdin.read().strip()
    if not args.remove and (not block.startswith(BEGIN + "\n") or not block.endswith("\n" + END)):
        raise ValueError("replacement is not a managed Aurora 20 entry")
    original = args.file.read_text() if args.file.exists() else ""
    result = update(original, block)
    if args.apply and result != original:
        args.file.parent.mkdir(parents=True, exist_ok=True)
        if args.file.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            shutil.copy2(args.file, args.file.with_name(args.file.name + ".pre-aurora20." + stamp))
        with tempfile.NamedTemporaryFile(mode="w", dir=args.file.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(result)
        try:
            shutil.copystat(args.file, temporary) if args.file.exists() else temporary.chmod(0o644)
            temporary.replace(args.file)
        finally:
            temporary.unlink(missing_ok=True)
    elif not args.apply:
        print(result, end="")


if __name__ == "__main__":
    main()
