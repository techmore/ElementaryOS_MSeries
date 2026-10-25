#!/usr/bin/env python3
"""Compare Rust packages with the pinned, unchanged Elementary packaging build.

The native-only option verifies real-source package construction locally. Full
Linux qualification runs upstream debian/rules with checksum-pinned Germinate
helpers, then compares all eight packages on both hosts with full/trimmed logs.
The upstream source remains temporary; no source/list text is vendored here.
"""

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
import urllib.request


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("deb_parity", HERE / "test-deb-parity.py")
parity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parity)
EPOCH = 1_700_000_000
PACKAGES = {
    "elementary-minimal", "elementary-standard", "elementary-desktop",
    "elementary-artwork", "pantheon-shell", "pantheon", "elementary-sdk",
    "elementary-live",
}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def source_archive(record, local_archive):
    if local_archive:
        data = local_archive.read_bytes()
    else:
        with urllib.request.urlopen(record["source_archive"], timeout=60) as response:
            data = response.read(2 * 1024 * 1024 + 1)
    if digest(data) != record["source_archive_sha256"]:
        raise RuntimeError("Elementary source archive SHA-256 mismatch")
    return data


def extract_source(data, source, commit, project="metapackages"):
    source.mkdir(parents=True)
    prefix = PurePosixPath(f"{project}-{commit}")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for entry in archive.getmembers():
            name = PurePosixPath(entry.name)
            if name.is_absolute() or ".." in name.parts or not name.is_relative_to(prefix):
                raise RuntimeError(f"unsafe upstream archive path: {entry.name}")
            relative = name.relative_to(prefix)
            target = source.joinpath(*relative.parts)
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif entry.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(entry).read())
                target.chmod(entry.mode & 0o777)
            else:
                raise RuntimeError(f"unsupported upstream archive entry: {entry.name}")


def install_reference(root, local_archive):
    data = parity.reference_archive(local_archive)
    library = root / "perl"
    binary = root / "bin"
    binary.mkdir()
    files = {
        "work/debhelper/germinate.pm": library / "Debian/Debhelper/Sequence/germinate.pm",
        "work/debhelper/dh_germinate_clean": binary / "dh_germinate_clean",
        "work/debhelper/dh_germinate_metapackage": binary / "dh_germinate_metapackage",
    }
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as archive:
        for name, target in files.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(name).read())
            target.chmod(0o755 if target.parent == binary else 0o644)
    return binary, library


