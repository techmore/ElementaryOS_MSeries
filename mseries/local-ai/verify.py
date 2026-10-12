#!/usr/bin/python3
"""Pending-verification checklist for this Mac, with history in SQLite.

Changes that can only be verified later (after a reboot, a login, or when the dock is plugged in) are
recorded as checks. A timer runs whatever has become applicable, stores every result, and notifies once
when a check passes, fails or needs a human look. Commands come only from the seed file next to this
tool (user-owned), never from a model.

  mseries-verify status [--json]      what is pending, passed or failed
  mseries-verify run [--notify]       run every check whose precondition holds now
  mseries-verify confirm ID yes|no [note...]   answer a "look at it yourself" check
  mseries-verify history [ID]         every recorded result
  mseries-verify reload               re-read the seed file (keeps recorded results)
  mseries-verify recheck ID           forget the outcome of one check so it runs again

States: waiting (precondition not met yet), passed, failed, ask (needs your yes/no).
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

STATE = Path.home() / '.local/state/mseries-troubleshooter'
DB = STATE / 'verify.db'
STATUS_JSON = STATE / 'verify-status.json'
SEED = Path.home() / '.local/share/mseries-verify/checks.json'
TIMEOUT = 25
SCHEMA = """
CREATE TABLE IF NOT EXISTS checks(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'auto',
  note TEXT, hint TEXT, precondition TEXT, command TEXT, after TEXT,
  state TEXT NOT NULL DEFAULT 'waiting', detail TEXT, updated REAL, passed_at REAL);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, check_id TEXT NOT NULL, ts REAL NOT NULL,
  boot_id TEXT, outcome TEXT NOT NULL, detail TEXT);
