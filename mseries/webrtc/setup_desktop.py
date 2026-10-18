#!/usr/bin/python3
"""Configure the existing user service and outbound SSH tunnel after Linux boot."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from urllib.parse import urlsplit

ALLOWED = {'HOST', 'PORT', 'MSERIES_WEBRTC_ORIGINS', 'MSERIES_WEBRTC_PUBLIC_URL', 'STUN_URL', 'TURN_URL', 'TURN_SECRET'}


def environment(data):
    result = {}
    for line in data.splitlines():
        if not line or line.lstrip().startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or key not in ALLOWED or key in result or any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise ValueError('Invalid/duplicate deployment setting')
        # Generated preparation files use unquoted literal values.
        result[key] = value
    url = urlsplit(result.get('MSERIES_WEBRTC_PUBLIC_URL', ''))
    if url.scheme != 'https' or url.netloc != 'mdm.stoverparc.org' or not re.fullmatch('/[a-f0-9]{48}/', url.path) or url.query or url.fragment:
        raise ValueError('Expected https://mdm.stoverparc.org/<48-hex-prefix>/')
    if result.get('HOST', '127.0.0.1') != '127.0.0.1' or result.get('PORT', '8789') != '8789':
        raise ValueError('The prepared tunnel requires a loopback service on port 8789')
    if result.get('TURN_URL') and not result.get('TURN_SECRET'):
        raise ValueError('TURN requires its shared secret')
    result['HOST'] = '127.0.0.1'; result['PORT'] = '8789'
    result['MSERIES_WEBRTC_ORIGINS'] = 'http://localhost:8789,http://127.0.0.1:8789,https://mdm.stoverparc.org'
    return result


def unit(target, identity):
    if not re.fullmatch(r'(?:[A-Za-z_][A-Za-z0-9_-]*@)?[A-Za-z0-9][A-Za-z0-9.-]*', target):
        raise ValueError('Invalid SSH target')
    if not identity.is_absolute() or any(c in str(identity) for c in '\n\r\x00'):
        raise ValueError('Invalid identity path')
    command = ['/usr/bin/ssh', '-NT', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', '-o', 'StrictHostKeyChecking=yes', '-i', str(identity), '-R', '127.0.0.1:18789:127.0.0.1:8789', target]
    quoted = ' '.join(json.dumps(arg.replace('%', '%%')) for arg in command)
    return f'''[Unit]
Description=M-series screen-sharing tunnel to SER8
After=mseries-webrtc.service
Wants=mseries-webrtc.service
PartOf=graphical-session.target

[Service]
ExecStart={quoted}
Restart=always
RestartSec=5
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=graphical-session.target
'''


def write_private(path, data):
    if path.is_symlink():
        raise ValueError('Refusing a symlink destination')
    temporary = path.with_name(path.name + '.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', type=Path, required=True)
    parser.add_argument('--ssh-target', default='sdolbec@100.127.99.74')
    parser.add_argument('--identity', type=Path, default=Path.home() / '.ssh/id_ed25519')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    settings = environment(args.environment.read_text())
    key = args.identity.expanduser().resolve()
    text = unit(args.ssh_target, key)
    if args.dry_run:
        print('Valid deployment settings. Would configure loopback service and strict-host SSH tunnel; no changes made.')
        return 0
    if os.uname().sysname != 'Linux' or os.geteuid() == 0:
        raise SystemExit('Run as the ElementaryOS desktop user, without sudo')
    info = key.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('SSH private key must be user-owned, mode 600 or stricter')
    # Verify existing trusted key authentication before writing/restarting anything.
    subprocess.run(['/usr/bin/ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5', '-i', str(key), args.ssh_target, 'true'], check=True, timeout=12)
    config = Path.home() / '.config/mseries-webrtc'
    units = Path.home() / '.config/systemd/user'
    config.mkdir(mode=0o700, parents=True, exist_ok=True); units.mkdir(parents=True, exist_ok=True)
    write_private(config / 'environment', ''.join(f'{k}={json.dumps(v)}\n' for k, v in settings.items()))
    write_private(units / 'mseries-webrtc-tunnel.service', text)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'restart', 'mseries-webrtc.service'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', 'mseries-webrtc-tunnel.service'], check=True)
    print('Service and tunnel configured. Open Screen Share and choose a screen. No capture/input session was started.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
