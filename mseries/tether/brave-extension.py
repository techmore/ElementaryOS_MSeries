#!/usr/bin/env python3
"""Prepare or register Tether's optional Chromium extension for Brave."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

VERSION = "0.2.37"
PACKAGE_EXTENSION = Path("/usr/share/tether/extensions/tether-chromium-extension.zip")
EXTENSION_DIR = (
    Path.home()
    / ".local/share/mseries/tether-brave-extension"
    / VERSION
    / "chromium"
)
BRAVE_MANIFEST = (
    Path.home()
    / ".config/BraveSoftware/Brave-Browser/NativeMessagingHosts"
    / "com.tether.extension.json"
)
HOST = Path("/usr/bin/tether-native-host")
ORIGIN_PATTERN = re.compile(r"^chrome-extension://([a-p]{32})/$")


def prepare() -> None:
    if not PACKAGE_EXTENSION.is_file():
        raise SystemExit(
            "Tether's packaged Chromium extension was not found. "
            "Install it first with: bash mseries/install-tether.sh"
        )
    if EXTENSION_DIR.exists():
        try:
            manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text())
        except (OSError, json.JSONDecodeError):
            raise SystemExit(f"Refusing to overwrite existing extension directory: {EXTENSION_DIR}")
        if manifest.get("version") == "1.0.6":
            print(f"Tether extension is already prepared at: {EXTENSION_DIR}")
            return
        raise SystemExit(f"Refusing to overwrite existing extension directory: {EXTENSION_DIR}")

    EXTENSION_DIR.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".tether-brave-", dir=EXTENSION_DIR.parent))
    try:
        with zipfile.ZipFile(PACKAGE_EXTENSION) as archive:
            for member in archive.infolist():
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise SystemExit(f"Unsafe extension archive path: {member.filename}")
            archive.extractall(staging)
        manifest = json.loads((staging / "manifest.json").read_text())
        if manifest.get("manifest_version") != 3 or not manifest.get("version"):
            raise SystemExit("The packaged Chromium extension manifest is not the expected MV3 extension.")
        os.replace(staging, EXTENSION_DIR)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    print(f"Prepared Tether's Chromium extension at: {EXTENSION_DIR}")
    print("In Brave, open brave://extensions, enable Developer mode, choose Load unpacked, and select that folder.")
    print("After Brave shows the extension ID, register it with this helper's register command.")
    print("The extension requests access on all websites. Review Brave's permission prompt before enabling it.")


def load_manifest() -> dict:
    if BRAVE_MANIFEST.is_symlink():
        raise SystemExit(f"Refusing to replace a symlink: {BRAVE_MANIFEST}")
    if not BRAVE_MANIFEST.exists():
        return {
            "name": "com.tether.extension",
            "description": "Tether Native Messaging Host",
            "path": str(HOST),
            "type": "stdio",
            "allowed_origins": [],
        }
    try:
        current = json.loads(BRAVE_MANIFEST.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read existing Brave native host manifest: {exc}")
    if current.get("name") != "com.tether.extension" or current.get("type") != "stdio":
        raise SystemExit(f"Existing manifest has an unexpected host identity: {BRAVE_MANIFEST}")
    if current.get("path") != str(HOST):
        raise SystemExit(
            f"Existing manifest points to another host ({current.get('path')}); refusing to replace it."
        )
    origins = current.setdefault("allowed_origins", [])
    if not isinstance(origins, list) or not all(isinstance(item, str) for item in origins):
        raise SystemExit("Existing allowed_origins must be a list of strings.")
    return current


def write_manifest(manifest: dict) -> None:
    BRAVE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".com.tether.extension.", dir=BRAVE_MANIFEST.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(manifest, output, indent=2)
            output.write("\n")
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, BRAVE_MANIFEST)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def register(extension_id: str) -> None:
    origin = f"chrome-extension://{extension_id}/"
    manifest = load_manifest()
    origins = manifest["allowed_origins"]
    if origin not in origins:
        origins.append(origin)
    write_manifest(manifest)
    print(f"Registered {origin} in {BRAVE_MANIFEST}")
    print("Quit and reopen Brave, then use the extension only on the site where you need a code.")


def unregister(extension_id: str) -> None:
    if not BRAVE_MANIFEST.exists():
        print("No Tether native messaging registration exists for Brave.")
        return
    manifest = load_manifest()
    origin = f"chrome-extension://{extension_id}/"
    origins = manifest["allowed_origins"]
    manifest["allowed_origins"] = [item for item in origins if item != origin]
    if manifest["allowed_origins"]:
        write_manifest(manifest)
    else:
        BRAVE_MANIFEST.unlink()
    print(f"Removed {origin} from Brave's Tether native messaging registration.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare", help="extract the pinned Chromium extension to a stable user directory")
    register_parser = subparsers.add_parser("register", help="allow a loaded Brave extension to use tetherd")
    register_parser.add_argument("extension_id", help="32-character ID shown at brave://extensions")
    unregister_parser = subparsers.add_parser("unregister", help="remove one extension ID from Brave's host manifest")
    unregister_parser.add_argument("extension_id", help="32-character ID shown at brave://extensions")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        if not re.fullmatch(r"[a-p]{32}", args.extension_id):
            parser.error("extension ID must contain 32 letters from a to p")
        if args.command == "register":
            if not HOST.is_file() or not os.access(HOST, os.X_OK):
                raise SystemExit("Install Tether first; /usr/bin/tether-native-host is missing or not executable.")
            if not EXTENSION_DIR.joinpath("manifest.json").is_file():
                raise SystemExit("Prepare and load the extension first: python3 mseries/tether/brave-extension.py prepare")
            register(args.extension_id)
        else:
            unregister(args.extension_id)


if __name__ == "__main__":
    main()
