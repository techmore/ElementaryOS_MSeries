#!/usr/bin/env python3
"""netusage: lightweight per-process / per-host network usage logger.

Runs as a systemd *user* service, no root needed.

* Per-connection byte counters (and the owning process) come from `ss -tinpHO`. The counters
  are cumulative per socket, so we only need to diff them between polls. Polling is skipped
  entirely while the interface counters in /proc/net/dev show the link is idle.
* Hostnames come from systemd-resolved's query monitor (`resolvectl monitor --json=short`),
  which gives both per-hostname query counts and name -> IP answers, so remote IPs can be shown
  as hostnames without issuing any reverse lookups of our own.
* Everything is aggregated in memory and flushed to SQLite (WAL) every FLUSH_SECONDS.

Only TCP is covered (the kernel keeps no byte counters for UDP sockets), so QUIC/HTTP3 traffic
is not attributed to apps. /proc/net/dev remains the source of truth for total throughput.
"""

import collections
import ipaddress
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time

POLL_SECONDS = 5
IDLE_FORCE_SECONDS = 30       # poll at least this often even if the link looks idle
IDLE_BYTES = 512              # /proc/net/dev delta below which a poll is skipped
FLUSH_SECONDS = 15
CACHE_REFRESH_SECONDS = 600
MINUTE_RETENTION = 2 * 86400
HOUR_RETENTION = 90 * 86400

DB_PATH = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "netusage", "usage.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_minute (
    ts INTEGER NOT NULL, proc TEXT NOT NULL, host TEXT NOT NULL,
    rx INTEGER NOT NULL DEFAULT 0, tx INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ts, proc, host)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS usage_hour (
    ts INTEGER NOT NULL, proc TEXT NOT NULL, host TEXT NOT NULL,
    rx INTEGER NOT NULL DEFAULT 0, tx INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ts, proc, host)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS dns_hour (
    ts INTEGER NOT NULL, name TEXT NOT NULL,
    queries INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ts, name)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

# comm names that say nothing about the program; use the script name instead.
GENERIC_COMMS = {"python", "python3", "node", "nodejs", "ruby", "perl", "java", "bash", "sh", "deno", "bun"}

stop = threading.Event()
lock = threading.Lock()

# (minute_ts, proc, host) -> [rx, tx]
pending_usage = collections.defaultdict(lambda: [0, 0])
# (hour_ts, name) -> [queries, failures]
pending_dns = collections.defaultdict(lambda: [0, 0])
# ip string -> hostname
ip_names = {}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- process naming

_pid_names = {}


def proc_name(pid, comm):
    cached = _pid_names.get(pid)
    if cached and cached[0] == comm:
        return cached[1]

    name = comm
    if comm.lower() in GENERIC_COMMS:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                args = f.read().split(b"\0")
            for arg in args[1:]:
                arg = arg.decode("utf-8", "replace")
                if arg and not arg.startswith("-"):
                    name = os.path.basename(arg)
                    break
        except OSError:
            pass

    if len(_pid_names) > 4096:
        _pid_names.clear()
    _pid_names[pid] = (comm, name)
    return name


# ---------------------------------------------------------------- DNS

def addr_to_str(octets):
    try:
        return str(ipaddress.ip_address(bytes(octets)))
    except ValueError:
        return None


def learn_answers(name, answers):
    for entry in answers or ():
        addr = entry.get("rr", {}).get("address")
        if addr and len(addr) in (4, 16):
            ip = addr_to_str(addr)
            if ip:
                ip_names[ip] = name


def load_cache_dump():
    """Seed ip -> name from resolved's cache so we have names for connections that predate us."""
    try:
        out = subprocess.run(
            ["resolvectl", "--no-ask-password", "show-cache", "--json=short"], capture_output=True, timeout=10
        ).stdout
        for link in json.loads(out):
            for item in link.get("cache", ()):
                name = item.get("key", {}).get("name")
                for rr in item.get("rrs") or ():
                    addr = rr.get("rr", {}).get("address")
                    if name and addr and len(addr) in (4, 16):
                        ip = addr_to_str(addr)
                        if ip:
                            ip_names.setdefault(ip, name)
    except Exception as e:  # noqa: BLE001 - best effort only
        log(f"cache dump failed: {e}")


