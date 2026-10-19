#!/usr/bin/env python3
"""Fetch and verify Omarchy's current published ARM64 nightly, then boot it."""

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

METADATA_URL = "https://nightly.omarchy.org/edge-aarch64/latest.json"
ALLOWED_HOST = "nightly.omarchy.org"
CHUNK_SIZE = 1024 * 1024
MIN_FREE_BYTES = 10 * 1024 * 1024 * 1024
EXISTING_VM_FREE_BYTES = 2 * 1024 * 1024 * 1024


def status(message: str) -> None:
    print(f"STATUS\t{message}", flush=True)


def fail(message: str, code: int = 1) -> None:
    status(f"ERROR: {message}")
    raise SystemExit(code)


def fetch_metadata() -> dict:
    request = urllib.request.Request(
        METADATA_URL,
        headers={"User-Agent": "MachineLab/0.1 (Omarchy ARM64 VM setup)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        metadata = json.load(response)
    if metadata.get("channel") != "edge-aarch64" or metadata.get("arch") != "aarch64":
        fail("Omarchy's latest metadata is not for the ARM64 edge channel.")
    version = metadata.get("version")
    digest = metadata.get("sha256")
    size = metadata.get("size")
    url = metadata.get("url")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z._-]+", version):
        fail("Omarchy returned an invalid image version.")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        fail("Omarchy returned an invalid SHA-256 digest.")
    if not isinstance(size, int) or size <= 0:
        fail("Omarchy returned an invalid image size.")
    expected_name = f"omarchy-edge-{version}-aarch64.iso"
    parsed = urlparse(url if isinstance(url, str) else "")
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST or parsed.path != f"/edge-aarch64/{version}/{expected_name}":
        fail("Omarchy returned an image URL outside the expected nightly path.")
    metadata["expected_name"] = expected_name
    return metadata


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def disk_installed(disk: Path) -> bool:
    """An empty qcow2 header is not an installation: require real data on disk."""
    return disk.is_file() and disk.stat().st_blocks * 512 >= 1024 ** 3


def existing_path(path: Path) -> Path:
    """Return the nearest existing directory so disk_usage works before setup."""
    candidate = path
    while not candidate.exists():
        candidate = candidate.parent
    return candidate


def check_space(metadata: dict, vm_dir: Path, cache: Path) -> dict:
    disk = vm_dir / "disk.qcow2"
    existing_vm = disk_installed(disk)
    image = cache / metadata["expected_name"]
    part = cache / (metadata["expected_name"] + ".part")
    if existing_vm:
        download_remaining = 0
        vm_required = EXISTING_VM_FREE_BYTES
        cache_required = 0
    else:
        partial_size = part.stat().st_size if part.exists() else 0
        download_remaining = metadata["size"] if partial_size >= metadata["size"] else metadata["size"] - partial_size
        if image.is_file() and image.stat().st_size == metadata["size"]:
            # The launch helper still verifies the checksum, but no more download space is needed.
            download_remaining = 0
        vm_required = MIN_FREE_BYTES
        cache_required = download_remaining

    cache_location = existing_path(cache)
    vm_location = existing_path(vm_dir)
    cache_free = shutil.disk_usage(cache_location).free
    vm_free = shutil.disk_usage(vm_location).free
    same_filesystem = cache_location.stat().st_dev == vm_location.stat().st_dev
    if existing_vm:
        enough = vm_free >= vm_required
    elif same_filesystem:
        # The install reserve and image download consume the same free-space pool.
        vm_required += cache_required
        cache_required = vm_required
        enough = min(cache_free, vm_free) >= vm_required
    else:
        enough = cache_free >= cache_required and vm_free >= vm_required

    return {
        "existing_vm": existing_vm,
        "download_remaining": download_remaining,
        "cache_free": cache_free,
        "vm_free": vm_free,
        "cache_required": cache_required,
        "vm_required": vm_required,
        "same_filesystem": same_filesystem,
        "enough": enough,
    }


def runtime_prerequisites(existing_vm: bool) -> list[str]:
    problems = []
    missing = [tool for tool in ("qemu-system-aarch64", "qemu-img") if shutil.which(tool) is None]
    if missing:
        problems.append("Install " + " and ".join(missing))
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        problems.append("KVM access is unavailable to this user (/dev/kvm)")
    if not Path("/usr/share/AAVMF/AAVMF_CODE.fd").is_file() or not Path("/usr/share/AAVMF/AAVMF_VARS.fd").is_file():
        problems.append("AAVMF UEFI firmware is missing")
    if not existing_vm:
        missing = [tool for tool in ("openssl", "genisoimage") if shutil.which(tool) is None]
        if missing:
            problems.append("Install " + " and ".join(missing))
    return problems


def print_check(vm_dir: Path, cache: Path) -> None:
    metadata = fetch_metadata()
    space = check_space(metadata, vm_dir, cache)
    problems = runtime_prerequisites(space["existing_vm"])
    fields = [
        metadata["version"], metadata.get("built_at", "unknown"),
        metadata.get("omarchy_version", "unknown"), str(metadata["size"]),
        "1" if space["existing_vm"] else "0",
        str(space["cache_free"]), str(space["vm_free"]),
        str(space["cache_required"]), str(space["vm_required"]),
        str(space["download_remaining"]),
        "1" if space["enough"] else "0",
        "1" if space["same_filesystem"] else "0",
        (" ".join(problems).replace("\t", " ").replace("\n", " ") or "-"),
    ]
    print("CHECK\t" + "\t".join(fields), flush=True)


def get_image(metadata: dict, cache: Path, vm_dir: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    image = cache / metadata["expected_name"]
    part = cache / (metadata["expected_name"] + ".part")
    expected_size = metadata["size"]
    expected_hash = metadata["sha256"]

    if image.exists() and image.stat().st_size == expected_size:
        status("Checking cached ISO checksum…")
        if digest_file(image) == expected_hash:
            return image
        image.unlink()

    offset = part.stat().st_size if part.exists() else 0
    if offset >= expected_size:
        part.unlink()
        offset = 0
    space = check_space(metadata, vm_dir, cache)
    if not space["enough"]:
        fail(
            "Not enough free space to download and install Omarchy safely. "
            f"Download storage needs {(space['cache_required'] / 1024**3):.1f} GiB "
            f"and has {(space['cache_free'] / 1024**3):.1f} GiB; "
            f"VM storage needs {(space['vm_required'] / 1024**3):.1f} GiB "
            f"and has {(space['vm_free'] / 1024**3):.1f} GiB."
        )

    headers = {"User-Agent": "MachineLab/0.1 (Omarchy ARM64 VM setup)"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
        status(f"Resuming Omarchy {metadata['omarchy_version']} ARM64 nightly at {(offset / 1024**3):.1f} GiB…")
    else:
        status(f"Downloading Omarchy {metadata['omarchy_version']} ARM64 nightly ({expected_size / 1024**3:.1f} GiB)…")

    try:
        response = urllib.request.urlopen(
            urllib.request.Request(metadata["url"], headers=headers), timeout=60
        )
    except (urllib.error.URLError, TimeoutError) as error:
        fail(f"Could not download the Omarchy image: {error}")

    if offset and response.status != 206:
        response.close()
        offset = 0
        response = urllib.request.urlopen(
            urllib.request.Request(metadata["url"], headers={"User-Agent": headers["User-Agent"]}),
            timeout=60,
        )
    mode = "ab" if offset else "wb"
    received = offset
    last_report = -1
    try:
        with response, part.open(mode) as target:
            while chunk := response.read(CHUNK_SIZE):
                target.write(chunk)
                received += len(chunk)
                percent = min(100, int(received * 100 / expected_size))
                if percent != last_report:
                    status(f"Downloading Omarchy {metadata['omarchy_version']} ARM64 nightly… {percent}%")
                    last_report = percent
    except (OSError, urllib.error.URLError, TimeoutError) as error:
        fail(f"Download stopped; the partial file is kept so the next attempt can resume: {error}")

    if part.stat().st_size != expected_size:
        fail(f"Downloaded image size does not match metadata ({part.stat().st_size} of {expected_size} bytes). The partial file is kept for retry.")
    status("Verifying Omarchy image SHA-256…")
    if digest_file(part) != expected_hash:
        part.unlink(missing_ok=True)
        fail("The downloaded image failed its SHA-256 check and was deleted.")
    part.replace(image)
    return image


def create_autoinstall_seed(metadata: dict, vm_dir: Path) -> tuple[Path, str]:
    required = ("openssl", "genisoimage")
    missing = [tool for tool in required if shutil.which(tool) is None]
    if missing:
        fail("Install the required tools first: " + ", ".join(missing))

    vm_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(vm_dir, 0o700)
    password_file = vm_dir / "credentials.txt"
    if password_file.exists():
        saved = password_file.read_text().splitlines()
        password = next((line.split(": ", 1)[1] for line in saved if line.startswith("Sudo password: ")), "")
        if not password:
            fail(f"The saved VM credentials file is invalid: {password_file}")
    else:
        password = secrets.token_hex(24)
        fd = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(f"Username: omarchy\nSudo password: {password}\n")

    hash_result = subprocess.run(
        ["openssl", "passwd", "-6", "-stdin"],
        check=True,
        capture_output=True,
        text=True,
        input=password + "\n",
    )
    password_hash = hash_result.stdout.strip()
    gib = 1024**3
    mib = 1024**2
    disk_bytes = 64 * gib
    boot_start = mib
    boot_size = 2 * gib
    main_start = boot_start + boot_size
    main_size = disk_bytes - main_start - mib
    seed_dir = vm_dir / f"autoinstall-{metadata['version']}"
    seed_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    configuration = {
        "app_config": None,
        "archinstall-language": "English",
        "auth_config": {},
        "audio_config": {"audio": "pipewire"},
        "bootloader_config": {"bootloader": "Limine", "uki": False, "removable": False},
        "custom_commands": [],
        "omarchy_install": {
            "mode": "full_disk",
            "defer_provisioning": False,
            "target_mount": "/mnt",
            "boot": {
                "esp_mount": "/boot",
                "esp_path": "/EFI/limine",
                "efi_binary": "limine_aa64.efi",
                "enable_fallback": True,
            },
            "storage": {"kernel": "linux-omarchy"},
        },
        "disk_config": {
            "config_type": "default_layout",
            "device_modifications": [
                {
                    "device": "/dev/vda",
                    "partitions": [
                        {
                            "btrfs": [],
                            "dev_path": None,
                            "flags": ["boot", "esp"],
                            "fs_type": "fat32",
                            "mount_options": [],
                            "mountpoint": "/boot",
                            "obj_id": "ea21d3f2-82bb-49cc-ab5d-6f81ae94e18d",
                            "size": {"sector_size": {"unit": "B", "value": 512}, "unit": "B", "value": boot_size},
                            "start": {"sector_size": {"unit": "B", "value": 512}, "unit": "B", "value": boot_start},
                            "status": "create",
                            "type": "primary",
                        },
                        {
                            "btrfs": [
                                {"mountpoint": "/", "name": "@"},
                                {"mountpoint": "/home", "name": "@home"},
                                {"mountpoint": "/var/log", "name": "@log"},
                                {"mountpoint": "/var/cache/pacman/pkg", "name": "@pkg"},
                            ],
                            "dev_path": None,
                            "flags": [],
                            "fs_type": "btrfs",
                            "mount_options": ["compress=zstd"],
                            "mountpoint": None,
                            "obj_id": "8c2c2b92-1070-455d-b76a-56263bab24aa",
                            "size": {"sector_size": {"unit": "B", "value": 512}, "unit": "B", "value": main_size},
                            "start": {"sector_size": {"unit": "B", "value": 512}, "unit": "B", "value": main_start},
                            "status": "create",
                            "type": "primary",
                        },
                    ],
                    "wipe": True,
                }
            ],
        },
        "hostname": "omarchy-vm",
        "kernels": ["linux-omarchy"],
        "network_config": {"type": "iso"},
        "ntp": True,
        "parallel_downloads": 8,
        "script": None,
        "services": [],
        "swap": True,
        "timezone": "UTC",
        "locale_config": {"kb_layout": "us", "sys_enc": "UTF-8", "sys_lang": "en_US.UTF-8"},
        "mirror_config": {
            "custom_repositories": [],
            "custom_servers": [{"url": "https://arm-mirror.omarchy.org/$arch/$repo"}],
            "mirror_regions": {},
            "optional_repositories": [],
        },
        "packages": ["base-devel", "git", "omarchy-keyring", "omarchy-settings-dev", "omarchy-dev"],
        "profile_config": {"gfx_driver": None, "greeter": None, "profile": {}},
        "version": "3.0.9",
    }
    credentials = {
        "root_enc_password": password_hash,
        "users": [{"enc_password": password_hash, "groups": [], "sudo": True, "username": "omarchy"}],
    }
    (seed_dir / "user_configuration.json").write_text(json.dumps(configuration, indent=2) + "\n")
    (seed_dir / "user_credentials.json").write_text(json.dumps(credentials, indent=2) + "\n")
    (seed_dir / "user_encrypt_installation.txt").write_text("false\n")

    cidata = vm_dir / f"cidata-{metadata['version']}.iso"
    temporary = cidata.with_suffix(".iso.part")
    try:
        subprocess.run(
            ["genisoimage", "-quiet", "-output", str(temporary), "-volid", "cidata", "-joliet", "-rock", str(seed_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        fail(f"Could not create Omarchy's unattended install seed: {error.stderr.strip()}")
    temporary.replace(cidata)
    return cidata, password


def emit_saved_credentials(vm_dir: Path) -> None:
    password_file = vm_dir / "credentials.txt"
    if password_file.is_file():
        credentials = password_file.read_text().replace("\n", " · ").strip(" ·")
        print(f"CREDENTIAL\t{credentials} · saved in {password_file}", flush=True)


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--check":
        try:
            print_check(Path(sys.argv[2]), Path(sys.argv[3]))
        except urllib.error.URLError as error:
            fail(f"Could not check Omarchy's latest version: {error}")
        return
    if len(sys.argv) != 4:
        fail("Internal updater arguments are invalid.")
    launcher, vm_dir, cache_dir = map(Path, sys.argv[1:])
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        fail("The QEMU launcher could not be found.")

    missing = [tool for tool in ("qemu-system-aarch64", "qemu-img") if shutil.which(tool) is None]
    if missing:
        fail("Install the required tools first: " + ", ".join(missing))
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        fail("KVM is unavailable to this user. Check /dev/kvm permissions.")
    if not Path("/usr/share/AAVMF/AAVMF_CODE.fd").is_file() or not Path("/usr/share/AAVMF/AAVMF_VARS.fd").is_file():
        fail("AAVMF UEFI firmware was not found under /usr/share/AAVMF.")

    # Starting an existing installation must not silently replace/update it
    # from a newly downloaded installer. Omarchy updates its installed guest
    # through its own updater, run inside the VM.
    disk = vm_dir / "disk.qcow2"
    if disk_installed(disk):
        cached_images = sorted(cache_dir.glob("omarchy-edge-*-aarch64.iso"))
        if cached_images:
            status("Starting the existing VM. To update installed Omarchy, run `omarchy update` inside the guest.")
            emit_saved_credentials(vm_dir)
            os.execv(str(launcher), [str(launcher), str(cached_images[-1]), str(vm_dir)])
        status("Starting the existing VM without installer media. To update installed Omarchy, run `omarchy update` inside the guest.")
        emit_saved_credentials(vm_dir)
        os.execv(str(launcher), [str(launcher), "--disk-only", str(vm_dir)])

    missing = [tool for tool in ("openssl", "genisoimage") if shutil.which(tool) is None]
    if missing:
        fail("Install the required tools first: " + ", ".join(missing))
    try:
        status("Checking Omarchy's current ARM64 nightly…")
        metadata = fetch_metadata()
        image = get_image(metadata, cache_dir, vm_dir)
        cidata, password = create_autoinstall_seed(metadata, vm_dir)
    except urllib.error.URLError as error:
        fail(f"Could not check Omarchy's latest version: {error}")
    status(f"Installing Omarchy {metadata['omarchy_version']} (nightly {metadata['version']}) automatically. The VM will reboot into the installed guest when setup finishes.")
    print(f"CREDENTIAL\tUsername: omarchy · sudo password: {password} · saved in {vm_dir / 'credentials.txt'}", flush=True)
    os.execv(str(launcher), [str(launcher), str(image), str(vm_dir), str(cidata)])


if __name__ == "__main__":
    main()
