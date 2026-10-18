#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Repackage the unchanged, checksum-pinned Aurora kernel for Debian; never install it."""
import argparse
import gzip
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

from release import HERE, PINS, asset, extract, sha256, validate_kernel


def tar_gz(root):
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as archive:
            for path in sorted(Path(root).rglob("*")):
                info = archive.gettarinfo(str(path), arcname="./" + path.relative_to(root).as_posix())
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = "root"
                if info.isfile():
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
                else:
                    archive.addfile(info)
    return buffer.getvalue()


def write_deb(output, control, payload):
    # Debian's uncompressed ar envelope contains two standard gzip tar members.
    with Path(output).open("wb") as target:
        target.write(b"!<arch>\n")
        for name, data in (("debian-binary", b"2.0\n"), ("control.tar.gz", tar_gz(control)),
                           ("data.tar.gz", tar_gz(payload))):
            header = f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n"
            target.write(header.encode("ascii"))
            target.write(data)
            if len(data) % 2:
                target.write(b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    inputs = {kind: asset(args.cache, kind, offline=args.offline) for kind in ("kernel", "recipe", "source")}
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aurora-package-") as temporary:
        work = Path(temporary)
        payload, control, recipe, licenses = (work / name for name in ("payload", "control", "recipe", "licenses"))
        control.mkdir()
        extract(inputs["kernel"], payload, ("usr/lib/modules", "usr/lib/modprobe.d"))
        modules = validate_kernel(payload)
        extract(inputs["recipe"], recipe, ("PKGBUILD", "config", "rust-toolchain.toml", "linux-aurora-phram.conf"))
        if sha256(recipe / "config") != PINS["recipe_config_sha256"]:
            raise ValueError("upstream recipe configuration mismatch")
        source_root = "aurora-linux-" + PINS["kernel_source"]
        extract(inputs["source"], licenses, (source_root + "/COPYING", source_root + "/LICENSES"))
        docs = payload / "usr/share/doc" / PINS["debian_package"]
        shutil.copytree(licenses / source_root, docs)
        shutil.copytree(recipe, docs / "upstream-recipe")
        shutil.copy2(HERE / "release.json", docs / "release.json")
        (docs / "README").write_text(
            "Unmodified upstream Aurora kernel, modules and device trees.\n"
            "Payload package only: no maintainer scripts, /boot writes, bootloader changes or reboot.\n"
            "Use mseries/aurora-sep/install-aurora-sep.sh for explicit candidate installation.\n"
            "Pair with the pinned m1n1 and J314S DTB; see mseries/aurora/README.md.\n"
            "The original source archive accompanies this package. Not hardware-qualified on J314S/WD22TB4.\n")
        size = sum(path.stat().st_size for path in payload.rglob("*") if path.is_file()) // 1024
        (control / "control").write_text(
            f"Package: {PINS['debian_package']}\nVersion: {PINS['debian_version']}\n"
            "Architecture: arm64\nMaintainer: ElementaryOS MSeries contributors <builder@localhost>\n"
            f"Installed-Size: {size}\nSection: kernel\nPriority: optional\n"
            "Depends: kmod\n"
            f"Homepage: https://github.com/{PINS['repository']}\n"
            "Description: Optional upstream Aurora Apple Silicon kernel payload\n"
            " M1/M2/M3 and Neo drivers, modules and DTBs from a pinned upstream build.\n"
            " Explicit initramfs and boot-chain staging required; no automatic boot changes.\n")
        filename = f"{PINS['debian_package']}_{PINS['debian_version']}_arm64.deb"
        package = args.output / filename
        write_deb(package, control, payload)
        # Corresponding source, original build recipe and input binary travel with the .deb.
        for path in inputs.values():
            destination = args.output / path.name
            if path.resolve() != destination.resolve():
                shutil.copy2(path, destination)
        report = {"pins": PINS, "package": filename, "package_sha256": sha256(package),
                  "kernel_image_sha256": sha256(modules / "vmlinuz"),
                  "j314s_dtb_sha256": sha256(modules / "dtbs/t6000-j314s.dtb"),
                  "validation": "Checksums, payload/dependency/DT checks only; no hardware boot"}
        (args.output / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    files = sorted(path for path in args.output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (args.output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in files))
    print(f"Packaged {package}; no package was installed")


if __name__ == "__main__":
    main()
