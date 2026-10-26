#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare the pinned unified72 J314S trial offline; never install, arm or reboot.

The release identity and trial slug come from series.json. Use the newest matching
dated native-build receipt when present; wip2 retains its historical date-only receipt."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
BASE = "7.1.12-elementary-aurora20-enh1"
SERIES = json.loads((HERE / "series.json").read_text())
NEW = SERIES["kernel_release"]["unified72"]
SLUG = NEW.split("elementary-", 1)[1]          # e.g. aurora72-wip3
TRIAL_ENTRY = f"elementary-{SLUG}-trial"
RECEIPTS = sorted(HERE.glob(f"native-build-{SLUG.split('-')[1]}-*.json"))
NATIVE_RECEIPT = RECEIPTS[-1] if RECEIPTS else HERE / "native-build-2026-10-21.json"
BASE_SHA = "06a885396f5613154b2fbb6774744efde95a9d25512698d297b3f14da0d4f3aa"
BOOT_SHA = "9c9c2d01c3bdb2784daf99cecd6f0e2327eb8f148ea43c8e522e5bae09a14d5f"
TRANSITIONS = {
    "kernel/crypto/fcrypt.ko": "Absent from this candidate; not needed by the observed AES-XTS LUKS2 root.",
    "kernel/crypto/pcbc.ko": "Absent from this candidate; not needed by the observed AES-XTS LUKS2 root.",
    "kernel/lib/raid6/raid6_pq.ko": "Relocated to kernel/lib/raid/raid6/raid6_pq.ko; retained through the new Btrfs dependency closure.",
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(args):
    os.umask(0o077)
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(Path(p)) for p in ("/boot", "/usr", "/etc", "/Volumes")):
        raise ValueError("choose a fresh private work directory outside live system paths")
    if args.root_cipher != "aes-xts-plain64":
        raise ValueError("this transition policy only covers an observed AES-XTS root")
    native = json.loads(NATIVE_RECEIPT.read_text())
    provenance = native["provenance"]
    if provenance["kernel_release"] != NEW or digest(args.package.read_bytes()) != provenance["package_sha256"]:
        raise ValueError("candidate package identity differs from the independently audited artifact")
    baseline = args.baseline.read_bytes()
    boot = args.existing_boot.read_bytes()
    if digest(baseline) != BASE_SHA or digest(boot) != BOOT_SHA:
        raise ValueError("working initramfs/shared boot payload changed; review this preparation again")
    modules = args.module_root.resolve() / "lib/modules" / NEW
    config = (args.module_root / f"share/doc/linux-image-elementary-{SLUG}/build.config").read_bytes()
    if digest(config) != provenance["resolved_config_sha256"]:
        raise ValueError("resolved candidate config changed")
    for key, value in {"CRYPTO_AES": "y", "CRYPTO_XTS": "y", "CRYPTO_SHA256": "y",
                       "NVME_APPLE": "y", "DM_CRYPT": "m", "BTRFS_FS": "m",
                       "PINCTRL_APPLE_GPIO": "y", "APPLE_DOCKCHANNEL": "y"}.items():
        if f"CONFIG_{key}={value}\n".encode() not in config:
            raise ValueError("required boot/unlock config missing: " + key)
    trial = load("trial_initrd", HERE.parent / "prepare-trial-initrd.py")
    audit = load("trial_initrd_audit", HERE.parent / "audit-trial-initrd.py")
    early, compressed = trial.split_image(baseline)
    rows, trailer = trial.newc.parse(gzip.decompress(compressed))
    prefix = f"usr/lib/modules/{BASE}/"
    selected = {trial.newc.canonical(n)[len(prefix):] for n, v, d in rows
                if trial.newc.canonical(n).startswith(prefix + "kernel/") and stat.S_ISREG(v[1])}
    missing = {name for name in selected if not (modules / name).is_file()}
    if missing != set(TRANSITIONS):
        raise ValueError("unexpected module transitions: " + repr(sorted(missing)))
    relocated = "kernel/lib/raid/raid6/raid6_pq.ko"
    if subprocess.check_output(["modinfo", "-F", "name", str(modules / relocated)], text=True).strip() != "raid6_pq":
        raise ValueError("relocated RAID6 module identity differs")
    # Only module selectors change. The later independent audit compares against
    # the ORIGINAL working image, not this intermediate filtered image.
    retained = [(n, v, d) for n, v, d in rows
                if trial.newc.canonical(n) not in {prefix + name for name in TRANSITIONS}]
    output.mkdir(mode=0o700, parents=True)
    filtered = output / "baseline-module-selectors.img"
    filtered.write_bytes(early + gzip.compress(trial.newc.encode(retained, trailer), compresslevel=6, mtime=0))
    initrd = output / ("initrd.img-" + NEW)
    trial.prepare(filtered, args.module_root, BASE, NEW, initrd, output / "module-preparation.json")
    result = audit.audit(baseline, initrd.read_bytes(), modules)
    _, entries = audit.entries(initrd.read_bytes())
    candidate_prefix = f"usr/lib/modules/{NEW}/"
    module_hashes = {name: digest(data) for name, (values, data) in entries.items()
                     if name.startswith(candidate_prefix + "kernel/") and stat.S_ISREG(values[1])}
    if candidate_prefix + relocated not in module_hashes:
        raise ValueError("Btrfs RAID6 dependency not included")
    # Verify every embedded module directly against the original pinned package.
    seen = set()
    with subprocess.Popen(["dpkg-deb", "--fsys-tarfile", str(args.package)], stdout=subprocess.PIPE) as process:
        with tarfile.open(fileobj=process.stdout, mode="r|") as package_tar:
            for member in package_tar:
                name = member.name.removeprefix("./")
                if member.isfile() and name in module_hashes:
                    if digest(package_tar.extractfile(member).read()) != module_hashes[name]:
                        raise ValueError("initramfs module differs from audited package: " + name)
                    seen.add(name)
        if process.wait() or seen != set(module_hashes):
            raise ValueError("incomplete package/module verification")
    image = modules / "vmlinuz"
    if digest(image.read_bytes()) != native["package"]["image_sha256"]:
        raise ValueError("candidate Image differs from audited artifact")
    shutil.copy2(image, output / f"vmlinuz-{SLUG}")
    (output / "boot.bin.rollback").write_bytes(boot)
    original_grub = args.custom_grub.read_text()
    match = re.search(r"^menuentry '[^']*DEV: Aurora \.20-enh1[^']*' --id elementary-aurora20-enh1 \{\n.*?^\}", original_grub, re.M | re.S)
    if not match or TRIAL_ENTRY in original_grub:
        raise ValueError("expected current DEV entry not found or trial already exists")
    block = match.group().replace(match.group().splitlines()[0], f"menuentry 'elementary OS - TRIAL: Aurora 7.2 {SLUG.split('-')[1]}' --id {TRIAL_ENTRY} {{")
    block = block.replace("/vmlinuz-aurora20-enh1", f"/vmlinuz-{SLUG}").replace("/initrd.img-" + BASE, "/initrd.img-" + NEW)
    proposed = original_grub.rstrip() + "\n\n" + block + "\n"
    (output / "custom.cfg.proposed").write_text(proposed)
    subprocess.run(["grub-script-check", str(output / "custom.cfg.proposed")], check=True)
    result.update(kind=f"offline-j314s-{SLUG.split('-')[1]}-boot-preparation", package_sha256=provenance["package_sha256"],
                  candidate_image_sha256=native["package"]["image_sha256"],
                  resolved_config_sha256=provenance["resolved_config_sha256"],
                  root_cipher=args.root_cipher, original_baseline_sha256=BASE_SHA,
                  explicit_module_transitions=TRANSITIONS, package_module_bytes_verified=True,
                  module_sha256=module_hashes, shared_boot_sha256=BOOT_SHA,
                  shared_boot_change_required=False, shared_boot_policy="Retain exact current 7.1 DTB/m1n1/U-Boot payload; legacy DART source checks are separate evidence.",
                  original_custom_grub_sha256=digest(original_grub.encode()),
                  proposed_custom_grub_sha256=digest(proposed.encode()),
                  persistent_default="elementary-aurora20", trial_entry=TRIAL_ENTRY,
                  installed=False, armed=False, rebooted=False,
                  status="prepared offline and original-unlock/module-package audit passed; no hardware boot qualification")
    (output / "preparation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "candidate_sha256", "verified_module_count")}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("package", "baseline", "module-root", "existing-boot", "custom-grub", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--root-cipher", required=True)
    prepare(parser.parse_args())