CREATE INDEX IF NOT EXISTS runs_check ON runs(check_id, ts);
"""


def connect():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    fresh = not DB.exists()
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    if fresh:
        os.chmod(DB, 0o600)
    return db


def boot_id():
    try:
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    except OSError:
        return ''


def load_seed(db, path=None):
    """Upsert check definitions; recorded state and history are kept."""
    seed = json.loads(Path(path or SEED).read_text())
    for item in seed['checks']:
        db.execute(
            """INSERT INTO checks(id,title,kind,note,hint,precondition,command,after,updated)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET title=excluded.title, kind=excluded.kind, note=excluded.note,
               hint=excluded.hint, precondition=excluded.precondition, command=excluded.command,
               after=excluded.after""",
            (item['id'], item['title'], item.get('kind', 'auto'), item.get('note'), item.get('hint'),
             item.get('precondition'), item.get('command'), item.get('after'), time.time()))
    db.commit()
    return len(seed['checks'])


def sh(command):
    """Run a read-only shell snippet; returns (exit status, trimmed output)."""
    try:
        result = subprocess.run(['/bin/bash', '-c', command], capture_output=True, text=True, timeout=TIMEOUT)
        out = (result.stdout + result.stderr).strip()
        return result.returncode, out[-600:]
    except subprocess.TimeoutExpired:
        return 124, f'timed out after {TIMEOUT}s'
    except OSError as error:
        return 127, str(error)


def record(db, check_id, outcome, detail):
    db.execute('INSERT INTO runs(check_id,ts,boot_id,outcome,detail) VALUES(?,?,?,?,?)',
               (check_id, time.time(), boot_id(), outcome, detail))


def evaluate(db, row):
    """Return (new state, detail) for one check, or None to leave it alone."""
    if row['state'] == 'passed':
        return None
    if row['after']:
        dep = db.execute('SELECT state FROM checks WHERE id=?', (row['after'],)).fetchone()
        if dep is None or dep['state'] != 'passed':
            return ('waiting', f"waiting for '{row['after']}' to pass first")
    if row['precondition']:
        status, out = sh(row['precondition'])
        if status != 0:
            return ('waiting', out or 'precondition not met yet')
    if row['kind'] == 'manual':
        # A manual answer sticks (yes -> passed, no -> failed) until `recheck`.
        return None if row['state'] in ('ask', 'failed') else ('ask', row['hint'] or 'please look and confirm')
    status, out = sh(row['command'] or 'false')
    return ('passed' if status == 0 else 'failed', out)


def notify(title, body):
    try:
        subprocess.run(['notify-send', '-a', 'Mac checklist', '-i', 'emblem-system-symbolic', title, body],
                       timeout=5, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


def write_status(db):
    rows = db.execute('SELECT id,title,kind,state,detail,updated,passed_at FROM checks ORDER BY rowid').fetchall()
    counts = {}
    for row in rows:
        counts[row['state']] = counts.get(row['state'], 0) + 1
    payload = {'generated': time.time(), 'counts': counts, 'items': [dict(row) for row in rows]}
    tmp = STATE / 'verify-status.json.tmp'
    with open(tmp, 'w', opener=lambda p, f: os.open(p, f, 0o600)) as out:
        json.dump(payload, out)
    tmp.replace(STATUS_JSON)
    return payload


def cmd_run(db, args):
    changed = []
    for _ in range(3):  # dependencies (after:) can unlock in the same pass
        progressed = False
        for row in db.execute('SELECT * FROM checks ORDER BY rowid').fetchall():
            row = db.execute('SELECT * FROM checks WHERE id=?', (row['id'],)).fetchone()
            verdict = evaluate(db, row)
            if verdict is None:
                continue
            state, detail = verdict
            if state == row['state'] and state in ('waiting', 'ask') or (
                    state == row['state'] == 'failed' and detail == row['detail']):
                continue
            db.execute('UPDATE checks SET state=?, detail=?, updated=?, passed_at=CASE WHEN ?=\'passed\' THEN ? ELSE passed_at END WHERE id=?',
                       (state, detail, time.time(), state, time.time(), row['id']))
            if state != 'waiting' or row['state'] != 'waiting':
                record(db, row['id'], state, detail)
            if state != 'waiting':
                progressed = True
                if state != row['state']:  # only a real change is worth a notification
                    changed.append((row['title'], state, detail))
        db.commit()
        if not progressed:
            break
    payload = write_status(db)
    for title, state, detail in changed:
        line = {'passed': '✓ ' + title, 'failed': '✗ ' + title, 'ask': '? ' + title}[state]
        print(f'{state:7s} {title}: {detail}')
        if args.notify:
            body = detail[:200] if state != 'ask' else detail[:160] + '  → open the Local Troubleshooter, or: mseries-verify confirm'
            notify(line, body)
    if not changed and not args.quiet:
        print('nothing changed;', ', '.join(f'{v} {k}' for k, v in sorted(payload['counts'].items())))
    return 0


def cmd_status(db, args):
    payload = write_status(db)
    if args.json:
        print(json.dumps(payload, indent=1))
        return 0
    icon = {'passed': '✓', 'failed': '✗', 'ask': '?', 'waiting': '…'}
    for item in payload['items']:
        when = time.strftime('%b %d %H:%M', time.localtime(item['updated'])) if item['updated'] else ''
        print(f"{icon.get(item['state'], '?')} {item['state']:7s} {item['id']:24s} {item['title']}")
        if item['state'] in ('failed', 'ask', 'waiting') and item['detail']:
            print(f"    {item['detail'][:150]}")
    print(', '.join(f'{v} {k}' for k, v in sorted(payload['counts'].items())))
    return 0


def cmd_confirm(db, args):
    row = db.execute('SELECT * FROM checks WHERE id=?', (args.id,)).fetchone()
    if row is None or row['kind'] != 'manual':
        print(f'{args.id}: not a manual check', file=sys.stderr)
        return 1
    ok = args.answer == 'yes'
    note = ' '.join(args.note) or ('confirmed by user' if ok else 'user reported a problem')
    state = 'passed' if ok else 'failed'
    db.execute('UPDATE checks SET state=?, detail=?, updated=?, passed_at=? WHERE id=?',
               (state, note, time.time(), time.time() if ok else row['passed_at'], args.id))
    record(db, args.id, state, note)
    db.commit()
    write_status(db)
    print(f'{args.id}: {state}')
    return 0


def cmd_history(db, args):
    query = 'SELECT * FROM runs'
    params = ()
    if args.id:
        query += ' WHERE check_id=?'
        params = (args.id,)
    for row in db.execute(query + ' ORDER BY ts DESC LIMIT 60', params):
        stamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(row['ts']))
        print(f"{stamp} {row['check_id']:24s} {row['outcome']:7s} {(row['detail'] or '')[:110]!r}")
    return 0


def cmd_recheck(db, args):
    db.execute("UPDATE checks SET state='waiting', detail=NULL, updated=? WHERE id=?", (time.time(), args.id))
    db.commit()
    write_status(db)
    print(f'{args.id}: will run again')
    return 0


def cmd_reload(db, args):
    print(f'{load_seed(db, args.seed)} checks loaded')
    write_status(db)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    run = sub.add_parser('run')
    run.add_argument('--notify', action='store_true')
    run.add_argument('--quiet', action='store_true')
    run.set_defaults(func=cmd_run)
    status = sub.add_parser('status')
    status.add_argument('--json', action='store_true')
    status.set_defaults(func=cmd_status)
    confirm = sub.add_parser('confirm')
    confirm.add_argument('id')
    confirm.add_argument('answer', choices=['yes', 'no'])
    confirm.add_argument('note', nargs='*')
    confirm.set_defaults(func=cmd_confirm)
    history = sub.add_parser('history')
    history.add_argument('id', nargs='?')
    history.set_defaults(func=cmd_history)
    recheck = sub.add_parser('recheck')
    recheck.add_argument('id')
    recheck.set_defaults(func=cmd_recheck)
    reload_ = sub.add_parser('reload')
    reload_.add_argument('--seed')
    reload_.set_defaults(func=cmd_reload)
    args = parser.parse_args(argv)
    db = connect()
    if args.cmd in ('run', 'status') and not db.execute('SELECT 1 FROM checks LIMIT 1').fetchone() and SEED.exists():
        load_seed(db)
    return args.func(db, args)


if __name__ == '__main__':
    raise SystemExit(main())
