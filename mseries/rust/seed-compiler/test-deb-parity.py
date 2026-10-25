#!/usr/bin/env python3
"""Qualify native metapackages against dpkg and Debhelper on synthetic inputs.

--native-only runs archive, checksum, date and reproducibility checks without
the Linux oracle. Full CI also compares binary control fields and installed
documentation with dpkg-gencontrol and Debhelper, using pinned Germinate 2.49.
"""

import argparse
import gzip
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
LONG_PACKAGE = "fixture-" + "long" * 20
PACKAGES = ["fixture-desktop", "fixture-empty", "fixture-all", "fixture-amd", "fixture-meta", LONG_PACKAGE]


def run(command, *, cwd, env, binary=False):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=not binary)
    if result.returncode:
        raise RuntimeError(f"{command!r} exited {result.returncode}\n{result.stdout!r}\n{result.stderr!r}")
    return result


def fields(text):
    result = {}
    key = None
    for line in text.splitlines():
        if line.startswith((" ", "\t")):
            result[key] += "\n" + line[1:]
        elif line:
            key, value = line.split(":", 1)
            result[key] = value.lstrip()
    return result


def archive_members(package, member, epoch, environment):
    compressed = run(["ar", "p", str(package), member], cwd=package.parent, env=environment, binary=True).stdout
    with tarfile.open(fileobj=io.BytesIO(compressed), mode="r:gz") as archive:
        result = {}
        for entry in archive.getmembers():
            if entry.uid != 0 or entry.gid != 0 or entry.mtime != epoch:
                raise AssertionError(f"noncanonical ownership/date: {entry.name}")
            if entry.mode != (0o755 if entry.isdir() else 0o644):
                raise AssertionError(f"incorrect mode: {entry.name}")
            name = entry.name.removeprefix("./")
            if entry.isfile():
                result[name] = archive.extractfile(entry).read()
            elif not entry.isdir():
                raise AssertionError(f"unexpected archive entry type: {entry.name}")
        return result


def semantic_payload(files):
    return {name[:-3] if name.endswith(".gz") else name:
            gzip.decompress(value) if name.endswith(".gz") else value
            for name, value in files.items()}


