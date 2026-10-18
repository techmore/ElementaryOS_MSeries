#!/usr/bin/env python3
"""Opt-in, user-local experimental Apple Passwords integration."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

REV = "916ef17a5a14965f353d556a53ca3eedc1439113"
IMAGE = "docker.io/dadoum/anisette-v3-server@sha256:12ebe8bedbffe96953ce4fd20b578997bc7ed266f7a5015d4f96526e9c65af1f"
HERE = Path(__file__).resolve().parent


def run(*args):
    subprocess.run(args, check=True)


def write(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)


def prepare_source(source):
    # Fail closed instead of upstream's cleartext-on-disk master-key fallback.
    session = source / "icp/auth/session.py"
    old = "return key if key is not None else _key_from_file()"
    new = 'if key is None:\n        raise SessionError("GNOME Keyring must be available and unlocked; file fallback disabled")\n    return key'
    text = session.read_text()
    if text.count(old) != 1:
        raise RuntimeError("Upstream keyring patch no longer applies")
    session.write_text(text.replace(old, new))
    manifest_path = source / "extension/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("browser_specific_settings", None)
    manifest["background"].pop("scripts", None)
    manifest["key"] = (HERE / "chromium-key.pub").read_text().strip()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    digest = hashlib.sha256(base64.b64decode(manifest["key"], validate=True)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experimental", action="store_true", required=True,
                        help="enable this unofficial, read-only integration")
    parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Run as your desktop user, without sudo")
    if os.uname().machine != "aarch64":
        parser.error("This initial helper image pin is ARM64 only")
    for tool in ("git", "python3", "podman", "systemctl", "brave-browser"):
        if not shutil.which(tool):
            parser.error(f"Install prerequisite: {tool}")
    os.umask(0o077)
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    base = data / "mseries/icloud-passwords"
    source = base / "source"
    if source.exists():
        installed = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        if installed != REV:
            raise RuntimeError("Existing source has a different pin; refusing to overwrite")
        manifest = json.loads((source / "extension/manifest.json").read_text())
        key = manifest.get("key")
        expected = (HERE / "chromium-key.pub").read_text().strip()
        if key != expected or "file fallback disabled" not in (source / "icp/auth/session.py").read_text():
            raise RuntimeError("Existing source is not this integration; refusing to overwrite")
        digest = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
        extension_id = "".join(chr(ord("a") + int(c, 16)) for c in digest)
    else:
        source.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", "https://github.com/Sank6/iCloud-Keychain-for-Linux.git", str(source))
        run("git", "-C", str(source), "checkout", "--detach", REV)
        extension_id = prepare_source(source)
    run("python3", "-m", "venv", str(source / ".venv"))
    run(str(source / ".venv/bin/pip"), "install", "-e", str(source))
    (source / "host/icp-host.sh").chmod(0o700)
    native = {"name": "org.icp.native", "description": "Experimental Apple Passwords",
              "path": str(source / "host/icp-host.sh"), "type": "stdio",
              "allowed_origins": [f"chrome-extension://{extension_id}/"]}
    write(config / "BraveSoftware/Brave-Browser/NativeMessagingHosts/org.icp.native.json",
          json.dumps(native, indent=2) + "\n")
    # Persist anisette machine identity between restarts, bound only to loopback.
    unit = f"""[Unit]
Description=Experimental Apple Passwords local authentication helper
After=network-online.target
Wants=network-online.target
[Service]
ExecStartPre=-/usr/bin/podman rm -f mseries-icloud-anisette
ExecStart=/usr/bin/podman run --name mseries-icloud-anisette --publish 127.0.0.1:6969:6969 --volume mseries-icloud-anisette:/home/Alcoholic/.config/anisette-v3/lib {IMAGE}
ExecStop=/usr/bin/podman stop -t 10 mseries-icloud-anisette
Restart=on-failure
RestartSec=10
TimeoutStartSec=300
[Install]
WantedBy=default.target
"""
    write(config / "systemd/user/mseries-icloud-anisette.service", unit)
    run("podman", "pull", IMAGE)
    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", "--now", "mseries-icloud-anisette.service")
    launcher = home / ".local/bin/mseries-icloud-passwords"
    write(launcher, f"""#!/usr/bin/env bash
set -euo pipefail
umask 077
export ICP_ANISETTE_URL=http://127.0.0.1:6969
case "${{1:-show}}" in
  login)
    {shlex.quote(str(source / '.venv/bin/python'))} -c 'import sys, secretstorage; c=secretstorage.get_default_collection(secretstorage.dbus_init()); c.is_locked() and sys.exit("Unlock GNOME Keyring before signing in")'
    systemctl --user start mseries-icloud-anisette.service
    echo 'Experimental unofficial client. Enter Apple credentials here, never in chat.'
    echo 'Use your known device passcode; stop on recovery failure rather than retrying guesses.'
    ;;
  show|sync|logout) ;;
  *) echo 'Usage: mseries-icloud-passwords [login|show|sync|logout]' >&2; exit 2 ;;
esac
exec {shlex.quote(str(source / '.venv/bin/icp'))} "${{@:-show}}"
""", 0o700)
    for action, label in (("show", "Apple Passwords (Experimental)"),
                          ("login", "Set Up Apple Passwords (Experimental)"),
                          ("sync", "Sync Apple Passwords (Experimental)")):
        write(data / f"applications/mseries-icloud-passwords-{action}.desktop", f"""[Desktop Entry]
Type=Application
Name={label}
Comment=Unofficial read-only iCloud Keychain integration
Exec="{launcher}" {action}
Icon=dialog-password
Terminal=true
Categories=Utility;Security;
""", 0o644)
    write(base / "installation.json", json.dumps({"upstream_revision": REV, "anisette_image": IMAGE,
          "extension_id": extension_id, "experimental": True}, indent=2) + "\n")
    print(f"Ready. In brave://extensions enable Developer mode and Load unpacked: {source / 'extension'}")
    print(f"Expected extension ID: {extension_id}")
    print("Then open Set Up Apple Passwords (Experimental) to sign in privately.")


if __name__ == "__main__":
    main()
