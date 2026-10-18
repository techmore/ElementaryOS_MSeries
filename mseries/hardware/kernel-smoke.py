#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scoped J314S GPU shader/readback and temporary-file fsync smoke tests.

Requires an existing matching read-only receipt, a C compiler and EGL/GLES dev
files. No sensor probe, suspend, boot selection, audio or display-mode changes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "aurora"))
import qualification as q


def run(receipt_path, work_dir, output, kernel_image, boot_image):
    if output.exists():
        raise ValueError("choose a new hardware-test receipt")
    record = json.loads(receipt_path.read_text())
    identity = q.validate_receipt(record)
    boot_id = q.read("/proc/sys/kernel/random/boot_id")
    if boot_id != record["boot_id"] or q.read("/proc/sys/kernel/osrelease") != identity["kernel_release"]:
        raise ValueError("the running boot differs from the supplied receipt")
    if q.digest(kernel_image) != identity["kernel_image_sha256"] or q.digest(boot_image) != identity["boot_payload_sha256"]:
        raise ValueError("kernel or boot payload changed")
    for name, expected in identity["modules"].items():
        if q.digest(Path("/usr/lib/modules") / identity["kernel_release"] / name) != expected:
            raise ValueError("installed driver/DTB files changed")
    before = q.context(Path("/"))
    if before["parameters"] != identity["runtime_parameters"]:
        raise ValueError("runtime feature parameters changed")
    work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work_dir, prefix="kernel-smoke-") as tmp:
        tmp = Path(tmp)
        binary = tmp / "gpu-readback"
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "egl", "glesv2"], text=True))
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", str(HERE / "gpu-readback.c"), "-o", str(binary), *flags], check=True)
        lines = subprocess.check_output([str(binary)], text=True).splitlines()
        gpu = dict(line.split("=", 1) for line in lines)
        data = bytes(range(256)) * 4096
        storage = tmp / "io-check"
        with storage.open("xb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        expected = hashlib.sha256(data).hexdigest()
        if q.digest(storage) != expected:
            raise ValueError("temporary-file fsync/readback mismatch")
    if q.read("/proc/sys/kernel/random/boot_id") != boot_id:
        raise ValueError("boot changed during smoke tests")
    after = q.context(Path("/"))
    if before["parameters"] != after["parameters"]:
        raise ValueError("runtime feature parameters changed during testing")
    def controls(data):
        result = json.loads(json.dumps(data))
        for supply in result["power_supplies"].values():
            supply.pop("energy_now", None)
            supply.pop("capacity", None)
        return result
    result = {"schema": 1, "kind": "hardware-test", "captured_at": datetime.now(timezone.utc).isoformat(),
              "identity": identity, "identity_sha256": record["identity_sha256"], "boot_id": boot_id,
              "status": "hardware-tested-scoped; incomplete qualification", "controls_unchanged": controls(before) == controls(after),
              "context_before": before, "context_after": after,
              "checks": {"gpu_readback_smoke": {"result": "pass", "scope": "surfaceless GLES shader draw and 16-pixel RGBA readback; not GPU soak or compositor acceptance", **gpu},
                         "storage_fsync_smoke": {"result": "pass", "scope": "1 MiB temporary file fsync and SHA256 readback on work filesystem; not destructive media, suspend, or recovery testing", "bytes": len(data), "sha256": expected}},
              "source_receipt": {"file": receipt_path.name, "sha256": q.digest(receipt_path)},
              "power_improvement_claim": False}
    q.write_new(output, result)
    print(json.dumps(result["checks"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kernel-image", type=Path, required=True)
    parser.add_argument("--boot-image", type=Path, required=True)
    args = parser.parse_args()
    run(args.receipt, args.work, args.output, args.kernel_image, args.boot_image)
