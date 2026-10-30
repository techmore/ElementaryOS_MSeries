#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare, test or build the separate Aurora enhancement candidate; never install."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime

from release import HERE, PINS, asset, extract, sha256, validate_kernel

ENHANCEMENTS = HERE / "enhancements"
MANIFEST = ENHANCEMENTS / "series.json"
SOURCE_DOWNLOAD_ATTEMPTS = 4
MAX_SOURCE_RETRY_DELAY = 30
RETRYABLE_SOURCE_HTTP_ERRORS = {429, 500, 502, 503, 504}


def source_retry_delay(error, attempt):
    """Return a bounded retry delay, or None when Retry-After exceeds our wait budget."""
    retry_after = error.headers.get("Retry-After") if error.headers else None
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
            except (OverflowError, TypeError, ValueError):
                delay = None
        if delay is not None:
            delay = max(0.0, delay)
            return delay if delay <= MAX_SOURCE_RETRY_DELAY else None
    return min(float(2 ** (attempt + 1)), float(MAX_SOURCE_RETRY_DELAY))


def download_pinned_source(url, destination, *, attempts=SOURCE_DOWNLOAD_ATTEMPTS):
    """Download an immutable source archive with bounded HTTP 429/5xx retries."""
    if attempts < 1:
        raise ValueError("source download attempts must be positive")
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=120) as source, Path(destination).open("wb") as target:
                shutil.copyfileobj(source, target)
            return
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_SOURCE_HTTP_ERRORS or attempt + 1 >= attempts:
                error.close()
                raise
            delay = source_retry_delay(error, attempt)
            if delay is None:
                error.close()
                raise
            print(f"Pinned source download returned HTTP {error.code}; retrying in {delay:g}s", flush=True)
            error.close()
            time.sleep(delay)


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def fetch_pinned_source_from_git(source_pin, destination):
    """Archive an exact Git commit after verifying its commit and tree pins."""
    required = ("git_url", "commit", "git_tree_sha1", "archive_root")
    if any(not source_pin.get(key) for key in required):
        raise ValueError("pinned source has no complete Git fallback identity")
    with tempfile.TemporaryDirectory(prefix="aurora-pinned-source-") as temporary:
        repository = Path(temporary) / "repository"
        run("git", "init", "--quiet", "--initial-branch=source", repository)
        run("git", "-C", repository, "fetch", "--quiet", "--depth=1", "--no-tags",
            source_pin["git_url"], source_pin["commit"])
        commit = subprocess.run(["git", "-C", str(repository), "rev-parse", "FETCH_HEAD"],
                                 check=True, capture_output=True, text=True).stdout.strip()
        if commit != source_pin["commit"]:
            raise ValueError("Git source fallback resolved a different commit")
        tree = subprocess.run(["git", "-C", str(repository), "rev-parse", "FETCH_HEAD^{tree}"],
                              check=True, capture_output=True, text=True).stdout.strip()
        if tree != source_pin["git_tree_sha1"]:
            raise ValueError("Git source fallback tree checksum mismatch")
        run("git", "-C", repository, "archive", "--format=tar",
            f"--prefix={source_pin['archive_root']}/", f"--output={destination}", "FETCH_HEAD")


