#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared pinned Aurora inputs. Importing this module performs no I/O writes."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
PINS = json.loads((HERE / "release.json").read_text())


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def asset(cache, kind, *, offline=False):
    pin = PINS["assets"][kind]
    path = Path(cache) / pin["name"]
    if path.exists():
        if sha256(path) != pin["sha256"]:
            raise ValueError(f"checksum mismatch: {path}")
        return path
    if offline:
        raise ValueError(f"missing cached input: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    url = pin.get("url", f"https://github.com/{PINS['repository']}/releases/download/{PINS['release']}/{pin['name']}")
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as source, temporary.open("wb") as target:
            while block := source.read(1024 * 1024):
                target.write(block)
        if sha256(temporary) != pin["sha256"]:
            raise ValueError(f"checksum mismatch: {url}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def extract(archive, destination, prefixes):
    """Extract selected paths, refusing escaping paths/links and device nodes."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    process = None
    if str(archive).endswith(".zst"):
        process = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
        stream = tarfile.open(fileobj=process.stdout, mode="r|")
    else:
        stream = tarfile.open(archive, "r|*")
    try:
        with stream:
            for member in stream:
                name = member.name.removeprefix("./")
                if not any(name == prefix or name.startswith(prefix.rstrip("/") + "/") for prefix in prefixes):
                    continue
                stream.extract(member, destination, filter="data")
    finally:
        if process:
            process.stdout.close()
            result = process.wait()
            if result:
                raise ValueError(f"zstd failed ({result}): {archive}")


def validate_kernel(root, kernel_release=None):
    """Admission checks for the release payload, not a hardware qualification."""
    modules = Path(root) / "usr/lib/modules" / (kernel_release or PINS["kernel_release"])
    required = (
        "vmlinuz", "modules.dep", "dtbs/t6000-j314s.dtb",
        "kernel/drivers/gpu/drm/apple/appledrm.ko",
        "kernel/drivers/gpu/drm/apple/dcp-fabric-core.ko",
        "kernel/drivers/gpu/drm/drm_dma_helper.ko",
        "kernel/drivers/thunderbolt/thunderbolt.ko",
        "kernel/drivers/soc/apple/apple-sep.ko",
    )
    for name in required:
        if not (modules / name).is_file():
            raise ValueError(f"required Aurora payload missing: {name}")
    dependency = next((line for line in (modules / "modules.dep").read_text().splitlines()
                       if line.startswith("kernel/drivers/gpu/drm/apple/appledrm.ko:")), "")
    if not all(name in dependency for name in ("dcp-fabric-core.ko", "drm_dma_helper.ko")):
        raise ValueError("appledrm dependencies are incomplete")
    dtb = modules / "dtbs/t6000-j314s.dtb"
    def prop(node, key):
        return subprocess.check_output(["fdtget", str(dtb), node, key], text=True).strip()
    if "apple,j314s" not in prop("/", "compatible").split():
        raise ValueError("J314S DTB has the wrong board identity")
    sep = prop("/aliases", "sep")
    if prop(sep, "status") != "okay":
        raise ValueError("SEP is disabled in the release DTB")
    sensor = "/soc/spi@39b108000/fingerprint@0"
    if prop(sensor, "compatible") != "apple,mesa-fingerprint" or prop(sensor, "status") != "okay":
        raise ValueError("J314S fingerprint sensor is not enabled")
    for alias in ("dcpext0", "dcpext1"):
        if prop(prop("/aliases", alias), "apple,typec-dptx-phys") != "0 1 2":
            raise ValueError("J314S Type-C display routes are incomplete")
    return modules
