#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare, test or build the separate Aurora enhancement candidate; never install."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile

from release import HERE, PINS, asset, extract, sha256, validate_kernel

ENHANCEMENTS = HERE / "enhancements"
MANIFEST = ENHANCEMENTS / "series.json"


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def series():
    data = json.loads(MANIFEST.read_text())
    if data["base_source"] != PINS["kernel_source"]:
        raise ValueError("candidate base and release pins differ: rebase before updating")
    for patch in data["patches"]:
        if sha256(ENHANCEMENTS / "patches" / patch["file"]) != patch["sha256"]:
            raise ValueError(f"candidate patch checksum mismatch: {patch['file']}")
    return data


def settings(data, profile):
    result = dict(data["config"]["candidate"])
    # Explicitly retain the release's disabled eGPU drivers in the normal candidate.
    result.update(DRM_AMDGPU="n", DRM_NOUVEAU="n")
    if profile == "egpu":
        result.update(data["config"]["egpu"])
    result.update(LOCALVERSION='""', LOCALVERSION_AUTO="n")
    return result


def configure(text, options):
    """Update the actual full recipe config, not just the unused asahi fragment."""
    keys = {"CONFIG_" + key for key in options}
    lines = [line for line in text.splitlines()
             if not any(line.startswith(key + "=") or line == f"# {key} is not set" for key in keys)]
    for key, value in options.items():
        lines.append(f"# CONFIG_{key} is not set" if value == "n" else f"CONFIG_{key}={value}")
    return "\n".join(lines) + "\n"


def config_values(text):
    values = {}
    for line in text.splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            values[key.removeprefix("CONFIG_")] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            values[line[9:-11]] = "n"
    return values


def config_gate(text, data, profile):
    values = config_values(text)
    required = settings(data, profile)
    required.update(ARM64_16K_PAGES="y", RUST="y", DRM_ASAHI="y", DRM_APPLE="m",
                    DRM_APPLE_FABRIC_CORE="m", APPLE_SEP="m", USB4="m", USB4_APPLE_SOC="m")
    for key, value in required.items():
        if values.get(key) != value:
            raise ValueError(f"resolved CONFIG_{key}: expected {value}, got {values.get(key)}")


def fresh(path, *, outside=None):
    path = Path(path).resolve()
    if outside and (path == outside or outside in path.parents):
        raise ValueError("artifact output must be outside the prepared source/build tree")
    if path.exists():
        raise ValueError(f"output must not exist: {path}")
    if path == Path("/boot") or Path("/boot") in path.parents or Path("/Volumes") in path.parents:
        raise ValueError("use a private build directory, not a boot or mounted-volume path")
    path.mkdir(parents=True)
    return path


def prepare(cache, output, profile, offline):
    data = series()
    # Verify both original inputs before creating the output directory.
    inputs = {kind: asset(cache, kind, offline=offline) for kind in ("source", "recipe")}
    root = fresh(output)
    upstream = "aurora-linux-" + PINS["kernel_source"]
    extract(inputs["source"], root, (upstream,))
    source = root / "source"
    (root / upstream).rename(source)
    recipe = root / "recipe"
    extract(inputs["recipe"], recipe, ("config", "PKGBUILD", "rust-toolchain.toml", "linux-aurora-phram.conf"))
    if sha256(recipe / "config") != PINS["recipe_config_sha256"]:
        raise ValueError("upstream recipe config mismatch")
    selected = [patch for patch in data["patches"] if patch["profile"] == "candidate" or profile == "egpu"]
    modified = set()
    for patch in selected:
        path = ENHANCEMENTS / "patches" / patch["file"]
        # Each series member must apply without fuzz; do not silently skip conflicts.
        run("git", "apply", "--check", path, cwd=source)
        run("git", "apply", path, cwd=source)
        stats = subprocess.check_output(["git", "apply", "--numstat", str(path)], text=True, cwd=source)
        modified.update(line.split("\t", 2)[2] for line in stats.splitlines())
    # A distinct modules directory prevents overwriting the released .20 modules.
    if list(source.glob("localversion*")):
        raise ValueError("unexpected upstream localversion: review version composition")
    suffix = data["kernel_release"][profile].removeprefix("7.1.12")
    (source / "localversion.elementary").write_text(suffix + "\n")
    modified.add("localversion.elementary")
    config = configure((recipe / "config").read_text(), settings(data, profile))
    config_gate(config, data, profile)
    (root / "build").mkdir()
    (root / "build/.config").write_text(config)
    shutil.copy2(recipe / "rust-toolchain.toml", source / "rust-toolchain.toml")
    modified.add("rust-toolchain.toml")
    receipt = {"profile": profile, "kernel_release": data["kernel_release"][profile],
               "base_pins": PINS, "series_sha256": sha256(MANIFEST), "patches": selected,
               "modified_files": {name: sha256(source / name) for name in sorted(modified)},
               "prepared_config_sha256": sha256(root / "build/.config"),
               "status": "prepared only; no ARM64 kernel build or hardware boot"}
    (root / "candidate.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Prepared {receipt['kernel_release']} at {root}", flush=True)
    return root