def obtain_pinned_source(source_pin, cache, offline):
    """Return (archive path, cleanup path) for a checksum-verified pinned source."""
    path = Path(cache) / source_pin["name"]
    if path.exists():
        if sha256(path) != source_pin["sha256"]:
            raise ValueError("unified source checksum mismatch")
        return path, None
    if offline:
        raise ValueError(f"missing cached input: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    fallback = path.with_name(f".{path.name}.git.tar.part")
    temporary.unlink(missing_ok=True)
    fallback.unlink(missing_ok=True)
    try:
        try:
            download_pinned_source(source_pin["url"], temporary)
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_SOURCE_HTTP_ERRORS or not source_pin.get("git_url"):
                error.close()
                raise
            print(f"Pinned source codeload remained HTTP {error.code}; trying the exact Git tree",
                  flush=True)
            error.close()
            try:
                fetch_pinned_source_from_git(source_pin, fallback)
            except Exception:
                fallback.unlink(missing_ok=True)
                raise
            return fallback, fallback
        if sha256(temporary) != source_pin["sha256"]:
            raise ValueError("unified source checksum mismatch")
        temporary.replace(path)
        return path, None
    finally:
        temporary.unlink(missing_ok=True)


def tree_digest(root):
    """Bind every source file, executable bit and symlink, not only patch hunks."""
    root = Path(root)
    result = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            entry = [str(path.relative_to(root)), "symlink", os.readlink(path)]
        elif path.is_file():
            entry = [str(path.relative_to(root)), path.stat().st_mode & 0o111, sha256(path)]
        else:
            continue
        result.update(json.dumps(entry, separators=(",", ":")).encode() + b"\n")
    return result.hexdigest()


def manifest(profile):
    return (HERE / "unified72" / {"unified72": "series.json",
            "unified72-egpu": "egpu-series.json", "unified72-connectx": "connectx-series.json"}[profile]
            if profile in ("unified72", "unified72-egpu", "unified72-connectx") else MANIFEST)


def series(profile="candidate"):
    path = manifest(profile)
    data = json.loads(path.read_text())
    if data["base_source"] != PINS["kernel_source"]:
        raise ValueError("candidate base and release pins differ: rebase before updating")
    for patch in data["patches"]:
        if sha256(path.parent / "patches" / patch["file"]) != patch["sha256"]:
            raise ValueError(f"candidate patch checksum mismatch: {patch['file']}")
    return data


def settings(data, profile):
    result = dict(data["config"]["candidate"])
    # Explicitly retain the release's disabled eGPU drivers in the normal candidate.
    result.update(DRM_AMDGPU="n", DRM_NOUVEAU="n")
    if profile in ("egpu", "unified72-egpu"):
        result.update(data["config"]["egpu"])
    if profile == "unified72-connectx":
        result.update(data["config"]["connectx"])
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
    data = series(profile)
    # Verify both original inputs before creating the output directory.
    inputs = {"recipe": asset(cache, "recipe", offline=offline)}
    source_pin = data.get("source")
    temporary_source = None
    if source_pin:
        inputs["source"], temporary_source = obtain_pinned_source(source_pin, cache, offline)
    else:
        inputs["source"] = asset(cache, "source", offline=offline)
    source_fetch_method = "release-asset"
    if source_pin:
        source_fetch_method = "pinned-git-tree" if temporary_source else "pinned-archive-sha256"
    source_archive_sha256 = sha256(inputs["source"])
    try:
        root = fresh(output)
        upstream = source_pin["archive_root"] if source_pin else "aurora-linux-" + PINS["kernel_source"]
        extract(inputs["source"], root, (upstream,))
    finally:
        if temporary_source:
            temporary_source.unlink(missing_ok=True)
    source = root / "source"
    (root / upstream).rename(source)
    recipe = root / "recipe"
    extract(inputs["recipe"], recipe, ("config", "PKGBUILD", "rust-toolchain.toml", "linux-aurora-phram.conf"))
    if sha256(recipe / "config") != PINS["recipe_config_sha256"]:
        raise ValueError("upstream recipe config mismatch")
    selected = [patch for patch in data["patches"] if patch["profile"] == "candidate" or profile == "egpu"]
    modified = set()
    for patch in selected:
        path = manifest(profile).parent / "patches" / patch["file"]
        # Each series member must apply without fuzz; do not silently skip conflicts.
        run("git", "apply", "--check", path, cwd=source)
        run("git", "apply", path, cwd=source)
        stats = subprocess.check_output(["git", "apply", "--numstat", str(path)], text=True, cwd=source)
        modified.update(line.split("\t", 2)[2] for line in stats.splitlines())
    # A distinct modules directory prevents overwriting the released .20 modules.
    if list(source.glob("localversion*")):
        raise ValueError("unexpected upstream localversion: review version composition")
    makefile = (source / "Makefile").read_text()
    base_version = ".".join(re.search(rf"^{key}\s*=\s*(\d+)$", makefile, re.M)[1]
                            for key in ("VERSION", "PATCHLEVEL", "SUBLEVEL"))
    if not data["kernel_release"][profile].startswith(base_version + "-"):
        raise ValueError("kernel release does not match source Makefile")
    suffix = data["kernel_release"][profile].removeprefix(base_version)
    (source / "localversion.elementary").write_text(suffix + "\n")
    modified.add("localversion.elementary")
    config = configure((recipe / "config").read_text(), settings(data, profile))
    config_gate(config, data, profile)
    (root / "build").mkdir()
    (root / "build/.config").write_text(config)
    shutil.copy2(recipe / "rust-toolchain.toml", source / "rust-toolchain.toml")
    modified.add("rust-toolchain.toml")
    receipt = {"profile": profile, "kernel_release": data["kernel_release"][profile],
               "base_pins": PINS, "series_sha256": sha256(manifest(profile)), "patches": selected,
               "source_pin": source_pin,
               "source_fetch_method": source_fetch_method,
               "source_archive_sha256": source_archive_sha256,
               "source_tree_sha256": tree_digest(source),
               "modified_files": {name: sha256(source / name) for name in sorted(modified)},
               "prepared_config_sha256": sha256(root / "build/.config"),
               "status": "prepared only; no ARM64 kernel build or hardware boot"}
    (root / "candidate.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Prepared {receipt['kernel_release']} at {root}", flush=True)
    return root


def verify(root):
    receipt = json.loads((root / "candidate.json").read_text())
    profile = receipt.get("profile", "candidate")
    data = series(profile)
    if receipt["series_sha256"] != sha256(manifest(profile)) or receipt["base_pins"] != PINS or receipt.get("source_pin") != data.get("source"):
        raise ValueError("prepared candidate no longer matches the repository inputs")
    for name, digest in receipt["modified_files"].items():
        if sha256(root / "source" / name) != digest:
            raise ValueError(f"prepared source changed: {name}")
    if not receipt.get("source_tree_sha256") or tree_digest(root / "source") != receipt["source_tree_sha256"]:
        raise ValueError("prepared source tree changed or receipt missing: prepare afresh")
    if sha256(root / "build/.config") != receipt["prepared_config_sha256"]:
        raise ValueError("prepared configuration changed: start a fresh build")
    return data, receipt


def check(root):
    data, receipt = verify(root)
    source = root / "source"
    # These are the upstream tests of production Rust modules, not duplicated policy.
    with tempfile.TemporaryDirectory(prefix="aurora-host-tests-") as temporary:
        for index, test in enumerate(data.get("host_tests", ["tools/asahi/m3-runtime-tests.rs"])):
            binary = Path(temporary) / f"production-tests-{index}"
            run("rustc", "--edition=2021", "--test", "-D", "warnings", source / test, "-o", binary, cwd=root)
            run(binary)
    if receipt["profile"] not in ("unified72", "unified72-egpu", "unified72-connectx"):
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
        name = data.get("debian_package", "linux-image-elementary-aurora-enhancements" + ("-egpu" if receipt["profile"] == "egpu" else ""))
        # A shared filename would make dpkg reject co-installation with .20
        # (or the other candidate profile), even when its content is identical.
        shutil.copy2(root / "recipe/linux-aurora-phram.conf", modprobe / f"{name}-phram.conf")
        docs = payload / "usr/share/doc" / name
        docs.mkdir(parents=True)
        shutil.copy2(source / "COPYING", docs)
        shutil.copytree(source / "LICENSES", docs / "LICENSES")
        shutil.copytree(manifest(receipt["profile"]).parent, docs / "enhancements")
        shutil.copytree(root / "recipe", docs / "upstream-recipe")
        shutil.copy2(out / ".config", docs / "build.config")
        shutil.copy2(root / "candidate.json", docs)
        (docs / "README").write_text("Experimental source-built kernel. No maintainer scripts or /boot files.\n"
                                    "Not supported by the fixed-release Aurora20 installer/stager.\n"
                                    "Hardware qualification and a matched boot-chain review are required.\n")
        version = data.get("debian_version", "7.1.12+elementary.aurora20.enh1-1")
        size = sum(path.stat().st_size for path in payload.rglob("*") if path.is_file()) // 1024
        (control / "control").write_text(f"Package: {name}\nVersion: {version}\nArchitecture: arm64\n"
            "Maintainer: ElementaryOS MSeries contributors <builder@localhost>\n"
            f"Installed-Size: {size}\nSection: kernel\nPriority: optional\nDepends: kmod\n"
            "Description: Experimental Aurora enhancement kernel payload\n"
            " Distinct modules directory, no boot hooks; requires explicit boot-chain staging.\n")
        package = output / f"{name}_{version}_arm64.deb"
        shutil.copytree(control, payload / "DEBIAN")
        # Native Debian packaging supports fast zstd and parallel compression;
        # this does not run package installation or concurrent dpkg transactions.
        run("dpkg-deb", "-Zzstd", "-z3", f"--threads-max={jobs}", "--root-owner-group",
            "--build", payload, package,
            env=dict(env, SOURCE_DATE_EPOCH="1792195200"))
    receipt.update(status="ARM64 Image/modules/DTBs built; no hardware boot", package=package.name,
                   package_sha256=sha256(package), source_sha256=sha256(source_archive),
                   resolved_config_sha256=sha256(out / ".config"))
    receipt["rustc"] = subprocess.check_output(["rustc", "--version"], text=True, env=env).strip()
    receipt["clang"] = subprocess.check_output(["clang", "--version"], text=True, env=env).splitlines()[0]
    receipt["package_compression"] = {"format": "zstd", "level": 3, "max_threads": jobs}
    (output / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
    shutil.copy2(out / ".config", output / "build.config")
    shutil.copytree(manifest(receipt["profile"]).parent, output / "enhancements")
    (output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sorted(output.iterdir())
                                                  if path.is_file() and path.name != "SHA256SUMS"))
    print(f"Built {package}; no installation or boot changes", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--cache", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--profile", choices=("candidate", "egpu", "unified72", "unified72-egpu", "unified72-connectx"), default="candidate")
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
