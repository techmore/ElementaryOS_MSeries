#!/usr/bin/env python3
"""Compare synthetic profile package sets with checksum-pinned Germinate 2.49.

Requires system Python with python3-apt. This checks the union of required and
recommended runtime package membership, not output reasons or installability.
No Elementary seed content or upstream implementation is vendored.
"""

import argparse
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=lambda value: Path(value).resolve())
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    manifest = json.loads((HERE.parent / "elementary-build-inputs.json").read_text())
    reference = next(item for item in manifest["reference_projects"] if item["id"] == "ubuntu/germinate")
    if args.archive:
        archive = args.archive.read_bytes()
    else:
        with urllib.request.urlopen(reference["source_archive"], timeout=60) as response:
            archive = response.read(8 * 1024 * 1024 + 1)
    if hashlib.sha256(archive).hexdigest() != reference["source_archive_sha256"]:
        raise RuntimeError("Germinate reference archive SHA-256 mismatch")

    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="mseries-seed-parity-") as temporary:
        root = Path(temporary)
        source_root = root / "reference"
        module_root = source_root / "germinate"
        module_root.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:xz") as source:
            for member in source.getmembers():
                if (member.isfile() and member.name.startswith("work/germinate/")
                        and member.name.count("/") == 2 and member.name.endswith(".py")):
                    stream = source.extractfile(member)
                    if stream is None:
                        raise RuntimeError(f"missing reference module {member.name}")
                    (module_root / Path(member.name).name).write_bytes(stream.read())
        sys.path.insert(0, str(source_root))
        from germinate.archive import IndexType
        from germinate.germinator import Germinator
        from germinate.seeds import SeedStructure

        class SyntheticArchive:
            def __init__(self, packages):
                self.packages = packages

            def sections(self):
                binaries = {}
                for package in self.packages:
                    binaries.setdefault(package.get("Source", package["Package"]), []).append(package["Package"])
                for name, names in binaries.items():
                    yield IndexType.SOURCES, {"Package": name, "Version": "1", "Binary": ", ".join(names)}
                for package in self.packages:
                    yield IndexType.PACKAGES, package

        base_packages = [
            {"Package": "app", "Depends": "dep", "Recommends": "extra"},
            {"Package": "dep"}, {"Package": "extra"},
            {"Package": "blocked", "Source": "bad-source"},
            {"Package": "allowed"},
            {"Package": "provider", "Source": "bad-source", "Provides": "virtual"},
            {"Package": "optional", "Depends": "optional-dep", "Recommends": "optional-extra"},
            {"Package": "optional-dep"}, {"Package": "optional-extra"},
            {"Package": "base-app", "Depends": "blocked", "Recommends": "base-extra"},
            {"Package": "base-extra"},
            {"Package": "leaf-app", "Depends": "blocked", "Recommends": "leaf-extra"},
            {"Package": "leaf-extra"},
        ]
        cases = [
            ("plain", "desktop:\n", {"desktop": " * app\n"}, None),
            ("recommends", "feature follow-recommends\ndesktop:\n",
             {"desktop": " * app\n * (optional)\n"}, None),
            ("seed-recommends", "desktop:\n", {"desktop": " * app\n * (optional)\n"}, None),
            ("blocked-direct", "desktop:\n", {"desktop": " * app\n * blocked\n * !blocked\n"}, None),
            ("blocked-dependency", "desktop:\n", {"desktop": " * app\n * !blocked\n"}, "blocked"),
            ("blocked-alternative", "desktop:\n", {"desktop": " * app\n * !blocked\n"}, "blocked | allowed"),
            ("blocked-source-provider", "desktop:\n",
             {"desktop": " * app\n * !%bad-source [arm64]\n"}, "virtual"),
            ("ordinary-blocklist-seed", "desktop:\nblocklist:\n",
             {"desktop": " * blocked\n", "blocklist": " * !blocked\n"}, None),
            ("inner-blocklist", "base:\ndesktop: base\n",
             {"base": " * base-app\n * !blocked\n", "desktop": " * leaf-app\n"}, None),
            ("outer-blocklist", "base:\ndesktop: base\n",
             {"base": " * base-app\n", "desktop": " * leaf-app\n * !blocked\n"}, None),
            ("per-seed-feature", "feature follow-recommends\nbase:\ndesktop: base\n",
             {"base": " * Feature: no-follow-recommends\n * base-app\n", "desktop": " * leaf-app\n"}, None),
        ]
        count = 0
        logging.getLogger("germinate").setLevel(logging.CRITICAL)
        try:
            os.chdir(root)
            for architecture in ("amd64", "arm64"):
                for label, structure_text, documents, dependency in cases:
                    case = root / f"{label}-{architecture}"
                    seeds = case / "seeds" / "fixture"
                    seeds.mkdir(parents=True)
                    structure_text = "feature no-follow-build-depends\n" + structure_text
                    (seeds / "STRUCTURE").write_text(structure_text)
                    for name, contents in documents.items():
                        (seeds / name).write_text(contents)
                    packages = [{"Version": "1", "Architecture": architecture, **item} for item in base_packages]
                    if dependency is not None:
                        packages[0]["Depends"] = dependency
                    package_path = case / "Packages"
                    package_path.write_text("\n\n".join(
                        "\n".join(f"{key}: {value}" for key, value in package.items())
                        for package in packages
                    ) + "\n")
                    structure = SeedStructure("fixture", seed_bases=[seeds.parent.as_uri()])
                    germinator = Germinator(architecture)
                    germinator.parse_archive(SyntheticArchive(packages))
                    germinator.plant_seeds(structure, ["desktop"])
                    germinator.grow(structure)
                    expected = set(germinator.get_all(structure))
                    command = [str(args.binary), "resolve-seed-packages", str(seeds / "STRUCTURE"),
                               "fixture", "desktop", architecture, str(package_path)]
                    result = subprocess.run(command, text=True, capture_output=True)
                    if result.returncode:
                        raise RuntimeError(f"{label}/{architecture}: Rust exited {result.returncode}: {result.stderr}")
                    actual = {fields[1] for line in result.stdout.splitlines()
                              if (fields := line.split("\t"))[0] in ("package", "recommended-package")}
                    if actual != expected:
                        raise AssertionError(f"{label}/{architecture}: Rust {sorted(actual)} != Germinate {sorted(expected)}")
                    count += 1
        finally:
            os.chdir(previous)
        print(f"{count} Germinate {reference['version']}/Rust profile package-set comparisons passed")


if __name__ == "__main__":
    main()