def reference_archive(source_archive):
    reference = next(item for item in json.loads((HERE.parent / "elementary-build-inputs.json").read_text())["reference_projects"]
                     if item["id"] == "ubuntu/germinate")
    if source_archive:
        data = source_archive.read_bytes()
    else:
        with urllib.request.urlopen(reference["source_archive"], timeout=60) as response:
            data = response.read(8 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != reference["source_archive_sha256"]:
        raise RuntimeError("Germinate reference SHA-256 mismatch")
    return data


def reference_helper(root, source_archive):
    data = reference_archive(source_archive)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as archive:
        source = archive.extractfile("work/debhelper/dh_germinate_metapackage")
        if source is None:
            raise RuntimeError("pinned helper is absent")
        path = root / "dh_germinate_metapackage"
        path.write_bytes(source.read())
    return path


def fixture(source, lists, version):
    (source / "debian").mkdir(parents=True)
    lists.mkdir()
    (source / "debian/control").write_text(
        "Source: fixture-meta\nSection: metapackages\nPriority: optional\n"
        "Maintainer: Fixture <fixture@example.invalid>\nHomepage: https://example.invalid/source\n"
        "Build-Depends: debhelper-compat (= 13)\nDescription: Source synopsis\n Source long description.\n\n"
        "Package: fixture-desktop\nArchitecture: amd64 arm64\nPre-Depends: pre\n"
        "Depends: ${misc:Depends}, ${germinate:Depends}, fixture-desktop (= ${binary:Version}), lib (>= 1), lib (>= 2), arm-only [arm64]\n"
        "Recommends: ${germinate:Recommends}, lib (>= 1), amd-only [amd64]\nSuggests: optional, remaining\n"
        "Description: ${source:Synopsis} on ${Arch}\n ${source:Extended-Description}\n .\n  preserve indentation\n\n"
        "Package: fixture-empty\nArchitecture: any\nDepends: ${misc:Depends}, ${germinate:Depends}\n"
        "Recommends: ${germinate:Recommends}\nDescription: Empty metapackage\n No runtime payload.\n\n"
        "Package: fixture-all\nArchitecture: all\nHomepage: https://example.invalid/binary\n"
        "Depends: ${germinate:Depends}\nDescription: Shared data selection for ${Arch}\n\n"
        "Package: fixture-amd\nArchitecture: any-amd64\nDepends: tool:any (>= 2)\nDescription: Architecture selection\n\n"
        "Package: fixture-meta\nArchitecture: arm64\nDescription: Same source/binary name\n\n"
        f"Package: {LONG_PACKAGE}\nArchitecture: any\nPackage-Type: deb\n"
        "Provides: fixture-virtual (= ${binary:Version}), fixture-virtual (= ${binary:Version}), fixture-virtual\n"
        "Conflicts: old (<< 2), old (<< 3)\nBuilt-Using: fixture-runtime-source (= ${source:Version})\n"
        "Description: Long ustar path and relation normalization\n"
    )
    (source / "debian/rules").write_text("#!/usr/bin/make -f\n%:\n\tdh --with germinate $@\n")
    (source / "debian/copyright").write_bytes(b"Synthetic fixture copyright and license.\n")
    (source / "debian/fixture-all.copyright").write_bytes(b"Package-specific synthetic license.\n")
    (source / "debian/changelog").write_text(
        f"fixture-meta ({version}) unstable; urgency=medium\n\n  * Current fixture.\n\n"
        " -- Fixture <fixture@example.invalid>  Sun, 25 Oct 2026 20:00:00 +0000\n\n" + "".join(
            f"fixture-meta (0.{index}) unstable; urgency=low\n\n  * Old fixture {index}.\n\n"
            " -- Fixture <fixture@example.invalid>  Sat, 01 Jan 2022 00:00:00 +0000\n\n"
            for index in range(6)
        )
    )
    (lists / "metapackage-map").write_text("desktop fixture-desktop\nempty fixture-empty\nshared fixture-all\n")
    for architecture in ("amd64", "arm64"):
        (lists / f"desktop-{architecture}").write_text("pre\nzeta\nalpha | beta\nlib (>= 3)\nfixture-desktop\n")
        (lists / f"desktop-recommends-{architecture}").write_text("lib\noptional\nzeta\n")
        (lists / f"empty-{architecture}").write_text("")
        (lists / f"empty-recommends-{architecture}").write_text("")
    (lists / "shared-all").write_text("shared-data\n")
    (lists / "shared-recommends-all").write_text("")
    for path in lists.iterdir():
        shutil.copyfile(path, source / path.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=lambda value: Path(value).resolve())
    parser.add_argument("--native-only", action="store_true")
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    tools = ["ar"] + ([] if args.native_only else ["dpkg-deb", "dpkg-gencontrol", "dpkg-architecture", "dh_installdocs", "dh_installchangelogs", "dh_compress", "perl"])
    for tool in tools:
        if not shutil.which(tool):
            parser.error(f"required tool is missing: {tool}")
    environment = os.environ.copy()
    for name in list(environment):
        if name.startswith("DEB_") or name.startswith("DH_") or name == "SOURCE_DATE_EPOCH":
            environment.pop(name)
    environment["LC_ALL"] = "C.UTF-8" if not args.native_only else "C"
    count = 0
    failures = []
    with tempfile.TemporaryDirectory(prefix="mseries-deb-parity-") as temporary:
        root = Path(temporary)
        helper = None if args.native_only else reference_helper(root, args.archive)
        for version in ("1.2", "2:1.2-beta-3"):
            for host in ("amd64", "arm64"):
                for full in (False, True):
                    case = root / f"{version.replace(':', '-')}-{host}-{full}"
                    source, lists = case / "source", case / "lists"
                    fixture(source, lists, version)
                    env = environment.copy()
                    epoch = 1_700_000_000
                    env["SOURCE_DATE_EPOCH"] = str(epoch)
                    if not args.native_only:
                        env.update(line.split("=", 1) for line in run(["dpkg-architecture", f"-a{host}", "-l"], cwd=source, env=env).stdout.splitlines())
                    command = [str(args.binary), "build-metapackages", str(source), str(lists), host, str(case / "first")]
                    if full:
                        command.append("--full-changelog")
                    run(command, cwd=source, env=env)
                    second = command.copy()
                    second[5] = str(case / "second")
                    run(second, cwd=source, env=env)
                    expected_packages = set(PACKAGES) - ({"fixture-meta"} if host == "amd64" else {"fixture-amd"})
                    actual_packages = set()
                    for package_file in sorted((case / "first").glob("*.deb")):
                        if package_file.read_bytes() != (case / "second" / package_file.name).read_bytes():
                            raise AssertionError("native package rebuild is not reproducible")
                        control = archive_members(package_file, "control.tar.gz", epoch, env)
                        data = archive_members(package_file, "data.tar.gz", epoch, env)
                        metadata = fields(control["control"].decode())
                        package = metadata["Package"]
                        actual_packages.add(package)
                        if metadata["Version"] != version or metadata["Architecture"] != ("all" if package == "fixture-all" else host):
                            raise AssertionError("incorrect binary version/architecture")
                        if ":" in package_file.name:
                            raise AssertionError("epoch was retained in package filename")
                        sums = {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in control["md5sums"].decode().splitlines()}
                        if sums != {name: hashlib.md5(value).hexdigest() for name, value in data.items()}:
                            raise AssertionError("data md5sums do not match archive contents")
                        if not args.native_only:
                            stage = case / f"unpacked-{package}"
                            run(["dpkg-deb", "--info", str(package_file)], cwd=source, env=env)
                            run(["dpkg-deb", "--raw-extract", str(package_file), str(stage)], cwd=source, env=env)
                            # Model dh_gencontrol's stage: DEBIAN exists, but its
                            # control and md5sums files have not been generated.
                            shutil.rmtree(stage / "DEBIAN")
                            (stage / "DEBIAN").mkdir()
                            run(["perl", str(helper), f"-p{package}"], cwd=source, env=env)
                            substvars = source / "debian" / f"{package}.substvars"
                            substvars.touch(exist_ok=True)
                            expected_control = run(["dpkg-gencontrol", f"-p{package}", f"-P{stage}", f"-T{substvars}", "-O"], cwd=source, env=env).stdout
                            if metadata != fields(expected_control):
                                for field in sorted(metadata.keys() | fields(expected_control).keys()):
                                    if metadata.get(field) != fields(expected_control).get(field):
                                        failures.append(f"{version}/{host}/{full}/{package}/{field}: Rust {metadata.get(field)!r} != dpkg {fields(expected_control).get(field)!r}")
                            run(["dh_installdocs", f"-p{package}"], cwd=source, env=env)
                            run(["dh_installchangelogs", f"-p{package}"] + (["--no-trim"] if full else []), cwd=source, env=env)
                            run(["dh_compress", f"-p{package}"], cwd=source, env=env)
                            reference_root = source / "debian" / package
                            reference_data = {path.relative_to(reference_root).as_posix(): path.read_bytes()
                                              for path in reference_root.rglob("*") if path.is_file()}
                            if semantic_payload(data) != semantic_payload(reference_data):
                                failures.append(f"{version}/{host}/{full}/{package}: installed documentation differs from Debhelper: Rust {semantic_payload(data)!r} != reference {semantic_payload(reference_data)!r}")
                        count += 1
                    if actual_packages != expected_packages:
                        raise AssertionError(f"incorrect selected packages: {actual_packages} != {expected_packages}")
        # Failure must leave no output directory even if earlier packages were valid.
        source, lists = root / "invalid/source", root / "invalid/lists"
        fixture(source, lists, "1.2")
        (source / "debian/fixture-empty.postinst").write_text("#!/bin/sh\nexit 0\n")
        output = root / "invalid-output"
        result = subprocess.run([str(args.binary), "build-metapackages", str(source), str(lists), "arm64", str(output)], env=environment, capture_output=True)
        if not result.returncode or output.exists():
            raise AssertionError("unsupported payload/script source emitted partial packages")
    if failures:
        raise AssertionError("\n".join(failures))
    if args.native_only:
        print(f"{count} native package archive/checksum/reproducibility checks passed; Linux oracle not run")
    else:
        print(f"{count} native packages passed dpkg control, Debhelper documentation, extraction, checksum and reproducibility comparisons")


if __name__ == "__main__":
    main()
