#!/usr/bin/python3
"""Watch this user's coredumps, deduplicate, and optionally diagnose locally."""
import json
import os
from pathlib import Path
import subprocess
import time
import hashlib
import re

MESSAGE_ID = 'fc2e22bc6ee647b6b90729ab34a250b1'
STATE = Path.home() / '.local/state/mseries-troubleshooter'

KERNEL_PATTERNS = [
    ('gpu', r'(?:gpu|drm|asahi).*(?:fault|hang|timeout|timed out|wedge)|Job timed out on the DRM scheduler'),
    ('memory', r'out of memory|oom-kill|Killed process \d+'),
    ('lockup', r'soft lockup|hard LOCKUP|rcu.*stall|hung task|blocked for more than'),
    ('oops', r'Kernel panic|Oops:|BUG:|WARNING: CPU:'),
    ('storage', r'(?:nvme|I/O|btrfs|ext4).*(?:error|timeout|corrupt|read-only)'),
    ('suspend', r'(?:suspend|resume|PM:).*(?:failed|error|timeout)'),
    ('usb4', r'(?:thunderbolt|apple-nhi).*(?:DPRX.*timeout|router.*failed|error)'),
]


def kernel_event(record):
    if record.get('_TRANSPORT') != 'kernel':
        return None
    message = record.get('MESSAGE')
    if not isinstance(message, str):
        return None
    for subsystem, pattern in KERNEL_PATTERNS:
        if re.search(pattern, message, re.I):
            # Group changing addresses, PIDs and durations into one fault signature.
            normalized = re.sub(r'\b(?:0x)?[0-9a-f]{8,}\b|\b\d+\b', '#', message.lower())
            signature = hashlib.sha256((subsystem + normalized).encode()).hexdigest()[:16]
            return {'pid': '0', 'program': 'kernel/' + subsystem, 'signal': 'kernel fault',
                    'time': str(record.get('__REALTIME_TIMESTAMP', ''))[:30],
                    'boot_id': str(record.get('_BOOT_ID', ''))[:36],
                    'signature': signature, 'message': message[:500]}
    return None


def event_from_record(record):
    return kernel_event(record) if record.get('_TRANSPORT') == 'kernel' else crash_event(record)


def crash_event(record, uid=None):
    uid = os.getuid() if uid is None else uid
    if str(record.get('COREDUMP_UID', '')) != str(uid):
        return None
    pid = str(record.get('COREDUMP_PID', ''))
    if not pid.isdecimal():
        return None
    return {'pid': pid, 'program': str(record.get('COREDUMP_COMM', 'unknown'))[:100],
            'signal': str(record.get('COREDUMP_SIGNAL_NAME', 'unknown'))[:30],
            'time': str(record.get('__REALTIME_TIMESTAMP', ''))[:30]}


def save(state):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = STATE / 'crashes.json.tmp'
    with open(temporary, 'w', opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
        json.dump(state, output)
    temporary.replace(STATE / 'crashes.json')


def previous_boot():
    result = subprocess.run(['journalctl', '-b', '-1', '-k', '-p', 'warning', '-n', '200',
                             '-o', 'json', '--no-pager'], capture_output=True, text=True, timeout=10)
    events = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            try:
                event = kernel_event(json.loads(line))
            except (ValueError, TypeError):
                continue
            if event:
                events.append(event)
    return {'events': events[-10:], 'available': result.returncode == 0,
            'pstore_records': [p.name for p in Path('/sys/fs/pstore').glob('*') if p.is_file()][:10],
            'note': 'A panic can prevent final journal writes; missing records do not prove a clean boot.'}


def main():
    try:
        previous = previous_boot()
    except (OSError, subprocess.SubprocessError):
        previous = {'available': False, 'events': [], 'note': 'Previous-boot evidence unavailable'}
    state = {'status': 'Watching for application and kernel faults', 'events': [], 'previous_boot': previous}
    last = {}
    worker = None
    analyses = []
    fields = 'COREDUMP_UID,COREDUMP_COMM,COREDUMP_PID,COREDUMP_SIGNAL_NAME,__REALTIME_TIMESTAMP,_TRANSPORT,_BOOT_ID,MESSAGE'
    save(state)
    # Start from now: restarting never replays yesterday's crashes or starts old jobs.
    with subprocess.Popen(['journalctl', '-b', '-f', '-n', '0', '-o', 'json',
            '--output-fields=' + fields, 'MESSAGE_ID=' + MESSAGE_ID, '+', '_TRANSPORT=kernel'],
            stdout=subprocess.PIPE, text=True) as journal:
        for line in journal.stdout:
            try:
                event = event_from_record(json.loads(line))
            except (ValueError, TypeError):
                continue
            if event is None:
                continue
            now = time.monotonic()
            name = event['program']
            key = event.get('signature', name)
            if now - last.get(key, -1000) < (600 if 'signature' in event else 60):
                continue
            last[key] = now
            # Bounded dedupe state even if process names change continuously.
            last = dict(sorted(((key, stamp) for key, stamp in last.items() if now - stamp < 600),
                               key=lambda item: item[1])[-128:])
            state['events'] = (state['events'] + [event])[-10:]
            state['status'] = 'Crash detected: ' + name
            save(state)
            analyses = [stamp for stamp in analyses if now - stamp < 900]
            if (STATE / 'auto-diagnose').exists() and len(analyses) < 3 and (worker is None or worker.poll() is not None):
                # No shell, arbitrary command execution, or model-generated repairs.
                question = f"Diagnose the event from {name!r}, PID {event['pid']}, signal {event['signal']}. Cite evidence and uncertainties. Kernel signature: {event.get('signature', 'none')}."
                worker = subprocess.Popen([str(Path.home() / '.local/bin/mseries-troubleshoot'),
                    '--start', '--release-model', question], stdout=subprocess.DEVNULL, stderr=None)
                analyses.append(now)
        raise SystemExit('Journal stream ended; service will retry')


if __name__ == '__main__':
    main()
