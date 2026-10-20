#!/usr/bin/env python3
"""Summarize compositor session metrics written by collect-session-metrics.sh.

    python3 summarize-metrics.py metrics/*.csv           # one table per capture
    python3 summarize-metrics.py --json metrics/*.csv    # machine-readable
    python3 summarize-metrics.py --process gala metrics/*.csv

The capture CSVs carry their run metadata in leading '#' comments (session,
workload, display mode, duration, interval). This tool only reduces those rows to
per-process statistics; it does not compare captures. Samples taken under
different workloads, session ages, display modes or scales are not comparable,
and no win or regression can be read off a single capture.

CPU values are percent of one core (one core = 100%). 'NA' rows — a process that
appeared after sampling began, which can indicate a restart — are excluded from
the statistics and reported separately. Battery flow is only meaningful on
battery; on mains it is reported as captured, without interpretation.
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
    """Return (metadata dict, rows) for one collect-session-metrics.sh CSV."""
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


def summarize(rows):
    """Per-process statistics for one capture. Returns a list of dicts."""
    by_process = {}
    for row in rows:
        by_process.setdefault(row["process"], []).append(row)
    summary = []
    for process in sorted(by_process):
        samples = by_process[process]
        cpu = [v for v in (numeric(r[CPU]) for r in samples) if v is not None]
        rss = [v for v in (numeric(r[RSS]) for r in samples) if v is not None]
        entry = {
            "process": process,
            "pids": sorted({r["pid"] for r in samples}),
            "samples": len(samples),
            "cpu_samples": len(cpu),
            "cpu_na": len(samples) - len(cpu),
        }
        for name, values in (("cpu", cpu), ("rss", rss)):
            if values:
                entry[f"{name}_mean"] = round(statistics.fmean(values), 2)
                entry[f"{name}_median"] = round(statistics.median(values), 2)
                entry[f"{name}_min"] = round(min(values), 2)
                entry[f"{name}_max"] = round(max(values), 2)
            else:
                entry[f"{name}_mean"] = entry[f"{name}_median"] = None
                entry[f"{name}_min"] = entry[f"{name}_max"] = None
        summary.append(entry)
    return summary


def capture_summary(path):
    metadata, rows = read_capture(path)
    return {
        "file": str(path),
        "metadata": metadata,
        "processes": summarize(rows),
    }


def render_text(summary):
    meta = summary["metadata"]
    print(f"== {summary['file']}")
    print("   session={session} workload={workload} display_mode={display_mode} "
          "duration_s={duration_s} interval_s={interval_s} started_utc={started_utc}".format(
              session=meta.get("session", "?"), workload=meta.get("workload", "?"),
              display_mode=meta.get("display_mode", "?"), duration_s=meta.get("duration_s", "?"),
              interval_s=meta.get("interval_s", "?"), started_utc=meta.get("started_utc", "?")))
    print(f"   {'process':<18} {'n':>3} {'cpu mean':>9} {'cpu median':>11} {'cpu min':>8} {'cpu max':>8} "
          f"{'rss median KiB':>15}")
    for p in summary["processes"]:
        print(f"   {p['process']:<18} {p['samples']:>3} {p['cpu_mean']:>9} {p['cpu_median']:>11} "
              f"{p['cpu_min']:>8} {p['cpu_max']:>8} {p['rss_median']:>15}")
        if p["cpu_na"]:
            print(f"   {'':<18} ({p['cpu_na']} sample(s) excluded as NA)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("captures", nargs="+", help="CSV files from collect-session-metrics.sh")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a text table")
    ap.add_argument("--process", help="only report processes whose name contains this substring")
    args = ap.parse_args()

    summaries = []
    for capture in args.captures:
        summary = capture_summary(capture)
        if args.process:
            summary["processes"] = [p for p in summary["processes"] if args.process in p["process"]]
            if not summary["processes"]:
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
