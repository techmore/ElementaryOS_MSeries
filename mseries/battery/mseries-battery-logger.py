#!/usr/bin/python3 -I
"""Battery history logger: samples power, CPU and top processes every few seconds into SQLite.

Runs as a user service (mseries-battery-logger.service). `--once` takes two samples a second apart and
prints the second, for checks. Never changes any setting; it only reads sysfs and procfs.
"""
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import battery_core as core  # noqa: E402


def main(argv):
    interval = core.SAMPLE_SECONDS
    sampler = core.Sampler()
    if not sampler.battery:
        print("No laptop battery found; nothing to log.", file=sys.stderr)
        return 0
    if "--once" in argv:
        sampler.sample()
        time.sleep(1)
        print(sampler.sample())
        return 0

    conn = core.connect()
    detector = core.EventDetector()
    stop = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.append(1))
    sampler.sample()                      # primes the CPU and per-process counters
    last_prune = 0
    while not stop:
        time.sleep(interval)
        if stop:
            break
        try:
            row = sampler.sample()
            core.store(conn, row)
            detector.feed(conn, row)
            conn.commit()
            if row["ts"] - last_prune > 86400:
                core.prune(conn)
                last_prune = row["ts"]
        except Exception as error:  # keep logging through a transient sysfs hiccup
            print("sample failed: %s" % error, file=sys.stderr)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
