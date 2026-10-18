#!/usr/bin/python3
"""Export the scoped English F5 source release from one exact Git commit.

Only Git blobs supply package bytes; untracked files, index contents and working
tree edits are never read. No installer, model, native library or test worker is
executed. This creates reviewable artifacts, not a tag or published release.
"""
import argparse
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True

VERSION = "0.0.1"
NAME = "elementaryos-mseries-f5-" + VERSION
ARCHIVE = NAME + ".tar.gz"
SCOPE = "existingM1Pro32GBdesktopSTTonly"
INSTALLER = "mseries/install-dictation-english.py"
PACKAGER = "mseries/releases/package-f5.py"
TEMPLATES = "mseries/releases/v0.0.1/"
RUNTIME_FILES = frozenset((
    "stream-dictate.py", "dictation-input.py", "dictation-input-client.py", "dictation_status.py",
    "dictation_resources.py", "dictation_model.py", "dictation_ane.py", "ane-worker-shim.py",
    "dictation_mlx.py", "mlx-speech-worker.py", "dictation-engine.py", "dictation-launch.py",
    "dictation_review.py", "dictation_pipeline.py", "dictation_live.py", "dictation-panel.py",
))
FIXED_FILES = {
    INSTALLER: INSTALLER,
    "mseries/install-dictation-input.py": "mseries/install-dictation-input.py",
    "mseries/local-ai/machine.py": "mseries/local-ai/machine.py",
    "mseries/dictation/enable-app-input.py": "mseries/dictation/enable-app-input.py",
    "mseries/dictation/mseries-dictation-input.service": "mseries/dictation/mseries-dictation-input.service",
    "LICENSE": "LICENSE",
    "install.sh": TEMPLATES + "install.sh",
    "README.md": TEMPLATES + "README.md",
    "THIRD-PARTY.md": TEMPLATES + "THIRD-PARTY.md",
    TEMPLATES + "preflight.py": TEMPLATES + "preflight.py",
    "tools/package-f5.py": PACKAGER,
}
MAX_BLOB = 2 * 1024 * 1024
MAX_PACKAGE = 16 * 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class PackageError(ValueError):
    """The exact committed source cannot safely form this release."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()


def git(repo, *args):
    # Disable replace objects so the supplied commit identifies the actual tree.
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0")
    # A caller's Git environment must not redirect this explicit repository.
    for key in tuple(env):
        if key.startswith("GIT_") and key not in {"GIT_NO_REPLACE_OBJECTS", "GIT_OPTIONAL_LOCKS"}:
            del env[key]
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        raise PackageError("Git object read failed") from error
    if result.returncode:
        raise PackageError("Requested committed source is unavailable")
    return result.stdout


def source_commit(repo, ref):
    if not isinstance(ref, str) or not COMMIT.fullmatch(ref):
        raise PackageError("--source-ref requires a full lowercase 40-character commit SHA")
    resolved = git(repo, "rev-parse", "--verify", ref + "^{commit}").decode().strip()
    if resolved != ref:
        raise PackageError("--source-ref must identify the exact commit object")
    return resolved


def read_blob(repo, commit, name):
    if (not isinstance(name, str) or "\\" in name or "\x00" in name
            or PurePosixPath(name).is_absolute()
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise PackageError("Unsafe source path")
    row = git(repo, "ls-tree", "-z", commit, "--", name).split(b"\x00")
    if len(row) != 2 or not row[0] or row[1]:
        raise PackageError("Missing or ambiguous committed file: " + name)
    header, actual = row[0].split(b"\t", 1)
    mode, kind, object_id = header.split()
    if actual.decode() != name or mode not in (b"100644", b"100755") or kind != b"blob":
        raise PackageError("Only regular committed files are permitted: " + name)
    size = int(git(repo, "cat-file", "-s", object_id.decode()))
    if not 0 <= size <= MAX_BLOB:
        raise PackageError("Committed source file exceeds its bound: " + name)
    data = git(repo, "cat-file", "blob", object_id.decode())
    if len(data) != size:
        raise PackageError("Committed blob size changed")
    return data, 0o755 if mode == b"100755" else 0o644


def parse(data, label):
    try:
        return ast.parse(data, filename=label)
    except (SyntaxError, ValueError, TypeError, RecursionError) as error:
        raise PackageError("Malformed committed Python source: " + label) from error


def constant(tree, name):
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(values) != 1:
        raise PackageError("Expected one literal committed constant: " + name)
    try:
        return ast.literal_eval(values[0])
    except (ValueError, TypeError, SyntaxError, RecursionError) as error:
        raise PackageError("Committed constant must be a literal: " + name) from error


def runtime_names(installer):
    names = constant(parse(installer, INSTALLER), "RUNTIME_FILES")
    if (not isinstance(names, (tuple, list)) or not all(isinstance(name, str) for name in names)
            or len(names) != len(RUNTIME_FILES) or set(names) != RUNTIME_FILES):
        raise PackageError("Installer runtime files differ from the scoped sixteen-file allowlist")
    return sorted(names)


def release_pins(payload):
    installer = parse(payload[INSTALLER][0], INSTALLER)
    engine_name = "mseries/dictation/dictation-engine.py"
    engine = parse(payload[engine_name][0], engine_name)
    preflight_name = TEMPLATES + "preflight.py"
    preflight = parse(payload[preflight_name][0], preflight_name)
    model_name = constant(engine, "NEMOTRON")
    model_sha = constant(engine, "NEMOTRON_SHA256")
    native_sha = constant(preflight, "NATIVE_SHA256")
    if (model_name != "nemotron-speech-streaming-en-0.6b-Q8_0.gguf"
            or not isinstance(model_sha, str) or not SHA256.fullmatch(model_sha)
            or not isinstance(native_sha, str) or not SHA256.fullmatch(native_sha)):
        raise PackageError("Committed model/native-library pins are malformed")
    urls = {node.value for node in ast.walk(installer) if isinstance(node, ast.Constant)
            and isinstance(node.value, str) and node.value.startswith("https://huggingface.co/")}
    pattern = r"https://huggingface\.co/(handy-computer/nemotron-speech-streaming-en-0\.6b-gguf)/resolve/([0-9a-f]{40})/"
    if len(urls) != 1 or not (match := re.fullmatch(pattern, next(iter(urls)))):
        raise PackageError("Expected one exact pinned Nemotron download origin")
    versions = {}
    for node in ast.walk(preflight):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "metadata" and len(node.args) == 2
                and all(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in node.args)):
            name, version = (arg.value for arg in node.args)
            if name in versions:
                raise PackageError("Ambiguous committed runtime package version")
            versions[name] = version
    if versions != {"transcribe-cpp": "0.4.0", "numpy": "2.5.4"}:
        raise PackageError("Runtime prerequisites differ from scoped v0.0.1 pins")
    return {
        "model": {"repository": match[1], "revision": match[2], "filename": model_name,
                  "sha256": model_sha, "distributed": False},
        "runtime": {"packages": versions, "native_library_sha256": native_sha,
                    "distributed": False,
                    "optional_engines": "existing ANE/MLX assets retained; no assets provisioned"},
    }


def collect(repo, commit):
    installer = read_blob(repo, commit, INSTALLER)
    mapping = dict(FIXED_FILES)
    mapping.update({"mseries/dictation/" + name: "mseries/dictation/" + name
                    for name in runtime_names(installer[0])})
    payload = {}
    for target, source in sorted(mapping.items()):
        payload[target] = installer if source == INSTALLER else read_blob(repo, commit, source)
        try:
            payload[target][0].decode("utf-8")
        except UnicodeDecodeError as error:
            raise PackageError("Source-only payload contains non-text bytes: " + source) from error
        if b"\x00" in payload[target][0]:
            raise PackageError("Source-only payload contains binary bytes: " + source)
        if target.endswith(".py"):
            parse(payload[target][0], source)
    if sum(len(data) for data, _ in payload.values()) > MAX_PACKAGE:
        raise PackageError("Release source exceeds package bound")
    # These public entrypoints must work independently of the source Git mode.
    for name in ("install.sh", "tools/package-f5.py", TEMPLATES + "preflight.py",
                 "mseries/dictation/enable-app-input.py"):
        payload[name] = (payload[name][0], 0o755)
    pins = release_pins(payload)
    manifest = {"version": VERSION, "source_commit": commit, "scope": SCOPE,
                "files": {name: digest(data) for name, (data, _) in sorted(payload.items())}, **pins}
    payload["manifest.json"] = (json_bytes(manifest), 0o644)
    return payload, manifest, mapping


def tar_bytes(payload):
    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name, (data, mode) in sorted(payload.items()):
                entry = tarfile.TarInfo(NAME + "/" + name)
                entry.size, entry.mode, entry.mtime = len(data), mode, 0
                entry.uid = entry.gid = 0
                entry.uname = entry.gname = ""
                archive.addfile(entry, io.BytesIO(data))
    return raw.getvalue()


def build(repo, ref, output):
    """Build from Git objects; the output directory must have no prior artifacts."""
    repo, output = Path(repo), Path(output)
    commit = source_commit(repo, ref)
    payload, manifest, mapping = collect(repo, commit)
    archive = tar_bytes(payload)
    provenance = {
        "schema_version": 1, "version": VERSION, "source_commit": commit, "scope": SCOPE,
        "archive": {"filename": ARCHIVE, "sha256": digest(archive), "size": len(archive)},
        "manifest_sha256": digest(payload["manifest.json"][0]),
        "packager_sha256": manifest["files"]["tools/package-f5.py"],
        "source_files": dict(sorted(mapping.items())),
        "integrity_scope": "manifest files excludes manifest.json; outer archive digest binds all bytes",
        "publication": "local artifacts only; physical F5 acceptance and release publication are separate",
        "model": manifest["model"], "runtime": manifest["runtime"],
    }
    artifacts = {ARCHIVE: archive, "provenance.json": json_bytes(provenance)}
    artifacts["SHA256SUMS"] = "".join(digest(data) + "  " + name + "\n"
                                      for name, data in sorted(artifacts.items())).encode()
    if output.is_symlink() or any(parent.is_symlink() for parent in output.absolute().parents):
        raise PackageError("Output directory must not follow symlinks")
    output.mkdir(parents=True, exist_ok=True)
    if not output.is_dir() or any((output / name).exists() or (output / name).is_symlink() for name in artifacts):
        raise PackageError("Output artifact already exists or output is not a directory")
    # Prepare all bytes before publishing any output; exclusive creation refuses
    # collisions instead of replacing a prior artifact or following a symlink.
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix=".f5-package-", dir=output) as temporary:
            for name, data in artifacts.items():
                staged = Path(temporary) / name
                staged.write_bytes(data)
                staged.chmod(0o644)
            for name in artifacts:
                os.link(Path(temporary) / name, output / name, follow_symlinks=False)
                created.append(output / name)
    except OSError as error:
        for path in created:
            path.unlink()
        raise PackageError("Could not exclusively create release outputs") from error
    return provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref", required=True, help="Exact full lowercase commit SHA; no branch or tag")
    parser.add_argument("--output", required=True, type=Path, help="Directory for the archive and two integrity files")
    args = parser.parse_args(argv)
    try:
        repo = git(Path(__file__).resolve().parent, "rev-parse", "--show-toplevel").decode().strip()
        result = build(repo, args.source_ref, args.output)
    except (PackageError, OSError) as error:
        parser.exit(1, "Source release packaging refused: " + str(error) + "\n")
    print(json.dumps({"archive": result["archive"]["filename"], "source_commit": result["source_commit"],
                      "sha256": result["archive"]["sha256"], "published": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
