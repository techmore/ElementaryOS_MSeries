#!/usr/bin/env python3
"""Publish a user-service build state for the existing loopback-only monitor."""
import argparse
from datetime import datetime, timezone
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
                             '-p', 'Result'], capture_output=True, text=True, timeout=10)
    props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    active = props.get('ActiveState', 'unknown') in ('active', 'activating')
    success = result.returncode == 0 and props.get('Result') == 'success' and props.get('ExecMainStatus') == '0'
    now = datetime.now(timezone.utc)
    state = 'running' if active else 'success' if success else 'failed'
    data = dict(state=state, phase='kernel-compile-and-debian-package' if active else 'complete',
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
