#!/usr/bin/python3
"""Watch this user's coredumps, deduplicate, and optionally diagnose locally."""
import json
import os
from pathlib import Path
import subprocess
import time

MESSAGE_ID = 'fc2e22bc6ee647b6b90729ab34a250b1'
STATE = Path.home() / '.local/state/mseries-troubleshooter'


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


def main():
    state = {'status': 'Watching for crashes', 'events': []}
    last = {}
    worker = None
    fields = 'COREDUMP_UID,COREDUMP_COMM,COREDUMP_PID,COREDUMP_SIGNAL_NAME,__REALTIME_TIMESTAMP'
    save(state)
    # Start from now: restarting never replays yesterday's crashes or starts old jobs.
    with subprocess.Popen(['journalctl', '-b', '-f', '-n', '0', '-o', 'json',
            '--output-fields=' + fields, 'MESSAGE_ID=' + MESSAGE_ID],
            stdout=subprocess.PIPE, text=True) as journal:
        for line in journal.stdout:
            try:
                event = crash_event(json.loads(line))
            except (ValueError, TypeError):
                continue
            if event is None:
                continue
            now = time.monotonic()
            name = event['program']
            if now - last.get(name, -1000) < 60:
                continue
            last[name] = now
            # Bounded dedupe state even if process names change continuously.
            last = dict(sorted(((key, stamp) for key, stamp in last.items() if now - stamp < 600),
                               key=lambda item: item[1])[-128:])
            state['events'] = (state['events'] + [event])[-10:]
            state['status'] = 'Crash detected: ' + name
            save(state)
            if (STATE / 'auto-diagnose').exists() and (worker is None or worker.poll() is not None):
                # No shell, arbitrary command execution, or model-generated repairs.
                question = f"Diagnose the crash of {name!r}, PID {event['pid']}, signal {event['signal']}. Cite available evidence and uncertainties."
                worker = subprocess.Popen([str(Path.home() / '.local/bin/mseries-troubleshoot'),
                    '--start', question], stdout=subprocess.DEVNULL, stderr=None)
        raise SystemExit('Journal stream ended; service will retry')


if __name__ == '__main__':
    main()
