#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify frozen chains and reject edits/deletions of already committed freezes."""
import argparse
import json
from pathlib import Path
import re
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
    for path in sorted((frozen / "builds").glob("*.json")):
        manifest = json.loads(path.read_text())
        if manifest.get("kind") != "kernel-build-freeze" or manifest.get("status") != "frozen-build-candidate" or manifest.get("hardware_qualification") is not False or manifest.get("tested_hardware_scopes") != []:
            raise ValueError("build freeze cannot claim hardware qualification")
        if manifest.get("schema") != 1 or manifest.get("frozen") is not True or path.stem != manifest.get("id"):
            raise ValueError("invalid build freeze identity")
        provenance = manifest["provenance"]
        if manifest["kernel_release"] != provenance["kernel_release"] or manifest["profile"] != provenance["profile"] or manifest["source_tree_sha256"] != provenance["source_tree_sha256"]:
            raise ValueError("build freeze and CI provenance differ")
        if manifest["assets"].get(provenance["package"]) != provenance["package_sha256"] or manifest["assets"].get("build.config") != provenance["resolved_config_sha256"] or manifest["assets"].get(f"linux-{manifest['kernel_release']}-source.tar.gz") != provenance["source_sha256"]:
            raise ValueError("build freeze package/config/source digest differs")
        if any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in manifest["assets"].values()):
            raise ValueError("invalid build freeze asset digest")
        verified.append(manifest["id"])
    return verified


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="reviewed base Git commit; existing freeze and pin bytes are immutable")
    args = parser.parse_args()
    print(json.dumps({"verified_freezes": check(base=args.base)}, indent=2))
