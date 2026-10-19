#!/usr/bin/env python3
"""Summarize screen-share cost captures from collect-share-cost.sh.

    python3 summarize-share-cost.py metrics/*.csv           # one table per capture
    python3 summarize-share-cost.py --json metrics/*.csv    # machine-readable
    python3 summarize-share-cost.py --process metrics/*.csv # per-process detail

Also reads the session captures from collect-session-metrics.sh: those have no
`role` column, so grouping falls back to the process name.

CPU is percent of one core. Within a role (for example the owner's browser,
which runs many processes), the processes are summed per sample and the
statistics are taken across samples, because that is the cost the desktop
actually feels. 'NA' samples — a process that appeared after sampling began —
are excluded and counted. The tool only reduces captures; two captures taken
under different workloads, viewer counts, display modes or power states are
not comparable, and no result can be read off a single capture.
"""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

CPU = "cpu_percent_one_core"
RSS = "ram_kib"


def read_capture(path):
    """Return (metadata dict, rows) for one collect-share-cost.sh CSV."""
    metadata = {}
    rows = []
    for line in Path(path).read_text().splitlines():
        if line.startswith("#"):
            for field in line.lstrip("#").strip().split():
                key, _, value = field.partition("=")
                if _:
                    metadata[key] = value
            continue
        if not line.strip():
            continue
        rows.append(line)
    if not rows:
        raise SystemExit(f"{path}: no samples found")
    reader = csv.DictReader(rows)
    required = {"session", "workload", "display_mode", "pid", "process", CPU, RSS}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"{path}: missing columns {sorted(missing)}")
    return metadata, list(reader)


def numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def stats(values):
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def role_samples(rows, role):
    """Sum this role's processes per sample timestamp. Returns (cpu list, rss list, na count).

    A process that appeared mid-run has no valid CPU delta (NA) but its resident
    size at that sample is still real, so RSS is summed regardless.
    """
    per_sample = {}
    na = 0
    for row in rows:
        if row.get("role") != role:
            continue
        sample = per_sample.setdefault(row["utc"], {"cpu": 0.0, "rss": 0, "any": False})
        rss = numeric(row[RSS])
        if rss is not None:
            sample["rss"] += int(rss)
            sample["any"] = True
        cpu = numeric(row[CPU])
        if cpu is None:
            na += 1
            continue
        sample["cpu"] += cpu
        sample["any"] = True
    cpu = [s["cpu"] for s in per_sample.values() if s["any"]]
    rss = [s["rss"] for s in per_sample.values() if s["any"]]
    return cpu, rss, na


def process_samples(rows, process):
    cpu = [v for v in (numeric(r[CPU]) for r in rows if r["process"] == process) if v is not None]
    rss = [numeric(r[RSS]) for r in rows if r["process"] == process]
    rss = [int(v) for v in rss if v is not None]
    na = sum(1 for r in rows if r["process"] == process and numeric(r[CPU]) is None)
    return cpu, rss, na


def observed_viewers(rows):
    seen = []
    for row in rows:
        value = row.get("share_viewers")
        if value and value != "NA" and value not in seen:
            seen.append(value)
    return seen


def capture_summary(path, per_process=False):
    metadata, rows = read_capture(path)
    has_role = any(row.get("role") for row in rows)
    processes = []
    if has_role:
        for role in sorted({row["role"] for row in rows if row.get("role")}):
            cpu, rss, na = role_samples(rows, role)
            entry = {"group": role, "kind": "role", "cpu": stats(cpu), "rss": stats(rss), "cpu_na": na,
                     "processes": sorted({r["process"] for r in rows if r.get("role") == role})}
            processes.append(entry)
            if per_process:
                for name in entry["processes"]:
                    pcpu, prss, pna = process_samples(rows, name)
                    processes.append({"group": f"{role}/{name}", "kind": "process",
                                      "cpu": stats(pcpu), "rss": stats(prss), "cpu_na": pna})
    else:
        for name in sorted({row["process"] for row in rows}):
            cpu, rss, na = process_samples(rows, name)
            processes.append({"group": name, "kind": "process", "cpu": stats(cpu),
                              "rss": stats(rss), "cpu_na": na})
    return {
        "file": str(path),
        "metadata": metadata,
        "viewers_observed": observed_viewers(rows),
        "groups": processes,
    }


def render_text(summary):
    meta = summary["metadata"]
    print(f"== {summary['file']}")
    print("   session={session} workload={workload} display_mode={display_mode} "
          "duration_s={duration_s} interval_s={interval_s} started_utc={started_utc} "
          "viewers_expected={viewers_expected}".format(
              session=meta.get("session", "?"), workload=meta.get("workload", "?"),
              display_mode=meta.get("display_mode", "?"), duration_s=meta.get("duration_s", "?"),
              interval_s=meta.get("interval_s", "?"), started_utc=meta.get("started_utc", "?"),
              viewers_expected=meta.get("viewers_expected", "?")))
    observed = summary["viewers_observed"]
    print(f"   viewers observed in capture: {', '.join(observed) if observed else 'NA'}")
    print(f"   {'group':<24} {'n':>3} {'cpu mean':>9} {'cpu median':>11} {'cpu min':>8} {'cpu max':>8} {'rss median KiB':>15}")
    for g in summary["groups"]:
        cpu, rss = g["cpu"], g["rss"]
        print(f"   {g['group']:<24} {cpu['n']:>3} {cpu['mean']:>9} {cpu['median']:>11} "
              f"{cpu['min']:>8} {cpu['max']:>8} {rss['median'] if rss['median'] is not None else 'NA':>15}")
        if g["cpu_na"]:
            print(f"   {'':<24} ({g['cpu_na']} sample(s) excluded as NA)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("captures", nargs="+", help="CSV files from collect-share-cost.sh or collect-session-metrics.sh")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a text table")
    ap.add_argument("--process", action="store_true", help="also show per-process rows inside each role")
    ap.add_argument("--group", help="only report groups whose name contains this substring")
    args = ap.parse_args()

    summaries = []
    for capture in args.captures:
        summary = capture_summary(capture, per_process=args.process)
        if args.group:
            summary["groups"] = [g for g in summary["groups"] if args.group in g["group"]]
            if not summary["groups"]:
                continue
        summaries.append(summary)

    if args.json:
        print(json.dumps(summaries, indent=2))
    else:
        for summary in summaries:
            render_text(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
