#!/usr/bin/env python3
"""Publish a user-service build state for the existing loopback-only monitor."""
import argparse
from datetime import datetime, timezone, timedelta
import json
import re
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('unit')
parser.add_argument('status', type=Path)
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z0-9_.@-]+\.service", args.unit):
    parser.error("Expected a user service unit name")
started = datetime.now(timezone.utc)
while True:
    result = subprocess.run(['systemctl', '--user', 'show', args.unit,
                             '-p', 'ActiveState', '-p', 'ExecMainStatus',
                             '-p', 'Result', '-p', 'ExecMainStartTimestampMonotonic'], capture_output=True, text=True, timeout=10)
    props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    active = props.get('ActiveState', 'unknown') in ('active', 'activating')
    success = result.returncode == 0 and props.get('Result') == 'success' and props.get('ExecMainStatus') == '0'
    now = datetime.now(timezone.utc)
    start_us = props.get('ExecMainStartTimestampMonotonic', '0')
    if start_us.isdigit() and int(start_us) > 0:
        started = now - timedelta(seconds=max(0, time.monotonic() - int(start_us) / 1_000_000))
    phase = 'kernel-compile'
    log = args.status.parent / 'kernel-build.log'
    try:
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 32768))
            tail = stream.read().decode(errors='replace')
        if 'dpkg-deb: building package' in tail:
            phase = 'debian-package-compression'
        elif 'INSTALL debian/' in tail:
            phase = 'stage-kernel-and-modules'
        elif 'BTF [M]' in tail or 'LD [M]' in tail:
            phase = 'link-kernel-modules'
        elif 'LD      vmlinux' in tail:
            phase = 'link-kernel'
    except OSError:
        pass
    state = 'running'  if active else 'success' if success else 'failed'
    data = dict(state=state, phase=phase if active else 'complete',
                sourceCommit='ce9f2eba72c061a50b2d790450e90af3439d8c24 + pinned USB4 patch',
                startedAt=started.isoformat(), updatedAt=now.isoformat(),
                elapsedSeconds=int((now-started).total_seconds()),
                exitCode=None if active else int(props.get('ExecMainStatus', '1')) if props.get('ExecMainStatus', '').isdigit() else 1)
    temp = args.status.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(args.status)
    if not active:
        break
    time.sleep(10)