def extracted_files(package, member, cwd, environment):
    option = "--ctrl-tarfile" if member == "control" else "--fsys-tarfile"
    data = parity.run(["dpkg-deb", option, str(package)], cwd=cwd, env=environment, binary=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        result = {}
        for entry in archive.getmembers():
            name = PurePosixPath(entry.name)
            if name.is_absolute() or ".." in name.parts:
                raise AssertionError(f"unsafe package path: {entry.name}")
            if entry.isfile():
                result[name.as_posix()] = archive.extractfile(entry).read()
            elif not entry.isdir():
                raise AssertionError(f"unexpected package entry type: {entry.name}")
        return result


def check_sums(control, data):
    sums = {line.split("  ", 1)[1]: line.split("  ", 1)[0]
            for line in control["md5sums"].decode().splitlines()}
    if sums != {name: hashlib.md5(value).hexdigest() for name, value in data.items()}:
        raise AssertionError("package payload md5sums do not match")


def semantic_digest(data):
    return digest(json.dumps({name: digest(value) for name, value in
                              parity.semantic_payload(data).items()}, sort_keys=True).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=lambda value: Path(value).resolve())
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--germinate-archive", type=Path)
    parser.add_argument("--native-only", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.report and args.report.exists():
        parser.error("report path already exists")
    required = ["ar"] + ([] if args.native_only else [
        "dpkg-deb", "dpkg-gencontrol", "dpkg-architecture", "dpkg-query", "make", "dh", "fakeroot",
    ])
    for tool in required:
        if not shutil.which(tool):
            parser.error(f"required tool is missing: {tool}")
    manifest = json.loads((HERE.parent / "elementary-image-projects.json").read_text())
    record = manifest["upstream_metapackages"]
    source = source_archive(record, args.source_archive)
    environment = os.environ.copy()
    for name in list(environment):
        if name.startswith(("DEB_", "DH_")) or name in {"SOURCE_DATE_EPOCH", "MAKEFLAGS", "PERL5LIB"}:
            environment.pop(name)
    environment.update(LC_ALL="C.UTF-8" if not args.native_only else "C", SOURCE_DATE_EPOCH=str(EPOCH))
    report = {"schema": 1, "source_commit": record["commit"],
              "source_archive_sha256": digest(source), "linux_oracle": not args.native_only,
              "source_date_epoch": EPOCH, "packages": []}
    failures = []
    with tempfile.TemporaryDirectory(prefix="mseries-upstream-deb-") as temporary:
        root = Path(temporary)
        if not args.native_only:
            binary, library = install_reference(root, args.germinate_archive)
            environment["PATH"] = f"{binary}{os.pathsep}{environment['PATH']}"
            environment["PERL5LIB"] = str(library)
            report["debhelper_version"] = parity.run(["dpkg-query", "-W", "-f=${Version}", "debhelper"], cwd=root, env=environment).stdout
            report["dpkg_dev_version"] = parity.run(["dpkg-query", "-W", "-f=${Version}", "dpkg-dev"], cwd=root, env=environment).stdout
        for host in ("amd64", "arm64"):
            for full in (False, True):
                case = root / f"{host}-{full}"
                native_source = case / "native-source"
                extract_source(source, native_source, record["commit"])
                env = environment.copy()
                if full:
                    env["DEB_BUILD_OPTIONS"] = "notrimdch"
                if not args.native_only:
                    env.update(line.split("=", 1) for line in parity.run(["dpkg-architecture", f"-a{host}", "-l"], cwd=case, env=env).stdout.splitlines())
                command = [str(args.binary), "build-metapackages", str(native_source), str(native_source), host, str(case / "native")]
                parity.run(command, cwd=case, env=env)
                repeated = command.copy()
                repeated[5] = str(case / "repeated")
                parity.run(repeated, cwd=case, env=env)
                reference = case / "reference/source"
                if not args.native_only:
                    extract_source(source, reference, record["commit"])
                    # Execute upstream's unchanged rules, with only the pinned
                    # Germinate tools installed in an isolated PATH/PERL5LIB.
                    parity.run(["make", "-f", "debian/rules", "clean"], cwd=reference, env=env)
                    parity.run(["fakeroot", "make", "-f", "debian/rules", "binary"], cwd=reference, env=env)
                actual = set()
                for package_file in sorted((case / "native").glob("*.deb")):
                    if package_file.read_bytes() != (case / "repeated" / package_file.name).read_bytes():
                        raise AssertionError("real-source native rebuild is not reproducible")
                    control = parity.archive_members(package_file, "control.tar.gz", EPOCH, env)
                    data = parity.archive_members(package_file, "data.tar.gz", EPOCH, env)
                    check_sums(control, data)
                    metadata = parity.fields(control["control"].decode())
                    package = metadata["Package"]
                    if package in actual or metadata["Architecture"] != host or metadata["Version"] != record["source_version"]:
                        raise AssertionError("unexpected/duplicate real-source binary identity")
                    actual.add(package)
                    receipt = {"host_architecture": host, "full_changelog": full,
                               "package": package, "version": metadata["Version"],
                               "native_sha256": digest(package_file.read_bytes()),
                               "installed_documentation_sha256": semantic_digest(data),
                               "native_installed_size_kib": metadata["Installed-Size"]}
                    if not args.native_only:
                        reference_file = reference.parent / package_file.name
                        reference_control = extracted_files(reference_file, "control", case, env)
                        reference_data = extracted_files(reference_file, "data", case, env)
                        check_sums(reference_control, reference_data)
                        if control.keys() != reference_control.keys():
                            failures.append(f"{host}/{full}/{package}: control archive file membership differs")
                        for name in (control.keys() & reference_control.keys()) - {"control", "md5sums"}:
                            if control[name] != reference_control[name]:
                                failures.append(f"{host}/{full}/{package}: control archive file {name} differs")
                        reference_metadata = parity.fields(reference_control["control"].decode())
                        if parity.semantic_payload(data) != parity.semantic_payload(reference_data):
                            failures.append(f"{host}/{full}/{package}: installed documentation differs")
                        # Compression bytes may differ, so verify native size
                        # against dpkg on its own bytes at the same build stage.
                        stage = case / f"stage-{package}"
                        parity.run(["dpkg-deb", "--raw-extract", str(package_file), str(stage)], cwd=reference, env=env)
                        shutil.rmtree(stage / "DEBIAN")
                        (stage / "DEBIAN").mkdir()
                        generated = parity.fields(parity.run([
                            "dpkg-gencontrol", f"-p{package}", f"-P{stage}",
                            f"-Tdebian/{package}.substvars", "-O",
                        ], cwd=reference, env=env).stdout)
                        for field in sorted(metadata.keys() | generated.keys()):
                            if metadata.get(field) != generated.get(field):
                                failures.append(f"{host}/{full}/{package}/{field}: Rust {metadata.get(field)!r} != dpkg {generated.get(field)!r}")
                        for field in sorted(metadata.keys() | reference_metadata.keys()):
                            if field != "Installed-Size" and metadata.get(field) != reference_metadata.get(field):
                                failures.append(f"{host}/{full}/{package}/{field}: Rust {metadata.get(field)!r} != upstream build {reference_metadata.get(field)!r}")
                        receipt.update(reference_sha256=digest(reference_file.read_bytes()),
                                       reference_installed_size_kib=reference_metadata["Installed-Size"])
                    report["packages"].append(receipt)
                if actual != PACKAGES:
                    raise AssertionError(f"upstream package set differs: {actual}")
    if failures:
        raise AssertionError("\n".join(failures))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
    count = len(report["packages"])
    if args.native_only:
        print(f"{count} pinned Elementary native package checks passed; Linux upstream build oracle not run")
    else:
        print(f"{count} pinned Elementary packages passed unchanged upstream rules, control, documentation, checksum and native reproducibility comparisons; Debhelper {report['debhelper_version']}; dpkg-dev {report['dpkg_dev_version']}")


if __name__ == "__main__":
    main()
