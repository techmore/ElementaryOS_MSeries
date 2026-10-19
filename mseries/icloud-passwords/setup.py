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
import ssl
import urllib.request

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



def replace_checked(text, old, new, count=1):
    if old in text:
        if text.count(old) != count:
            raise RuntimeError("Pinned upstream patch count changed")
        return text.replace(old, new)
    if text.count(new) != count:
        raise RuntimeError("Pinned upstream patch no longer applies")
    return text


def apply_network_patches(source):
    """Endpoint-specific workaround reported in Dadoum/anisette-v3-server#61.

    Do not change account-settings or CloudKit identity. No remote helper involved.
    """
    patches = {
        "icp/const.py": [
            ('"<MacBookPro18,3> <Mac OS X;13.4.1;22F8> "',
             '"<PC> <Windows;6.2(0,0);9200> "', 1)],
        "icp/auth/icloud.py": [
            ('class ICloudError(AppleError):',
             'DELEGATES_CLIENT_INFO = ("<PC> <Windows;6.2(0,0);9200> "\n'
             '                         "<com.apple.AOSKit/282 (com.apple.accountsd/113)>")\n\n\n'
             'class ICloudError(AppleError):', 1),
            ('"X-Mme-Client-Info": ICLOUD_CLIENT_INFO,\n        "Accept": "*/*",',
             '"X-Mme-Client-Info": DELEGATES_CLIENT_INFO,\n        "Accept": "*/*",', 1),
            ('verify=False', 'verify=True', 2)],
        "icp/escrow/srp.py": [
            ('"<MacBookPro18,3> <macOS;13.4.1;22F8> "',
             '"<PC> <Windows;6.2(0,0);9200> "', 1)],
        "icp/auth/gsa.py": [('verify=False', 'verify=True', 5)],
        "icp/auth/webauth.py": [('self.http.verify = False', 'self.http.verify = True', 1)],
    }
    # Validate every replacement before touching any file.
    updated = {}
    for relative, edits in patches.items():
        path = source / relative
        text = path.read_text()
        for old, new, count in edits:
            # Insertion markers can be contained in the already-patched replacement.
            if new in text and old in new:
                continue
            text = replace_checked(text, old, new, count)
        updated[path] = text
    for path, text in updated.items():
        path.write_text(text)
    for filename in ("gsa-errors.patch", "notification-wait.patch"):
        patch = str(HERE / filename)
        applied = subprocess.run(["git", "-C", str(source), "apply", "--reverse", "--check", patch],
                                 capture_output=True)
        if applied.returncode:
            run("git", "-C", str(source), "apply", "--check", patch)
            run("git", "-C", str(source), "apply", patch)



def install_ca_bundle(base):
    # Apple publishes its private-service roots over publicly trusted HTTPS.
    # Trust is scoped to this client; never alter the operating system CA store.
    roots = (
        ("https://www.apple.com/appleca/AppleIncRootCertificate.cer",
         "b0b1730ecbc7ff4505142c49f1295e6eda6bcaed7e2c68c5be91b5a11001f024"),
        ("https://www.apple.com/certificateauthority/AppleRootCA-G3.cer",
         "63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179"),
    )
    cafile = ssl.get_default_verify_paths().cafile
    if not cafile:
        raise RuntimeError("System trust bundle is unavailable")
    bundle = Path(cafile).read_text()
    for url, digest in roots:
        with urllib.request.urlopen(url, timeout=20) as response:
            der = response.read(16385)
        if len(der) > 16384 or hashlib.sha256(der).hexdigest() != digest:
            raise RuntimeError("Apple CA certificate pin mismatch")
        bundle += "\n" + ssl.DER_cert_to_PEM_cert(der)
    path = base / "ca-bundle.pem"
    write(path, bundle)
    return path


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
    run("/usr/bin/python3", "-c", "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Granite', '7.0'); from gi.repository import Gtk, Granite")
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
    ca_bundle = install_ca_bundle(base)
    apply_network_patches(source)
    run("python3", "-m", "venv", str(source / ".venv"))
    run(str(source / ".venv/bin/pip"), "install", "-e", str(source))
    host = source / "host/icp-host.sh"
    host_text = host.read_text()
    if "export REQUESTS_CA_BUNDLE=" not in host_text:
        host_text = host_text.replace('exec "$PY"',
                    'export REQUESTS_CA_BUNDLE=' + shlex.quote(str(ca_bundle)) + '\nexec "$PY"')
    write(host, host_text, 0o700)
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
export REQUESTS_CA_BUNDLE={shlex.quote(str(ca_bundle))}
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
    # Native GUI uses system Python for GTK/Granite and a separate venv worker.
    for filename in ("app.py", "worker.py"):
        write(base / "gui" / filename, (HERE / filename).read_text(), 0o700)
    gui = home / ".local/bin/mseries-icloud-passwords-gui"
    write(gui, '#!/usr/bin/env bash\nset -euo pipefail\numask 077\nexec /usr/bin/python3 ' +
          shlex.quote(str(base / "gui/app.py")) + '\n', 0o700)
    # Retire this integration's older terminal-only setup/sync shortcuts.
    for old_action in ("login", "sync", "show"):
        (data / f"applications/mseries-icloud-passwords-{old_action}.desktop").unlink(missing_ok=True)
    for action, label in (("show", "Apple Passwords (Experimental)"),):
        write(data / "applications/org.techmore.mseries.ApplePasswords.desktop", f"""[Desktop Entry]
Type=Application
Name={label}
Comment=Unofficial read-only iCloud Keychain integration
Exec="{gui}"
Icon=dialog-password
Terminal=false
StartupNotify=true
Categories=Utility;Security;
""", 0o644)
    write(base / "installation.json", json.dumps({"upstream_revision": REV, "anisette_image": IMAGE,
          "extension_id": extension_id, "experimental": True}, indent=2) + "\n")
    print(f"Ready. In brave://extensions enable Developer mode and Load unpacked: {source / 'extension'}")
    print(f"Expected extension ID: {extension_id}")
    print("Then open Apple Passwords (Experimental) to sign in privately in the native GUI.")


if __name__ == "__main__":
    main()
