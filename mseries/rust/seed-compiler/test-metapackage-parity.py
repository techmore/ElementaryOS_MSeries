#!/usr/bin/env python3
"""Compare Rust substvars with Germinate's pinned helper and real Debhelper.

Requires Linux, perl, debhelper, and dpkg-dev. The reference helper is loaded
from the checksum-verified source archive; it is never vendored into this repo.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


HERE = Path(__file__).resolve().parent


def run(command, *, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            f"{command!r} exited {result.returncode}\n{result.stdout}{result.stderr}"
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=lambda value: Path(value).resolve())
    parser.add_argument("--archive", type=Path, help="use a previously downloaded pinned source archive")
    args = parser.parse_args()
    for tool in ("perl", "dpkg-architecture", "dpkg-query"):
        if not shutil.which(tool):
            parser.error(f"required Linux reference tool is missing: {tool}")

    manifest = json.loads((HERE.parent / "elementary-build-inputs.json").read_text())
    reference = next(item for item in manifest["reference_projects"] if item["id"] == "ubuntu/germinate")
    if args.archive:
        archive = args.archive.read_bytes()
    else:
        with urllib.request.urlopen(reference["source_archive"], timeout=60) as response:
            archive = response.read(8 * 1024 * 1024 + 1)
    if hashlib.sha256(archive).hexdigest() != reference["source_archive_sha256"]:
        raise RuntimeError("Germinate reference archive SHA-256 mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:xz") as source:
        member = source.extractfile("work/debhelper/dh_germinate_metapackage")
        if member is None:
            raise RuntimeError("pinned reference helper is missing")
        helper = member.read()

    with tempfile.TemporaryDirectory(prefix="mseries-metapackage-parity-") as temporary:
        root = Path(temporary)
        reference_script = root / "dh_germinate_metapackage"
        reference_script.write_bytes(helper)
        fixture = root / "fixture"
        (fixture / "debian").mkdir(parents=True)
        (fixture / "metapackage-map").write_text(
            "desktop fixture-meta\ntools fixture-tools\ndata fixture-data\n"
        )
        (fixture / "debian/changelog").write_text(
            "fixture (1.0) unstable; urgency=medium\n\n  * Synthetic parity fixture.\n\n"
            " -- Fixture <fixture@example.invalid>  Thu, 01 Jan 2026 00:00:00 +0000\n"
        )
        (fixture / "debian/control").write_text(
            "Source: fixture\nSection: metapackages\nPriority: optional\n"
            "Maintainer: Fixture <fixture@example.invalid>\nStandards-Version: 4.7.0\n"
            "Build-Depends: debhelper-compat (= 13)\n\n" + "\n".join(
                f"Package: {package}\nArchitecture: {architecture}\n"
                "Depends: ${misc:Depends}, ${germinate:Depends}\n"
                "Recommends: ${germinate:Recommends}\nDescription: synthetic fixture\n"
                for package, architecture in (
                    ("fixture-meta", "any"), ("fixture-tools", "any"),
                    ("fixture-data", "all"), ("fixture-unmapped", "any")
                )
            )
        )
        (fixture / "data-all").write_text("shared-data\n")
        (fixture / "data-recommends-all").write_text("")
        for architecture in ("amd64", "arm64"):
            (fixture / f"desktop-{architecture}").write_text(
                f"zeta\n alpha (>= 2) | beta \nzeta\narch-{architecture}\n"
            )
            (fixture / f"desktop-recommends-{architecture}").write_text("optional\n docs\noptional\n")
            (fixture / f"tools-{architecture}").write_text("")
            (fixture / f"tools-recommends-{architecture}").write_text("recommended-only\n")

        count = 0
        for architecture in ("amd64", "arm64"):
            environment = os.environ.copy()
            architecture_values = run(
                ["dpkg-architecture", f"-a{architecture}", "-l"], cwd=fixture, env=environment
            ).stdout
            environment.update(line.split("=", 1) for line in architecture_values.splitlines())
            for package in ("fixture-meta", "fixture-tools", "fixture-data", "fixture-unmapped"):
                substvars = fixture / "debian" / f"{package}.substvars"
                substvars.unlink(missing_ok=True)
                run(["perl", str(reference_script), f"-p{package}"], cwd=fixture, env=environment)
                expected = substvars.read_text() if substvars.exists() else ""
                binary_architecture = "all" if package == "fixture-data" else architecture
                actual = run(
                    [str(args.binary), "metapackage-substvars", str(fixture), binary_architecture, package],
                    cwd=fixture, env=environment,
                ).stdout
                if actual != expected:
                    raise AssertionError(f"{architecture}/{package}: Rust {actual!r} != reference {expected!r}")
                count += 1

        version = run(["dpkg-query", "-W", "-f=${Version}", "debhelper"], cwd=fixture, env=os.environ).stdout
        print(f"{count} Germinate {reference['version']}/Rust substvars comparisons passed; Debhelper {version}")


if __name__ == "__main__":
    main()
