#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify frozen chains and reject edits/deletions of already committed freezes."""
import argparse
import json
from pathlib import Path
import subprocess

import qualification as q

HERE = Path(__file__).resolve().parent


def check(directory=HERE, base=None):
    directory = Path(directory).resolve()
    frozen = directory / "frozen"
    if base:
        repo = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=directory, text=True).strip())
        prefix = str(frozen.relative_to(repo))
        names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", base, "--", prefix], cwd=repo, text=True).splitlines()
        for name in names:
            if not name.endswith(".json"):
                continue
            previous = subprocess.check_output(["git", "show", f"{base}:{name}"], cwd=repo)
            path = repo / name
            if not path.is_file() or path.read_bytes() != previous:
                raise ValueError(f"existing freeze/pins cannot change: {name}; use a new release ID")
    verified = []
    for path in sorted(frozen.glob("*.json")):
        manifest = json.loads(path.read_text())
        # A fixed snapshot keeps historical freezes verifiable when the active
        # release.json is later advanced to another upstream kernel.
        pin_files = [directory / "release.json", *sorted((frozen / "pins").glob("*.json"))]
        pins = next((p for p in pin_files if p.is_file() and q.digest(p) == manifest["pins_sha256"]), None)
        if pins is None:
            raise ValueError(f"frozen pin snapshot is missing: {path.name}")
        evidence = [directory / "hardware-tests" / item["file"] for item in manifest["evidence"]]
        if any(p.parent != directory / "hardware-tests" for p in evidence):
            raise ValueError("evidence path escapes hardware-tests")
        q.verify(path, pins, evidence)
        verified.append(manifest["id"])
    return verified


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="reviewed base Git commit; existing freeze and pin bytes are immutable")
    args = parser.parse_args()
    print(json.dumps({"verified_freezes": check(base=args.base)}, indent=2))
