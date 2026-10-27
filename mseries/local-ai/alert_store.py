"""Private bounded alert inbox. No inference, notifications, journal or app access.

A journal cursor is an event identity, not a storm fingerprint. Event insertion,
incident count and source progress share one SQLite transaction. Attention is
independent of fault health: acknowledgement never establishes resolution.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

SCHEMA = 1
MAX_ALERTS = 256
MAX_EVENTS = 2048
MAX_GAPS = 64
MAX_SOURCES = 8
ATTENTION = ('new', 'seen', 'acknowledged')
SOURCE_STATUS = ('starting', 'watching', 'backfill', 'waiting', 'stopped', 'unavailable')
GAP_REASONS = ('cursor-unavailable', 'journal-unavailable', 'stream-ended',
               'malformed-record', 'record-too-large', 'backfill-limit', 'missing-cursor')
DEFAULT_DIRECTORY = Path.home()/'.local/state/mseries-troubleshooter'


class AlertConflict(ValueError):
    pass


class AlertUnavailable(ValueError):
    pass


def bounded_text(value, limit):
    if not isinstance(value, str): value = str(value)
    value = value.encode('utf-8', errors='replace').decode('utf-8')
    value = ''.join(c if ord(c) >= 32 and ord(c) != 127 else ' ' for c in value)
    return value[:limit]


def evidence(value):
    value = bounded_text(value, 4000).replace(str(Path.home()), '~')
    value = re.sub(r'(?i)(authorization\s*:\s*bearer\s+)\S+', r'\1[REDACTED]', value)
    value = re.sub(r'(?i)\b(password|passwd|token|api[_-]?key|secret)(\s*[=:]\s*)[^\s,;]+', r'\1\2[REDACTED]', value)
    value = re.sub(r'\bsk-[A-Za-z0-9_-]{12,}\b', '[REDACTED]', value)
    return value[:500]


def source_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,63}', value):
        raise ValueError('Invalid alert source')
    return value


def event_identity(source, cursor):
    source_name(source)
    if (not isinstance(cursor, str) or not 0 < len(cursor) <= 2048
            or any(ord(c) < 32 or ord(c) == 127 for c in cursor)):
        raise ValueError('Missing or invalid source cursor')
    return hashlib.sha256((source+'\0'+cursor).encode()).hexdigest()


def normalized_event(event):
    if not isinstance(event, dict): raise ValueError('Expected a classified alert')
    program = evidence(event.get('program', 'unknown'))[:100]
    signal = evidence(event.get('signal', 'unknown'))[:40]
    kind = 'kernel' if program.startswith('kernel/') else 'coredump'
    subsystem = program[7:47] if kind == 'kernel' else 'application'
    signature = event.get('signature')
    if not isinstance(signature, str) or not re.fullmatch(r'[a-f0-9]{16,64}', signature):
        signature = hashlib.sha256((program+'\0'+signal).encode()).hexdigest()[:16]
    pid = event.get('pid', '0')
    pid = str(pid) if str(pid).isdecimal() and len(str(pid)) <= 20 else '0'
    return {'program': program, 'signal': signal, 'kind': kind, 'subsystem': subsystem,
            'fingerprint': signature, 'pid': pid, 'evidence': evidence(event.get('message', '')),
            'severity': 'critical' if subsystem in ('oops', 'lockup') else 'error'}


class AlertStore:
    def __init__(self, directory=None, *, read_only=False, clock=time.time):
        self.directory = (Path(directory) if directory is not None else DEFAULT_DIRECTORY).absolute()
        self.path = self.directory/'alerts.sqlite3'
        self.read_only, self.clock = read_only, clock
        if not read_only: self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        try: self._private(self.directory, directory=True)
        except FileNotFoundError: raise AlertUnavailable('Alert inbox has not been created') from None
        if read_only and stat.S_IMODE(self.directory.stat().st_mode) & 0o077:
            raise AlertUnavailable('Alert directory is not private')
        if not read_only:
            self.directory.chmod(0o700)
            try:
                fd = os.open(self.path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
            except FileExistsError: pass
            else: os.close(fd)
        try: self._private(self.path)
        except FileNotFoundError: raise AlertUnavailable('Alert inbox has not been created') from None
        if not read_only:
            with self._db() as db:
                db.executescript('''
                    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS sources(source TEXT PRIMARY KEY,cursor TEXT,boot_id TEXT,
                        observed_us INTEGER,updated_at REAL,status TEXT NOT NULL DEFAULT 'starting');
                    CREATE TABLE IF NOT EXISTS alerts(alert_id TEXT PRIMARY KEY,source TEXT NOT NULL,
                        boot_id TEXT NOT NULL,fingerprint TEXT NOT NULL,kind TEXT NOT NULL,subsystem TEXT NOT NULL,
                        severity TEXT NOT NULL,program TEXT NOT NULL,signal TEXT NOT NULL,pid TEXT NOT NULL,
                        first_seen_us INTEGER NOT NULL,last_seen_us INTEGER NOT NULL,occurrence_count INTEGER NOT NULL,
                        attention TEXT NOT NULL,version INTEGER NOT NULL,last_event_id TEXT NOT NULL,
                        evidence TEXT NOT NULL,replayed INTEGER NOT NULL);
                    CREATE INDEX IF NOT EXISTS incident_group ON alerts(source,boot_id,fingerprint,last_seen_us);
                    CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY,source TEXT NOT NULL,
                        cursor TEXT NOT NULL,alert_id TEXT,observed_us INTEGER NOT NULL,created_at REAL NOT NULL,
                        UNIQUE(source,cursor));
                    CREATE TABLE IF NOT EXISTS gaps(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,
                        reason TEXT NOT NULL,created_at REAL NOT NULL,cursor TEXT);
                ''')
                found = db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
                if found and found[0] != str(SCHEMA): raise ValueError('Unsupported alert store schema')
                db.execute("INSERT OR IGNORE INTO meta VALUES('schema',?)", (str(SCHEMA),))
        else:
            with self._db() as db:
                row = db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
                if not row or row[0] != str(SCHEMA): raise ValueError('Unsupported alert store schema')

    @staticmethod
    def _private(path, directory=False):
        info = path.lstat()
        if info.st_uid != os.getuid() or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
            raise ValueError('Alert store path must be a regular owned private path')
        if not directory and stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('Alert database is not private')

    @contextmanager
    def _db(self, write=False):
        if write and self.read_only: raise ValueError('Alert store is read-only')
        self._private(self.path)
        for suffix in ('-wal', '-shm'):
            path = Path(str(self.path)+suffix)
            try: self._private(path)
            except FileNotFoundError: pass  # SQLite removes idle WAL/SHM files between connections.
        try:
            db = sqlite3.connect(self.path.as_uri()+'?mode=ro' if self.read_only else self.path,
                                 uri=self.read_only, timeout=2, isolation_level=None)
        except sqlite3.Error:
            raise AlertUnavailable('Alert inbox is unavailable or busy') from None
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA busy_timeout=2000')
            if not self.read_only:
                db.execute('PRAGMA journal_mode=WAL'); db.execute('PRAGMA synchronous=FULL')
                db.execute('PRAGMA wal_autocheckpoint=64')
            if write: db.execute('BEGIN IMMEDIATE')
            yield db
            if write: db.commit()
        except sqlite3.Error:
            if write: db.rollback()
            raise AlertUnavailable('Alert inbox is unavailable or busy') from None
        except BaseException:
            if write: db.rollback()
            raise
        finally: db.close()

    def _source(self, db, source):
        source_name(source)
        if not db.execute('SELECT 1 FROM sources WHERE source=?', (source,)).fetchone():
            if db.execute('SELECT count(*) FROM sources').fetchone()[0] >= MAX_SOURCES:
                raise ValueError('Alert source bound exceeded')
            db.execute('INSERT INTO sources(source,updated_at) VALUES(?,?)', (source,self.clock()))

    def _prune(self, db):
        for table, maximum, order in [('alerts',MAX_ALERTS,"CASE attention WHEN 'acknowledged' THEN 0 ELSE 1 END,last_seen_us"),
                                      ('events',MAX_EVENTS,'created_at,rowid'), ('gaps',MAX_GAPS,'id')]:
            count = db.execute('SELECT count(*) FROM '+table).fetchone()[0]
            if count > maximum:
                db.execute('DELETE FROM '+table+' WHERE rowid IN (SELECT rowid FROM '+table+' ORDER BY '+order+' LIMIT ?)', (count-maximum,))
                key = 'discarded_'+table
                db.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+excluded.value', (key,str(count-maximum)))

    @staticmethod
    def _row(row):
        if row is None: return None
        result = dict(row); result['replayed'] = bool(result['replayed'])
        result['resolved'] = False
        return result

    def ingest(self, source, cursor, boot_id, observed_us, event_or_none, *, replayed=False):
        identifier = event_identity(source,cursor)
        if not isinstance(boot_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,64}',boot_id):
            raise ValueError('Invalid boot identity')
        if type(observed_us) not in (int,str): raise ValueError('Invalid source timestamp')
        try: observed_us = int(observed_us)
        except (ValueError,TypeError): raise ValueError('Invalid source timestamp') from None
        if not 0 <= observed_us <= 2**63-1: raise ValueError('Invalid source timestamp')
        event = None if event_or_none is None else normalized_event(event_or_none)
        with self._db(write=True) as db:
            self._source(db,source)
            duplicate = db.execute('SELECT alert_id FROM events WHERE event_id=?',(identifier,)).fetchone()
            if duplicate:
                current = db.execute('SELECT status,cursor FROM sources WHERE source=?',(source,)).fetchone()
                if current['status']=='backfill' or current['cursor'] is None:
                    db.execute('UPDATE sources SET cursor=?,boot_id=?,observed_us=?,updated_at=? WHERE source=?',(cursor,boot_id,observed_us,self.clock(),source))
                return {'duplicate':True,'event_id':identifier,'alert':self._row(db.execute('SELECT * FROM alerts WHERE alert_id=?',(duplicate['alert_id'],)).fetchone())}
            alert_id = None
            if event:
                window = (600 if event['kind']=='kernel' else 60)*1_000_000
                old = db.execute('SELECT * FROM alerts WHERE source=? AND boot_id=? AND fingerprint=? AND last_seen_us BETWEEN ? AND ? ORDER BY last_seen_us DESC LIMIT 1',
                    (source,boot_id,event['fingerprint'],observed_us-window,observed_us+window)).fetchone()
                if old:
                    alert_id = old['alert_id']
                    db.execute('UPDATE alerts SET last_seen_us=?,first_seen_us=?,occurrence_count=min(occurrence_count+1,9223372036854775807),attention=\'new\',version=version+1,last_event_id=?,evidence=?,pid=?,replayed=? WHERE alert_id=?',
                        (max(observed_us,old['last_seen_us']),min(observed_us,old['first_seen_us']),identifier,event['evidence'],event['pid'],int(bool(replayed)),alert_id))
                else:
                    alert_id = identifier
                    values = (alert_id,source,boot_id,event['fingerprint'],event['kind'],event['subsystem'],event['severity'],event['program'],event['signal'],event['pid'],observed_us,observed_us,1,'new',1,identifier,event['evidence'],int(bool(replayed)))
                    db.execute('INSERT INTO alerts VALUES('+','.join('?'*18)+')',values)
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(identifier,source,cursor,alert_id,observed_us,self.clock()))
            db.execute('UPDATE sources SET cursor=?,boot_id=?,observed_us=?,updated_at=? WHERE source=?',
                       (cursor,boot_id,observed_us,self.clock(),source))
            self._prune(db)
            row = db.execute('SELECT * FROM alerts WHERE alert_id=?',(alert_id,)).fetchone()
            return {'duplicate':False,'event_id':identifier,'alert':self._row(row)}

    def source_state(self, source):
        source_name(source)
        with self._db() as db:
            row=db.execute('SELECT * FROM sources WHERE source=?',(source,)).fetchone()
            return dict(row) if row else None

    def set_collector_status(self, source, status):
        if status not in SOURCE_STATUS: raise ValueError('Invalid collector status')
        with self._db(write=True) as db:
            self._source(db,source)
            db.execute('UPDATE sources SET status=?,updated_at=? WHERE source=?',(status,self.clock(),source))

    def record_gap(self, source, reason):
        if reason not in GAP_REASONS: raise ValueError('Use a bounded collector gap reason')
        with self._db(write=True) as db:
            self._source(db,source)
            current=db.execute('SELECT cursor FROM sources WHERE source=?',(source,)).fetchone()
            # Consecutive identical gaps at the same cursor are one gap, not a storm.
            latest=db.execute('SELECT * FROM gaps WHERE source=? ORDER BY id DESC LIMIT 1',(source,)).fetchone()
            if not latest or latest['reason']!=reason or latest['cursor']!=current['cursor']:
                db.execute('INSERT INTO gaps(source,reason,created_at,cursor) VALUES(?,?,?,?)',(source,reason,self.clock(),current['cursor']))
            self._prune(db)

    def clear_cursor(self, source):
        """Only after recording a cursor gap; reanchor without pretending no loss."""
        with self._db(write=True) as db:
            self._source(db,source)
            if not db.execute('SELECT 1 FROM gaps WHERE source=?',(source,)).fetchone():
                raise ValueError('Record the collection gap before clearing a cursor')
            db.execute('UPDATE sources SET cursor=NULL,status=\'backfill\',updated_at=? WHERE source=?',(self.clock(),source))

    def get_alert(self, alert_id):
        if not isinstance(alert_id,str) or not re.fullmatch('[a-f0-9]{64}',alert_id): raise ValueError('Invalid alert identity')
        with self._db() as db: return self._row(db.execute('SELECT * FROM alerts WHERE alert_id=?',(alert_id,)).fetchone())

    def list_alerts(self, limit=50, attention=None):
        if type(limit) is not int or not 1 <= limit <= MAX_ALERTS: raise ValueError('Use a bounded alert limit')
        if attention is not None and attention not in ATTENTION: raise ValueError('Invalid attention filter')
        with self._db() as db:
            rows=db.execute('SELECT * FROM alerts'+(' WHERE attention=?' if attention else '')+' ORDER BY last_seen_us DESC,alert_id DESC LIMIT ?',
                            ((attention,limit) if attention else (limit,))).fetchall()
            return [self._row(row) for row in rows]

    def _attention(self, alert_id, expected_version, state):
        if type(expected_version) is not int or expected_version < 1: raise ValueError('Supply the observed alert version')
        self.get_alert(alert_id)  # Validate identity before beginning the write.
        with self._db(write=True) as db:
            row=db.execute('SELECT * FROM alerts WHERE alert_id=?',(alert_id,)).fetchone()
            if row is None: raise ValueError('Alert is no longer retained')
            if row['attention']==state and row['version'] in (expected_version,expected_version+1): return self._row(row)
            if row['version']!=expected_version: raise AlertConflict('Alert changed; read the latest occurrence before acknowledging')
            if state=='seen' and row['attention']=='acknowledged': raise AlertConflict('Acknowledged attention cannot be downgraded')
            db.execute('UPDATE alerts SET attention=?,version=version+1 WHERE alert_id=?',(state,alert_id))
            return self._row(db.execute('SELECT * FROM alerts WHERE alert_id=?',(alert_id,)).fetchone())

    def acknowledge(self, alert_id, expected_version): return self._attention(alert_id,expected_version,'acknowledged')
    def mark_seen(self, alert_id, expected_version): return self._attention(alert_id,expected_version,'seen')

    def set_previous_boot(self, value):
        events=[]
        for old in value.get('events',[])[:10]:
            row=normalized_event(old)
            events.append({'program':row['program'],'signal':row['signal'],'pid':row['pid'],
                           'signature':row['fingerprint'],'message':row['evidence'],
                           'time':bounded_text(old.get('time',''),30),'boot_id':bounded_text(old.get('boot_id',''),64)})
        record={'events':events,'available':bool(value.get('available')),
                'pstore_records':[bounded_text(x,100) for x in value.get('pstore_records',[])[:10]],
                'note':'Missing previous-boot evidence does not establish a clean boot.'}
        with self._db(write=True) as db:
            db.execute('INSERT INTO meta VALUES(\'previous_boot\',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(json.dumps(record),))

    def legacy_snapshot(self, limit=10):
        alerts=self.list_alerts(limit)
        with self._db() as db:
            sources=[dict(row) for row in db.execute('SELECT * FROM sources ORDER BY source')]
            gaps=[dict(row) for row in db.execute('SELECT * FROM gaps ORDER BY id DESC LIMIT 10')]
            retained={row['key']:int(row['value']) for row in db.execute('SELECT * FROM meta WHERE key LIKE \'discarded_%\'')}
            previous=db.execute('SELECT value FROM meta WHERE key=\'previous_boot\'').fetchone()
        events=[{'pid':a['pid'],'program':a['program'],'signal':a['signal'],'time':str(a['last_seen_us']),
                 'boot_id':a['boot_id'],'signature':a['fingerprint'],'message':a['evidence'],
                 'alert_id':a['alert_id'],'occurrence_count':a['occurrence_count'],'attention':a['attention'],
                 'version':a['version'],'resolved':False,'replayed':a['replayed']} for a in alerts]
        return {'schema':SCHEMA,'available':True,'status':'Alert inbox; collection status is separate from fault health',
                'events':events,'previous_boot':json.loads(previous[0]) if previous else {'available':False,'events':[],'note':'Previous-boot evidence unavailable'},
                'collector':{'sources':sources,'gaps':gaps,'retention':retained,'notifications':'disabled','automatic_diagnosis':False}}

    def write_legacy(self):
        """Compatibility projection only; database remains authoritative."""
        import tempfile
        fd,name=tempfile.mkstemp(prefix='.crashes-',dir=self.directory)
        try:
            with os.fdopen(fd,'w') as stream:
                os.fchmod(stream.fileno(),0o600);json.dump(self.legacy_snapshot(),stream);stream.flush();os.fsync(stream.fileno())
            os.replace(name,self.directory/'crashes.json')
        finally:
            if os.path.exists(name):os.unlink(name)
