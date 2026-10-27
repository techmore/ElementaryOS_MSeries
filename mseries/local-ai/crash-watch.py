#!/usr/bin/python3
"""Durable bounded kernel/current-user fault inbox; never launches model diagnosis."""
import json
import os
from pathlib import Path
import subprocess
import time
import hashlib
import re
from alert_store import AlertUnavailable

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


# Only bounded metadata enters the durable store. Raw journal records are never
# persisted or passed to a model, and the legacy auto-diagnose marker is ignored.
SOURCE = 'journal'
MAX_LINE = 32768
BACKFILL_LIMIT = 200
COMMAND_DEADLINE = 10
FIELDS = '__CURSOR,__REALTIME_TIMESTAMP,_BOOT_ID,_TRANSPORT,COREDUMP_UID,COREDUMP_COMM,COREDUMP_PID,COREDUMP_SIGNAL_NAME,MESSAGE'


def previous_boot():
    result = subprocess.run(['journalctl', '-b', '-1', '-k', '-p', 'warning', '-n', '200',
                             '-o', 'json', '--no-pager'], capture_output=True, text=True, timeout=10)
    events = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if len(line) > MAX_LINE: continue
            try: event = kernel_event(json.loads(line))
            except (ValueError, TypeError): continue
            if event: events.append(event)
    return {'events': events[-10:], 'available': result.returncode == 0,
            'pstore_records': [p.name for p in Path('/sys/fs/pstore').glob('*') if p.is_file()][:10],
            'note': 'A panic can prevent final journal writes; missing records do not prove a clean boot.'}


def journal_command(*, cursor=None, follow=False, tail=None, since=None, current_boot=False):
    command = ['journalctl','-o','json','--no-pager','--output-fields='+FIELDS]
    if cursor: command += ['--after-cursor='+cursor]
    if follow: command.append('--follow')
    if tail is not None: command += ['-n',str(tail)]
    if since is not None: command += ['--since=@'+str(int(since))]
    if current_boot: command.append('-b')
    return command+['MESSAGE_ID='+MESSAGE_ID,'+','_TRANSPORT=kernel']


