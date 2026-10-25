#!/usr/bin/env python3
"""Qualify real seed-to-list generation against signed archive snapshots.

Acquisition and the unchanged Germinate/debootstrap build are test oracles.
Rust consumes the exact same decoded index bytes and captured bootstrap sets.
Only hash/identity receipts are exported; source/index text stays temporary.
"""

import argparse
import bz2
import configparser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import importlib.util
import io
import json
import lzma
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


upstream = module("upstream_deb", "test-upstream-deb-parity.py")
parity = upstream.parity

REFERENCE_RUNNER = r'''
import sys, subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from germinate.scripts.germinate_update_metapackage import main
indices = Path(sys.argv[2])
original = subprocess.Popen
seen = set()
class RecordedBootstrap:
    def __init__(self, process, arch): self.process, self.arch = process, arch
    def __getattr__(self, name): return getattr(self.process, name)
    def communicate(self, *args, **kwargs):
        result = self.process.communicate(*args, **kwargs)
        if self.process.returncode == 0:
            (indices / ('debootstrap-' + self.arch)).write_text(result[0])
            seen.add(self.arch)
        return result
def capture(command, *args, **kwargs):
    process = original(command, *args, **kwargs)
    if command[0] == 'debootstrap' and '--print-debs' in command:
        return RecordedBootstrap(process, command[command.index('--arch') + 1])
    return process
with patch('subprocess.Popen', side_effect=capture):
    main(['germinate-update-metapackage', '--nodch'])
assert seen == {'amd64', 'arm64'}, seen
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url, limit):
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError(f"download exceeds expected bound: {url}")
    return data


def canonical(url):
    url = url.rstrip("/") + "/"
    return url.replace("http://archive.ubuntu.com/", "https://archive.ubuntu.com/").replace(
        "http://ports.ubuntu.com/", "https://ports.ubuntu.com/").replace(
        "http://ppa.launchpad.net/elementary-os/", "https://ppa.launchpadcontent.net/elementary-os/")


def configured_archives(config, distribution):
    split = lambda value: [canonical(item) for item in value.replace(",", " ").split()]
    defaults = split(config.get(distribution, "archive_base/default"))
    architectures = config.get(distribution, "architectures").split()
    if set(architectures) != {"amd64", "arm64"}:
        raise RuntimeError("real-input gate currently requires the configured amd64 and arm64 hosts")
    mirrors = {arch: split(config.get(distribution, f"archive_base/{arch}",
                                    fallback=config.get(distribution, "archive_base/default")))
               for arch in architectures}
    urls = list(dict.fromkeys(defaults + [url for values in mirrors.values() for url in values]))
    result = []
    for number, url in enumerate(urls):
        if url in {"https://archive.ubuntu.com/ubuntu/", "https://ports.ubuntu.com/ubuntu-ports/"}:
            key = "ubuntu"
        elif url.startswith("https://ppa.launchpadcontent.net/elementary-os/") and url.endswith("/ubuntu/"):
            key = "elementary-os-os-patches.gpg" if "/os-patches/" in url else "elementary-os.gpg"
        else:
            raise RuntimeError(f"archive requires an explicit trust review: {url}")
        result.append({"url": url, "id": f"archive-{number}", "key": key,
                       "architectures": [arch for arch in architectures if url in mirrors[arch]],
                       "sources": url in defaults})
    return result, mirrors, defaults


def release_body(data):
    text = data.decode()
    if not text.startswith("-----BEGIN PGP SIGNED MESSAGE-----\n"):
        raise RuntimeError("archive metadata is not a clearsigned InRelease")
    body = text.split("\n\n", 1)[1].split("-----BEGIN PGP SIGNATURE-----", 1)[0]
    return "\n".join(line[2:] if line.startswith("- ") else line for line in body.splitlines()) + "\n"


def index_paths(spec, components):
    for component in components:
        for arch in spec["architectures"]:
            yield f"{component}/binary-{arch}/Packages"
            yield f"{component}/debian-installer/binary-{arch}/Packages"
        if spec["sources"]:
            yield f"{component}/source/Sources"


def confirm_unavailable(spec, distribution, components):
    """An unsigned but readable index must never disappear from the test."""
    urls = [spec["url"] + f"dists/{distribution}/{path}{suffix}"
            for path in index_paths(spec, components) for suffix in (".xz", ".bz2", ".gz", "")]
    def probe(url):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                response.read(1)
            raise RuntimeError(f"index is readable without captured signed metadata: {url}")
        except urllib.error.HTTPError as error:
            if error.code not in (403, 404, 410):
                raise
            return {"url": url, "http_status": error.code}
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(probe, urls))


def verify_signature(command):
    result = subprocess.run(command, text=True, capture_output=True)
    statuses = [line.split()[1:] for line in result.stdout.splitlines() if line.startswith("[GNUPG:] ")]
    fingerprints = [fields[1] for fields in statuses if fields[0] == "VALIDSIG"]
    unknown = {fields[1] for fields in statuses if fields[0] == "NO_PUBKEY"}
    bad = {"BADSIG", "EXPSIG", "EXPKEYSIG", "REVKEYSIG", "NODATA", "UNEXPECTED", "ERROR", "FAILURE", "BADARMOR"}
    if (result.returncode not in (0, 2) or not fingerprints or any(fields[0] in bad for fields in statuses)
            or any(fields[0] == "ERRSIG" and fields[1] not in unknown for fields in statuses)
            or (result.returncode and not unknown)):
        raise RuntimeError(f"archive signature verification failed: {result.stdout}\n{result.stderr}")
    # A valid signature under the supplied trust anchor covers the full signed
    # payload. Unknown additional co-signers do not acquire trust here.
    return fingerprints, sorted(unknown)


def check_signature_failures(root, signed_file, keyring):
    home = root / "gnupg-negative"
    home.mkdir(mode=0o700)
    modified = root / "modified-InRelease"
    data = signed_file.read_bytes()
    changed = data.replace(b"\nOrigin: ", b"\nOrigin: altered-", 1)
    if changed == data:
        raise RuntimeError("negative signature fixture has no Origin field")
    modified.write_bytes(changed)
    empty = root / "empty-keyring.gpg"
    empty.write_bytes(b"")
    checks = []
    for name, keys, payload in [("modified-signed-payload-rejected", keyring, modified),
                                ("unknown-only-signatures-rejected", empty, signed_file)]:
        try:
            verify_signature(["gpgv", "--homedir", str(home), "--status-fd", "1", "--keyring", str(keys), str(payload)])
        except RuntimeError:
            checks.append(name)
        else:
            raise AssertionError(f"signature negative case was accepted: {name}")
    return checks


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def capture_archive(spec, root, distribution, components, ubuntu_keyring, index_cache):
    mirror = root / "mirrors" / spec["id"]
    suite = mirror / "dists" / distribution
    suite.mkdir(parents=True)
    url = spec["url"] + f"dists/{distribution}/InRelease"
    receipt = {**spec, "inrelease_url": url, "indexes": []}
    try:
        signed = fetch(url, 2 * 1024 * 1024)
    except urllib.error.HTTPError as error:
        if error.code not in (403, 404, 410):
            raise
        receipt.update(status="unavailable", inrelease_http_status=error.code,
                       unavailable_index_probes=confirm_unavailable(spec, distribution, components))
        return receipt
    keyring = ubuntu_keyring if spec["key"] == "ubuntu" else REPO / "repos/common-files/etc/apt/keyrings" / spec["key"]
    home = root / "gnupg" / spec["id"]
    home.mkdir(parents=True, mode=0o700)
    (suite / "InRelease").write_bytes(signed)
    fingerprints, unknown = verify_signature(["gpgv", "--homedir", str(home), "--status-fd", "1", "--keyring", str(keyring),
                                              str(suite / "InRelease")])
    body = release_body(signed)
    (suite / "Release").write_text(body)
    fields = parity.fields(body)
    now = datetime.now(timezone.utc)
    if parsedate_to_datetime(fields["Date"]).timestamp() > now.timestamp() + 600:
        raise RuntimeError(f"archive metadata is dated in the future: {url}")
    if "Valid-Until" in fields and parsedate_to_datetime(fields["Valid-Until"]) < now:
        raise RuntimeError(f"archive metadata has expired: {url}")
    hashes = {}
    for line in fields["SHA256"].splitlines():
        if line.strip():
            digest, size, path = line.split()
            if path.startswith("/") or ".." in Path(path).parts or len(digest) != 64:
                raise RuntimeError("invalid signed index path/digest")
            hashes[path] = (digest, int(size))
    receipt.update(status="verified", inrelease_sha256=sha(signed), release_date=fields["Date"],
                   valid_until=fields.get("Valid-Until"), signing_fingerprints=fingerprints,
                   unknown_cosigner_key_ids=unknown, keyring_sha256=sha(keyring.read_bytes()))
    for path in index_paths(spec, components):
        encoded_path = next((path + suffix for suffix in (".xz", ".bz2", ".gz", "") if path + suffix in hashes), None)
        if encoded_path is None:
            receipt["indexes"].append({"path": path, "status": "not-published"})
            continue
        digest, size = hashes[encoded_path]
        if size > 128 * 1024 * 1024:
            raise RuntimeError("signed compressed index exceeds qualification bound")
        canonical_url = spec["url"] + f"dists/{distribution}/{encoded_path}"
        by_hash = fields.get("Acquire-By-Hash", "").lower() == "yes"
        download_url = (spec["url"] + f"dists/{distribution}/{Path(path).parent}/by-hash/SHA256/{digest}") if by_hash else canonical_url
        cached = index_cache / digest
        cache_hit = cached.exists()
        if cache_hit:
            if cached.stat().st_size != size:
                raise RuntimeError(f"cached index size mismatch: {digest}")
            encoded = cached.read_bytes()
        else:
            try:
                encoded = fetch(download_url, size)
            except urllib.error.HTTPError as error:
                if error.code != 404 or not by_hash:
                    raise
                download_url = canonical_url
                encoded = fetch(download_url, size)
        if len(encoded) != size or sha(encoded) != digest:
            raise RuntimeError(f"signed index hash/size mismatch: {download_url}")
        if not cached.exists():
            cached.write_bytes(encoded)
        decoded = (lzma.decompress(encoded) if encoded_path.endswith(".xz") else
                   bz2.decompress(encoded) if encoded_path.endswith(".bz2") else
                   gzip.decompress(encoded) if encoded_path.endswith(".gz") else encoded)
        if path in hashes and (sha(decoded), len(decoded)) != hashes[path]:
            raise RuntimeError(f"signed uncompressed index mismatch: {path}")
        destination = suite / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(decoded)
        (suite / encoded_path).write_bytes(encoded)
        receipt["indexes"].append({"path": path, "status": "verified", "url": download_url,
                                   "cache_hit": cache_hit,
                                   "encoded_sha256": digest, "encoded_size": size,
                                   "decoded_sha256": sha(decoded), "decoded_size": len(decoded)})
    print(f"verified {spec['url']}: {sum(item['status'] == 'verified' for item in receipt['indexes'])} signed indexes", flush=True)
    return receipt


def extract_reference(data, root):
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as archive:
        for entry in archive.getmembers():
            if entry.isfile() and entry.name.startswith("work/germinate/") and entry.name.endswith(".py") and "/tests/" not in entry.name:
                relative = Path(entry.name).relative_to("work")
                if ".." in relative.parts:
                    raise RuntimeError("unsafe reference module path")
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.extractfile(entry).read())


def qualify(args, root):
    manifest = json.loads((HERE.parent / "elementary-build-inputs.json").read_text())
    meta_record = json.loads((HERE.parent / "elementary-image-projects.json").read_text())["upstream_metapackages"]
    source = root / "reference-build"
    meta_data = upstream.source_archive(meta_record, None)
    upstream.extract_source(meta_data, source, meta_record["commit"])
    config = configparser.ConfigParser()
    config.read(source / "update.cfg")
    original_config_hash = sha((source / "update.cfg").read_bytes())
    distribution = config.get("DEFAULT", "dist")
    components = config.get(distribution, "components").split()
    specs, mirrors, defaults = configured_archives(config, distribution)
    report = {"schema": 1, "status": "acquiring", "observed_at": datetime.now(timezone.utc).isoformat(),
              "metapackages_commit": meta_record["commit"], "metapackages_archive_sha256": sha(meta_data),
              "upstream_update_config_sha256": original_config_hash, "distribution": distribution,
              "components": components, "seed_collections": [], "archives": [], "outputs": []}
    write_report(args.report, report)
    for record in manifest["inputs"]:
        project = record["id"].split("/")[-1]
        data = upstream.source_archive(record, None)
        target = root / "seeds" / f"{project}.{distribution}"
        upstream.extract_source(data, target, record["commit"], project)
        report["seed_collections"].append({"id": record["id"], "commit": record["commit"], "source_archive_sha256": sha(data)})
    # Capture every configured mirror. Unavailable mirrors have every index
    # endpoint probed so readable data cannot be silently dropped.
    index_cache = args.index_cache or root / "index-cache"
    index_cache.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        report["archives"].append(capture_archive(spec, root, distribution, components, args.ubuntu_keyring, index_cache))
        write_report(args.report, report)
    report["negative_signature_checks"] = check_signature_failures(
        root, root / f"mirrors/{specs[0]['id']}/dists/{distribution}/InRelease", args.ubuntu_keyring)
    if args.acquire_only:
        report["status"] = "acquired-only"
        return report
    indices = root / "indices"
    indices.mkdir()
    mapping = {spec["url"]: root / "mirrors" / spec["id"] for spec in specs}
    for arch in ("amd64", "arm64"):
        with (indices / f"Packages-{arch}").open("wb") as packages, (indices / f"Sources-{arch}").open("wb") as sources:
            for component in components:
                for url in mirrors[arch]:
                    path = mapping[url] / f"dists/{distribution}/{component}/binary-{arch}/Packages"
                    if path.is_file():
                        packages.write(path.read_bytes() + b"\n")
                for url in defaults:
                    path = mapping[url] / f"dists/{distribution}/{component}/source/Sources"
                    if path.is_file():
                        sources.write(path.read_bytes() + b"\n")
                for url in mirrors[arch]:
                    path = mapping[url] / f"dists/{distribution}/{component}/debian-installer/binary-{arch}/Packages"
                    if path.is_file():
                        packages.write(path.read_bytes() + b"\n")
    config.set(distribution, "archive_base/default", ",".join(mapping[url].as_uri() + "/" for url in defaults))
    for arch in ("amd64", "arm64"):
        config.set(distribution, f"archive_base/{arch}", ",".join(mapping[url].as_uri() + "/" for url in mirrors[arch]))
    config.set(distribution, "seed_base", (root / "seeds").as_uri() + "/")
    config.set(distribution, "seed_dist", f"seeds.{distribution}")
    with (source / "update.cfg").open("w") as output:
        config.write(output)
    reference_data = parity.reference_archive(None)
    extract_reference(reference_data, root / "reference-modules")
    report["germinate_archive_sha256"] = sha(reference_data)
    report["debootstrap_version"] = parity.run(["dpkg-query", "-W", "-f=${Version}", "debootstrap"], cwd=root, env=None).stdout
    report["status"] = "running-reference"
    write_report(args.report, report)
    print("running unchanged updater with real captured archives and debootstrap", flush=True)
    parity.run([sys.executable, "-c", REFERENCE_RUNNER, str(root / "reference-modules"), str(indices)], cwd=source, env=None)
    output = root / "native-lists"
    parity.run([str(args.binary), "generate-metapackage-lists", str(source),
                str(root / f"seeds/seeds.{distribution}/STRUCTURE"), f"seeds.{distribution}",
                str(indices), str(output), f"platform.{distribution}={root / f'seeds/platform.{distribution}'}"], cwd=root, env=None)
    seeds = config.get(distribution, "output_seeds", fallback=config.get(distribution, "seeds")).split()
    expected = {"metapackage-map"} | {f"{seed}{suffix}-{arch}" for seed in seeds for suffix in ("", "-recommends") for arch in ("amd64", "arm64")}
    if {path.name for path in output.iterdir()} != expected:
        raise AssertionError("real native output file membership differs")
    failures = []
    for name in sorted(expected):
        actual, reference = (output / name).read_bytes(), (source / name).read_bytes()
        if actual != reference:
            failures.append(f"{name}: native-only {sorted(set(actual.splitlines()) - set(reference.splitlines()))!r}; reference-only {sorted(set(reference.splitlines()) - set(actual.splitlines()))!r}")
        report["outputs"].append({"name": name, "native_sha256": sha(actual), "reference_sha256": sha(reference), "line_count": len(actual.splitlines())})
    for arch in ("amd64", "arm64"):
        report.setdefault("bootstrap_sets", []).append({"architecture": arch, "sha256": sha((indices / f"debootstrap-{arch}").read_bytes()),
                                                       "package_count": len((indices / f"debootstrap-{arch}").read_text().split())})
    if failures:
        report.update(status="mismatch", differences=failures)
    else:
        report["status"] = "passed"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=lambda value: Path(value).resolve())
    parser.add_argument("--ubuntu-keyring", type=lambda value: Path(value).resolve(), default=Path("/usr/share/keyrings/ubuntu-archive-keyring.gpg"))
    parser.add_argument("--acquire-only", action="store_true")
    parser.add_argument("--work-directory", type=lambda value: Path(value).resolve())
    parser.add_argument("--index-cache", type=lambda value: Path(value).resolve())
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    required = ["gpgv"] + ([] if args.acquire_only else ["debootstrap", "dpkg-query"])
    for tool in required:
        if not shutil.which(tool):
            parser.error(f"required tool is missing: {tool}")
    if not args.ubuntu_keyring.is_file() or args.report.exists():
        parser.error("a trusted Ubuntu keyring and a new report path are required")
    try:
        if args.work_directory:
            args.work_directory.mkdir(parents=True)
            report = qualify(args, args.work_directory)
        else:
            with tempfile.TemporaryDirectory(prefix="mseries-real-lists-") as temporary:
                report = qualify(args, Path(temporary))
    except Exception as error:
        if args.report.exists():
            report = json.loads(args.report.read_text())
            report.update(status="failed", failure_type=type(error).__name__)
            write_report(args.report, report)
        raise
    write_report(args.report, report)
    if report["status"] == "mismatch":
        raise AssertionError("\n".join(report["differences"]))
    if args.acquire_only:
        print("real archive capture verified; generation oracle not run")
    else:
        print(f"{len(report['outputs'])} real seed/archive map/list files match Germinate with actual debootstrap sets")


if __name__ == "__main__":
    main()