def ignore_name(name):
    return name == "localhost" or name.endswith(".arpa") or name.endswith(".localhost")


def dns_monitor():
    """Runs in a thread; restarts the monitor if resolved restarts."""
    recent_a = {}
    while not stop.is_set():
        try:
            proc = subprocess.Popen(
                ["resolvectl", "--no-ask-password", "monitor", "--json=short"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            )
        except OSError as e:
            log(f"cannot start resolvectl monitor: {e}")
            stop.wait(30)
            continue

        for line in proc.stdout:
            if stop.is_set():
                break
            try:
                msg = json.loads(line)
                q = msg["question"][0]
            except (ValueError, KeyError, IndexError):
                continue

            name = q.get("name", "").lower().rstrip(".")
            if not name or ignore_name(name):
                continue

            qtype = q.get("type")
            ok = msg.get("state") == "success"
            now = time.time()

            with lock:
                if ok:
                    learn_answers(name, msg.get("answer"))

                # Count one lookup per name: A queries, plus AAAA only when no A just preceded it.
                count = False
                if qtype == 1:
                    recent_a[name] = now
                    count = True
                elif qtype == 28:
                    count = now - recent_a.get(name, 0) > 3
                if count:
                    hour = int(now) // 3600 * 3600
                    entry = pending_dns[(hour, name)]
                    entry[0] += 1
                    if not ok:
                        entry[1] += 1

            if len(recent_a) > 2048:
                recent_a.clear()

        proc.kill()
        proc.wait()
        if not stop.is_set():
            stop.wait(10)


# ---------------------------------------------------------------- sockets

SS_USERS = re.compile(r'\("([^"]*)",pid=(\d+)')
SS_BYTES_SENT = re.compile(r"\bbytes_sent:(\d+)")
SS_BYTES_RECV = re.compile(r"\bbytes_received:(\d+)")


def split_hostport(s):
    host, _, port = s.rpartition(":")
    return host.strip("[]"), port


def is_loopback(ip):
    try:
        return ipaddress.ip_address(ip.split("%")[0]).is_loopback
    except ValueError:
        return False


def read_sockets():
    """Returns {(local, peer): (proc, remote_ip, rx, tx)} for non-loopback TCP sockets."""
    try:
        out = subprocess.run(
            ["ss", "-tinpHO"], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError) as e:
        log(f"ss failed: {e}")
        return {}

    result = {}
    for line in out.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6:
            continue
        local, peer, rest = fields[3], fields[4], fields[5]
        rx_m = SS_BYTES_RECV.search(rest)
        tx_m = SS_BYTES_SENT.search(rest)
        if not rx_m and not tx_m:
            continue

        remote_ip, _ = split_hostport(peer)
        if is_loopback(remote_ip):
            continue

        users = SS_USERS.search(rest)
        proc = proc_name(int(users.group(2)), users.group(1)) if users else "(other)"
        result[(local, peer)] = (
            proc, remote_ip, int(rx_m.group(1)) if rx_m else 0, int(tx_m.group(1)) if tx_m else 0
        )
    return result


class Sampler:
    def __init__(self):
        self.prev = None  # None until the baseline poll; sockets that predate us are not charged

    def poll(self):
        current = read_sockets()
        now = time.time()
        minute = int(now) // 60 * 60

        if self.prev is not None:
            with lock:
                for key, (proc, ip, rx, tx) in current.items():
                    old = self.prev.get(key)
                    if old is None or old[0] != proc:
                        d_rx, d_tx = rx, tx          # connection opened since the last poll
                    else:
                        d_rx, d_tx = rx - old[2], tx - old[3]
                        if d_rx < 0 or d_tx < 0:     # 4-tuple reused by a new connection
                            d_rx, d_tx = rx, tx
                    if d_rx or d_tx:
                        host = ip_names.get(ip, ip)
                        entry = pending_usage[(minute, proc, host)]
                        entry[0] += d_rx
                        entry[1] += d_tx
        self.prev = current


# ---------------------------------------------------------------- link idle detection

_virtual_cache = {}


def is_virtual(name):
    v = _virtual_cache.get(name)
    if v is None:
        try:
            v = "/virtual/" in os.readlink(f"/sys/class/net/{name}")
        except OSError:
            v = True
        _virtual_cache[name] = v
    return v


def link_bytes():
    total = 0
    try:
        with open("/proc/net/dev") as f:
            for line in list(f)[2:]:
                name, _, rest = line.partition(":")
                name = name.strip()
                if not rest or is_virtual(name):
                    continue
                fields = rest.split()
                total += int(fields[0]) + int(fields[8])
    except (OSError, ValueError, IndexError):
        return None
    return total


# ---------------------------------------------------------------- storage

def open_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    return db


def flush(db):
    with lock:
        usage = dict(pending_usage)
        dns = dict(pending_dns)
        pending_usage.clear()
        pending_dns.clear()

    if not usage and not dns:
        return

    try:
        db.execute("BEGIN")
        for (minute, proc, host), (rx, tx) in usage.items():
            for table, ts in (("usage_minute", minute), ("usage_hour", minute // 3600 * 3600)):
                db.execute(
                    f"INSERT INTO {table} (ts, proc, host, rx, tx) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(ts, proc, host) DO UPDATE SET rx = rx + excluded.rx, tx = tx + excluded.tx",
                    (ts, proc, host, rx, tx),
                )
        for (hour, name), (queries, failures) in dns.items():
            db.execute(
                "INSERT INTO dns_hour (ts, name, queries, failures) VALUES (?,?,?,?) "
                "ON CONFLICT(ts, name) DO UPDATE SET queries = queries + excluded.queries, "
                "failures = failures + excluded.failures",
                (hour, name, queries, failures),
            )
        db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_flush', ?)", (str(int(time.time())),))
        db.execute("COMMIT")
    except sqlite3.Error as e:
        log(f"flush failed: {e}")
        try:
            db.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        # Put the data back so it is retried on the next flush.
        with lock:
            for k, (a, b) in usage.items():
                pending_usage[k][0] += a
                pending_usage[k][1] += b
            for k, (a, b) in dns.items():
                pending_dns[k][0] += a
                pending_dns[k][1] += b


def prune(db):
    now = int(time.time())
    try:
        db.execute("DELETE FROM usage_minute WHERE ts < ?", (now - MINUTE_RETENTION,))
        db.execute("DELETE FROM usage_hour WHERE ts < ?", (now - HOUR_RETENTION,))
        db.execute("DELETE FROM dns_hour WHERE ts < ?", (now - HOUR_RETENTION,))
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error as e:
        log(f"prune failed: {e}")


def main():
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    db = open_db()
    load_cache_dump()
    threading.Thread(target=dns_monitor, daemon=True).start()

    sampler = Sampler()
    sampler.poll()  # baseline
    last_link = link_bytes()
    last_poll = last_flush = last_cache = last_prune = time.monotonic()
    prune(db)

    while not stop.wait(POLL_SECONDS):
        now = time.monotonic()

        link = link_bytes()
        idle = (
            link is not None and last_link is not None
            and link - last_link < IDLE_BYTES
            and now - last_poll < IDLE_FORCE_SECONDS
        )
        if not idle:
            sampler.poll()
            last_poll = now
            last_link = link
        # On idle the link counter baseline is deliberately kept so slow trickles add up.

        if now - last_flush >= FLUSH_SECONDS:
            flush(db)
            last_flush = now
        if now - last_cache >= CACHE_REFRESH_SECONDS:
            load_cache_dump()
            last_cache = now
        if now - last_prune >= 6 * 3600:
            prune(db)
            last_prune = now

    flush(db)
    db.close()


if __name__ == "__main__":
    main()