class Collector:
    def __init__(self, store, *, runner=None, clock=time.time):
        self.store, self.clock = store, clock
        self.started_us = int(clock()*1_000_000)
        self.runner = runner if runner is not None else self.run_command
        self.pending = False
        self.last_projection = 0

    def flush(self, force=False):
        if force or (self.pending and time.monotonic()-self.last_projection >= 1):
            self.store.write_legacy();self.pending=False;self.last_projection=time.monotonic()

    def record(self, raw, *, replayed=None, anchor=False):
        try:
            row=json.loads(raw)
            if not isinstance(row,dict):raise ValueError()
            stamp=int(row['__REALTIME_TIMESTAMP'])
            self.store.ingest(SOURCE,row['__CURSOR'],row['_BOOT_ID'],stamp,
                              None if anchor else event_from_record(row),
                              replayed=(stamp<self.started_us if replayed is None else replayed))
        except AlertUnavailable:
            raise
        except (ValueError,TypeError,KeyError):
            self.store.record_gap(SOURCE,'missing-cursor' if isinstance(locals().get('row'),dict) and not row.get('__CURSOR') else 'malformed-record')
        self.pending=True

    def run_command(self, command, *, replayed=None, anchor=False):
        """Drain bounded pipes without retaining a journal or unbounded stderr."""
        import select
        import signal
        try: child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        except OSError:
            return {'returncode':1,'cursor_unavailable':False,'records':0}
        buffer=bytearray();dropping=False;errors=bytearray();records=0
        deadline=None if '--follow' in command else time.monotonic()+COMMAND_DEADLINE
        streams={child.stdout:'stdout',child.stderr:'stderr'}
        for stream in streams:os.set_blocking(stream.fileno(),False)
        try:
            while streams:
                if deadline is not None and time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command,COMMAND_DEADLINE)
                ready,_,_=select.select(list(streams),[],[],.5)
                self.flush()
                for stream in ready:
                    try:chunk=os.read(stream.fileno(),65536)
                    except BlockingIOError:continue
                    if not chunk:
                        del streams[stream];continue
                    if stream is child.stderr:
                        errors.extend(chunk[:max(0,4096-len(errors))]);continue
                    for piece in chunk.splitlines(keepends=True):
                        ended=piece.endswith(b'\n')
                        if not dropping:
                            buffer.extend(piece)
                            if len(buffer)>MAX_LINE:
                                dropping=True;buffer.clear();self.store.record_gap(SOURCE,'record-too-large');self.pending=True
                        if ended:
                            if not dropping:
                                self.record(bytes(buffer),replayed=replayed,anchor=anchor);records+=1
                            buffer.clear();dropping=False
            if buffer or dropping:
                self.store.record_gap(SOURCE,'malformed-record');self.pending=True
            rc=child.wait(timeout=3)
        finally:
            if child.poll() is None:
                try:os.killpg(child.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:child.wait(2)
                except subprocess.TimeoutExpired:
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    child.wait(2)
            child.stdout.close();child.stderr.close();self.flush(force=True)
        error=errors.decode('utf-8',errors='replace').lower()
        return {'returncode':rc,'cursor_unavailable':bool(rc and 'cursor' in error and any(x in error for x in ('seek','invalid','not found','unavailable'))),'records':records}

    def invoke(self, command, **options):
        try:return self.runner(command,**options)
        except InterruptedError:
            raise
        except (OSError,subprocess.SubprocessError):
            self.store.record_gap(SOURCE,'journal-unavailable')
            self.store.set_collector_status(SOURCE,'unavailable');self.flush(force=True)
            return {'returncode':1,'cursor_unavailable':False,'records':0}

    def run(self, previous=None):
        self.store.set_collector_status(SOURCE,'starting')
        if previous is not None:self.store.set_previous_boot(previous)
        state=self.store.source_state(SOURCE)
        if not state['cursor'] and state['observed_us'] is None:
            # Anchor only: old selected events are not fresh alerts at startup.
            result=self.invoke(journal_command(tail=1,current_boot=True),anchor=True)
            if result['returncode']:
                self.store.record_gap(SOURCE,'journal-unavailable');self.store.set_collector_status(SOURCE,'unavailable');self.flush(force=True);return 1
            state=self.store.source_state(SOURCE)
        self.store.set_collector_status(SOURCE,'watching');self.flush(force=True)
        result=self.invoke(journal_command(cursor=state['cursor'],follow=True,
                                           since=None if state['cursor'] else self.clock()))
        if result['cursor_unavailable']:
            self.store.record_gap(SOURCE,'cursor-unavailable');self.store.clear_cursor(SOURCE)
            result=self.invoke(journal_command(tail=BACKFILL_LIMIT),replayed=True)
            if result['records']>=BACKFILL_LIMIT:self.store.record_gap(SOURCE,'backfill-limit')
            if result['returncode']==0:
                state=self.store.source_state(SOURCE)
                self.store.set_collector_status(SOURCE,'watching');self.flush(force=True)
                result=self.invoke(journal_command(cursor=state['cursor'],follow=True,
                                                   since=None if state['cursor'] else self.clock()))
        self.store.record_gap(SOURCE,'stream-ended' if result['returncode']==0 else 'journal-unavailable')
        self.store.set_collector_status(SOURCE,'unavailable');self.flush(force=True)
        return 1


def main(argv=None):
    import argparse
    from alert_store import AlertStore
    parser=argparse.ArgumentParser(description='Durable kernel/current-user coredump alert inbox; no automatic diagnosis or popups')
    parser.add_argument('--state-dir',type=Path,default=STATE)
    parser.add_argument('--replay-file',type=Path,help='Import a chosen synthetic JSONL fixture without journal access')
    args=parser.parse_args(argv)
    store=AlertStore(args.state_dir)
    # One collector owns this source cursor. Readers/acknowledgers use SQLite
    # transactions independently; another collector must not race its frontier.
    import fcntl
    fd=os.open(args.state_dir/'collector.lock',os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('The alert collector is already running') from None
        collector=Collector(store)
        if args.replay_file:
            store.set_collector_status(SOURCE,'backfill')
            with args.replay_file.open('rb') as source:
                while True:
                    raw=source.readline(MAX_LINE+1)
                    if not raw:break
                    if len(raw)>MAX_LINE:
                        store.record_gap(SOURCE,'record-too-large')
                        while raw and not raw.endswith(b'\n'):raw=source.readline(MAX_LINE+1)
                        continue
                    collector.record(raw,replayed=True)
            store.set_collector_status(SOURCE,'stopped');collector.flush(force=True);return 0
        import signal
        previous_term=signal.getsignal(signal.SIGTERM)
        def stopped(_signum,_frame):raise InterruptedError('Owned alert collector stopped')
        signal.signal(signal.SIGTERM,stopped)
        try:
            try:previous=previous_boot()
            except (OSError,subprocess.SubprocessError):previous={'available':False,'events':[]}
            return collector.run(previous)
        except InterruptedError:
            store.set_collector_status(SOURCE,'stopped');collector.flush(force=True);return 0
        finally:signal.signal(signal.SIGTERM,previous_term)


if __name__=='__main__':raise SystemExit(main())
