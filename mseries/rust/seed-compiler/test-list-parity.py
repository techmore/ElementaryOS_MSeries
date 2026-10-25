#!/usr/bin/env python3
"""Compare generated map/list files with the pinned Germinate updater.

Uses synthetic local archive/seed inputs and freezes only debootstrap's package
set/version boundary. Germinate's updater, archive reader, and seed parser run
from checksum-verified, unmodified source. Requires Linux system python3-apt.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


HERE = Path(__file__).resolve().parent
REFERENCE_RUNNER = r'''
import sys
from pathlib import Path
import subprocess
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from germinate.scripts.germinate_update_metapackage import main
original = subprocess.Popen
indices = Path(sys.argv[2])
seen = set()
def frozen_bootstrap(command, *args, **kwargs):
    if command[0] == 'debootstrap' and '--print-debs' in command:
        arch = command[command.index('--arch') + 1]
        seen.add(arch)
        values = (indices / ('debootstrap-' + arch)).read_text()
        command = [sys.executable, '-c', 'import sys; print(sys.argv[1])', values]
    elif command[0] == 'dpkg-query' and command[-1] == 'debootstrap':
        command = [sys.executable, '-c', 'print("1.0-fixture")']
    return original(command, *args, **kwargs)
with patch('subprocess.Popen', side_effect=frozen_bootstrap):
    main(['germinate-update-metapackage', '--nodch'] + sys.argv[3:])
assert seen == {'amd64', 'arm64'}, seen
'''


def run(command, cwd):
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{command!r} exited {result.returncode}\n{result.stdout}{result.stderr}")
    return result


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

    with tempfile.TemporaryDirectory(prefix="mseries-list-parity-") as temporary:
        root = Path(temporary)
        reference_source = root / "reference"
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:xz") as source:
            for member in source.getmembers():
                if (member.isfile() and member.name.startswith("work/germinate/")
                        and "/tests/" not in member.name and member.name.endswith(".py")):
                    relative = Path(member.name).relative_to("work")
                    if ".." in relative.parts:
                        raise RuntimeError("unexpected archive member")
                    stream = source.extractfile(member)
                    if stream is None:
                        raise RuntimeError(f"missing reference module {member.name}")
                    target = reference_source / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(stream.read())

        documents = {
            "minimal": "Task-Metapackage: custom-minimal\n * essential-core\n * boot\n * not-in-bootstrap\n * custom-minimal\n * (essential-rec)\n * (minimal-doc)\n",
            "standard": " * boot\n * standard-tool\n * (standard-doc)\n",
            "artwork": "Task-Metapackage: artwork-selected\n * wallpaper\n",
            "desktop": "TaSk-MeTaPaCkAgE: native-desktop\nTask-Seeds: artwork\n * standard-tool\n * app-primary | app-fallback | missing-alternative\n * primary-missing | app-fallback\n * wildcard-*\n * single-?\n * virtual-choice\n * %source-bundle\n * %versioned-source\n * %missing-source\n * %default-source\n * (%source-recommended)\n * (desktop-doc)\n * essential-top\n * !blocked\n * blocked\n * arch-tool [arm64]\n * native-desktop\n * Languages: en fr\n * locale-${Languages}\n * Languages: de\n * (locale-${languages})\n * Empty:\n * ignored-${Empty}\n * unknown-${missing}tail\n * Pattern: expanded-*\n * ${Pattern}\n * Source: unexpanded-source\n * %${Source}\n",
            "bundle": " * (bundle-doc)\ntask-seeds: standard desktop\n",
            "empty": "Task-Name: Empty synthetic profile\n",
        }
        seeds = root / "seeds" / "fixture"
        seeds.mkdir(parents=True)
        (seeds / "STRUCTURE").write_text(
            "minimal:\nstandard: minimal\nartwork:\ndesktop: standard artwork\nbundle: desktop\nempty:\n"
        )
        for name, text in documents.items():
            (seeds / name).write_text(text)
        indices = root / "indices"
        indices.mkdir()
        mirror = root / "mirror"
        binaries = [
            {"Package": name} for name in (
                "locale-en", "locale-fr", "locale-de", "unknown-tail", "expanded-one",
                "boot", "not-in-bootstrap", "custom-minimal", "minimal-doc", "standard-tool",
                "standard-doc", "wallpaper", "app-primary", "unseeded-dependency", "wildcard-one",
                "wildcard-two", "single-a", "desktop-doc", "blocked", "arch-tool", "native-desktop", "bundle-doc",
            )
        ] + [
            {"Package": "essential-core", "Essential": "yes"},
            {"Package": "essential-rec", "Essential": "yes"},
            {"Package": "essential-top", "Essential": "yes"},
            {"Package": "provider-one", "Provides": "virtual-choice"},
            {"Package": "provider-two", "Provides": "virtual-choice"},
            {"Package": "source-one", "Source": "source-bundle"},
            {"Package": "source-two", "Source": "source-bundle", "Architecture": "all"},
            {"Package": "source-doc", "Source": "source-recommended"},
            {"Package": "source-orphan", "Source": "source-bundle"},
            {"Package": "source-old", "Source": "versioned-source"},
            {"Package": "source-new", "Source": "versioned-source"},
            {"Package": "source-missing", "Source": "missing-source"},
            {"Package": "default-source"},
            {"Package": "unexpanded-binary", "Source": "unexpanded-source"},
        ]
        all_source_binaries = {}
        for architecture in ("amd64", "arm64"):
            packages = [{"Version": "1", "Architecture": architecture, **package} for package in binaries]
            if architecture == "amd64":
                packages.append({"Package": "app-fallback", "Version": "1", "Architecture": architecture})
            next(package for package in packages if package["Package"] == "app-primary")["Depends"] = "unseeded-dependency"
            text = "\n\n".join("\n".join(f"{key}: {value}" for key, value in package.items()) for package in packages) + "\n"
            (indices / f"Packages-{architecture}").write_text(text)
            (indices / f"debootstrap-{architecture}").write_text("boot essential-core essential-rec minimal-doc custom-minimal\n")
            component = mirror / "dists/sample/main"
            for suffix in (f"binary-{architecture}/Packages", f"debian-installer/binary-{architecture}/Packages"):
                path = component / suffix
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text if suffix.startswith("binary-") else "")
            for package in packages:
                if package["Package"] not in ("source-orphan", "source-missing", "source-old", "source-new", "default-source"):
                    all_source_binaries.setdefault(package.get("Source", package["Package"]), set()).add(package["Package"])
        source_text = "".join(f"Package: {name}\nVersion: 1\nBinary: {', '.join(sorted(names))}\n\n"
                              for name, names in all_source_binaries.items())
        source_text += "Package: default-source\nVersion: 1\n\n"
        source_text += "Package: versioned-source\nVersion: 1\nBinary: source-old\n\nPackage: versioned-source\nVersion: 2\nBinary: source-new\n\n"
        source_path = mirror / "dists/sample/main/source/Sources"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(source_text)
        for architecture in ("amd64", "arm64"):
            (indices / f"Sources-{architecture}").write_text(source_text)

        common = (f"architectures: amd64 arm64\narchive_base/default: {mirror.as_uri()}/\n"
                  f"seed_base: {seeds.parent.as_uri()}/\nseed_dist: fixture\ndists: sample\ncomponents: main\n")
        configs = [
            ("headers", "[DEFAULT]\ndist: sample\n[sample]\nseeds: minimal standard artwork desktop bundle empty\n" + common, None),
            ("maps", "[DEFAULT]\ndist: sample\nmeta_prefix: override\n[sample]\nseeds: minimal standard artwork desktop bundle empty\n"
             "output_seeds: desktop minimal empty\nseed_map/desktop: standard\nmetapackage_map/desktop: %(meta_prefix)s-desktop\n" + common, None),
            ("replacement", "[DEFAULT]\ndist: sample\n[sample]\nseeds: bundle empty\noutput_seeds: desktop bundle\n"
             "seed_map/bundle: empty\nmetapackage_map/bundle: fixture-custom\n" + common, None),
            ("explicit-dist", "[DEFAULT]\ndist: unused\n[unused]\nseeds: absent\narchitectures: invalid\n"
             "[second]\nseeds: bundle empty\n" + common, "second"),
        ]
        count = 0
        for label, config, distribution in configs:
            source_directory = root / label
            (source_directory / "debian").mkdir(parents=True)
            (source_directory / "debian/control").write_text("Source: fixture-meta\n")
            (source_directory / "update.cfg").write_text(config)
            run([sys.executable, "-c", REFERENCE_RUNNER, str(reference_source), str(indices)]
                + ([distribution] if distribution else []), source_directory)
            output = root / f"rust-{label}"
            command = [str(args.binary), "generate-metapackage-lists", str(source_directory),
                       str(seeds / "STRUCTURE"), "fixture", str(indices), str(output)]
            if distribution:
                command.append(f"--dist={distribution}")
            run(command, root)
            expected = {path.name: path.read_bytes() for path in source_directory.iterdir()
                        if path.is_file() and path.name not in ("update.cfg", "debootstrap-version")}
            actual = {path.name: path.read_bytes() for path in output.iterdir()}
            if actual != expected:
                for name in sorted(actual.keys() | expected.keys()):
                    if actual.get(name) != expected.get(name):
                        raise AssertionError(f"{label}/{name}: Rust {actual.get(name)!r} != reference {expected.get(name)!r}")
            count += len(expected)
        print(f"{count} Germinate {reference['version']}/Rust map/list file comparisons passed across {len(configs)} configurations")


if __name__ == "__main__":
    main()