def verify(root):
    data = series()
    receipt = json.loads((root / "candidate.json").read_text())
    if receipt["series_sha256"] != sha256(MANIFEST) or receipt["base_pins"] != PINS:
        raise ValueError("prepared candidate no longer matches the repository inputs")
    for name, digest in receipt["modified_files"].items():
        if sha256(root / "source" / name) != digest:
            raise ValueError(f"prepared source changed: {name}")
    if sha256(root / "build/.config") != receipt["prepared_config_sha256"]:
        raise ValueError("prepared configuration changed: start a fresh build")
    return data, receipt


def check(root):
    verify(root)
    source = root / "source"
    # These are the upstream tests of production Rust modules, not duplicated policy.
    with tempfile.TemporaryDirectory(prefix="aurora-host-tests-") as temporary:
        binary = Path(temporary) / "m3-runtime-tests"
        run("rustc", "--edition=2021", "--test", "-D", "warnings",
            source / "tools/asahi/m3-runtime-tests.rs", "-o", binary, cwd=root)
        run(binary)
    run("python3", ENHANCEMENTS / "check-macsmc.py", source)


def build(root, output, jobs):
    if platform.system() != "Linux" or platform.machine() not in ("aarch64", "arm64"):
        raise ValueError("full build requires native ARM64 Linux; use the GitHub workflow")
    data, receipt = verify(root)
    output = fresh(output, outside=root)
    source, out = root / "source", root / "build"
    env = dict(os.environ, ARCH="arm64", LLVM="1", RUSTUP_TOOLCHAIN="1.93.1",
               KBUILD_BUILD_USER="elementary-mseries", KBUILD_BUILD_HOST="ci",
               KBUILD_BUILD_TIMESTAMP="Sat, 17 Oct 2026 00:00:00 +0000")
    version = subprocess.check_output(["rustc", "--version"], text=True, env=env)
    if not version.startswith("rustc 1.93.1 "):
        raise ValueError("install pinned Rust 1.93.1 and rust-src")
    def make(*targets):
        run("make", "-C", source, f"O={out}", f"-j{jobs}", *targets, env=env)
    make("olddefconfig")
    config_gate((out / ".config").read_text(), data, receipt["profile"])
    actual = subprocess.check_output(["make", "-s", "-C", str(source), f"O={out}", "kernelrelease"], text=True, env=env).strip()
    if actual != receipt["kernel_release"]:
        raise ValueError(f"unexpected kernel release: {actual}")
    make("rustavailable")
    # Capture complete corresponding source and the resolved config before any compilation.
    shutil.copy2(out / ".config", source / "elementary-build.config")
    shutil.copy2(root / "candidate.json", source / "elementary-provenance.json")
    source_archive = output / f"linux-{actual}-source.tar.gz"
    with tarfile.open(source_archive, "w:gz") as archive:
        archive.add(source, arcname=f"linux-{actual}")
    make("Image", "modules", "dtbs")
    with tempfile.TemporaryDirectory(prefix="aurora-candidate-package-") as temporary:
        payload = Path(temporary) / "payload"
        control = Path(temporary) / "control"
        control.mkdir()
        make(f"INSTALL_MOD_PATH={payload / 'usr'}", "INSTALL_MOD_STRIP=1", "modules_install")
        modules = payload / "usr/lib/modules" / actual
        for name in ("build", "source"):
            (modules / name).unlink(missing_ok=True)
        shutil.copy2(out / "arch/arm64/boot/Image", modules / "vmlinuz")
        (modules / "dtbs").mkdir()
        for dtb in (out / "arch/arm64/boot/dts/apple").glob("*.dtb"):
            shutil.copy2(dtb, modules / "dtbs" / dtb.name)
        run("depmod", "-b", payload / "usr", actual)
        validate_kernel(payload, actual)
        modprobe = payload / "usr/lib/modprobe.d"
        modprobe.mkdir(parents=True)
        shutil.copy2(root / "recipe/linux-aurora-phram.conf", modprobe)
        name = "linux-image-elementary-aurora-enhancements" + ("-egpu" if receipt["profile"] == "egpu" else "")
        docs = payload / "usr/share/doc" / name
        docs.mkdir(parents=True)
        shutil.copy2(source / "COPYING", docs)
        shutil.copytree(source / "LICENSES", docs / "LICENSES")
        shutil.copytree(ENHANCEMENTS, docs / "enhancements")
        shutil.copytree(root / "recipe", docs / "upstream-recipe")
        shutil.copy2(out / ".config", docs / "build.config")
        shutil.copy2(root / "candidate.json", docs)
        (docs / "README").write_text("Experimental source-built kernel. No maintainer scripts or /boot files.\n"
                                    "Not supported by the fixed-release Aurora20 installer/stager.\n"
                                    "Hardware qualification and a matched boot-chain review are required.\n")
        version = "7.1.12+elementary.aurora20.enh1-1"
        size = sum(path.stat().st_size for path in payload.rglob("*") if path.is_file()) // 1024
        (control / "control").write_text(f"Package: {name}\nVersion: {version}\nArchitecture: arm64\n"
            "Maintainer: ElementaryOS MSeries contributors <builder@localhost>\n"
            f"Installed-Size: {size}\nSection: kernel\nPriority: optional\nDepends: kmod\n"
            "Description: Experimental Aurora enhancement kernel payload\n"
            " Distinct modules directory, no boot hooks; requires explicit boot-chain staging.\n")
        spec = importlib.util.spec_from_file_location("aurora_package", HERE / "package-release.py")
        package_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package_module)
        package = output / f"{name}_{version}_arm64.deb"
        package_module.write_deb(package, control, payload)
    receipt.update(status="ARM64 Image/modules/DTBs built; no hardware boot", package=package.name,
                   package_sha256=sha256(package), source_sha256=sha256(source_archive),
                   resolved_config_sha256=sha256(out / ".config"))
    receipt["rustc"] = subprocess.check_output(["rustc", "--version"], text=True, env=env).strip()
    receipt["clang"] = subprocess.check_output(["clang", "--version"], text=True, env=env).splitlines()[0]
    (output / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
    shutil.copy2(out / ".config", output / "build.config")
    shutil.copytree(ENHANCEMENTS, output / "enhancements")
    (output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sorted(output.iterdir())
                                                  if path.is_file() and path.name != "SHA256SUMS"))
    print(f"Built {package}; no installation or boot changes", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--cache", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--profile", choices=("candidate", "egpu"), default="candidate")
    prep.add_argument("--offline", action="store_true")
    for command in ("check", "build"):
        sub = commands.add_parser(command)
        sub.add_argument("--prepared", type=Path, required=True)
        if command == "build":
            sub.add_argument("--output", type=Path, required=True)
            sub.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.cache, args.output, args.profile, args.offline)
    elif args.command == "check":
        check(args.prepared.resolve())
    else:
        if args.jobs < 1:
            parser.error("--jobs must be positive")
        build(args.prepared.resolve(), args.output, args.jobs)


if __name__ == "__main__":
    main()
