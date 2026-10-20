#!/usr/bin/env python3
"""Compare matched screen-share cost captures and apply the README's rule.

    python3 compare-share-cost.py viewers-*.csv
    python3 compare-share-cost.py --json viewers-*.csv

The protocol in README.md requires at least two captures per viewer count, taken
under the same workload, display mode, interval and duration (the recommended
order is 1 -> 3 -> 1 -> 3). This tool refuses to compare captures whose recorded
conditions differ, flags a capture whose observed viewer count does not match
its expected count, and reports a difference only when it exceeds the spread
between repeated arms of the same condition. With fewer than two captures on
either side it says "insufficient repeats" instead of guessing.

CPU is percent of one core (the per-role sum per sample, reduced to the arm
median). System power is whole-system watts from the SMC rail. The condition
median is the median of the arm medians; the threshold is the larger of the two
within-condition ranges.
"""
import argparse
import importlib.util
import json
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent


def load_summarizer():
    spec = importlib.util.spec_from_file_location(
        "summarize_share_cost", HERE / "summarize-share-cost.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


summarizer = load_summarizer()

PROTOCOL_KEYS = ("workload", "display_mode", "duration_s", "interval_s", "browser")


def viewer_count(summary):
    try:
        return int(summary["metadata"].get("viewers_expected", ""))
    except (TypeError, ValueError):
        return None


def role_cpu_median(summary, role):
    for group in summary["groups"]:
        if group["group"] == role:
            return group["cpu"]["median"]
    return None


def power_median(summary):
    return summary["power"]["median"]


def protocol_errors(summaries):
    """Return a list of reasons the captures are not a matched set."""
    errors = []
    for key in PROTOCOL_KEYS:
        values = sorted({s["metadata"].get(key, "") for s in summaries if s["metadata"].get(key)})
        if len(values) > 1:
            errors.append(f"{key} differs across captures: {', '.join(values)}")
    for summary in summaries:
        expected = viewer_count(summary)
        if expected is None:
            errors.append(f"{summary['file']}: no viewers_expected in the capture header")
            continue
        observed = summary["viewers_observed"]
        if not observed:
            errors.append(f"{summary['file']}: no viewer count was recorded")
        elif observed != [str(expected)]:
            errors.append(
                f"{summary['file']}: expected {expected} viewer(s), observed {', '.join(observed)}")
        ac = summary["ac_online_observed"]
        if ac and "1" not in ac:
            errors.append(f"{summary['file']}: AC power was not on (ac_online={','.join(ac)})")
    return errors


def spread(values):
    if len(values) < 2:
        return None
    return round(max(values) - min(values), 2)


def compare_metric(captures_low, captures_high, extract):
    arms_low = [extract(c) for c in captures_low]
    arms_high = [extract(c) for c in captures_high]
    valid_low = [v for v in arms_low if v is not None]
    valid_high = [v for v in arms_high if v is not None]
    result = {
        "arms_low": arms_low,
        "arms_high": arms_high,
    }
    if not valid_low or not valid_high:
        result["verdict"] = "missing data"
        return result
    median_low = round(statistics.median(valid_low), 2)
    median_high = round(statistics.median(valid_high), 2)
    spread_low = spread(valid_low)
    spread_high = spread(valid_high)
    result.update({
        "median_low": median_low,
        "median_high": median_high,
        "delta": round(median_high - median_low, 2),
        "spread_low": spread_low,
        "spread_high": spread_high,
    })
    if spread_low is None or spread_high is None:
        result["threshold"] = None
        result["verdict"] = "insufficient repeats"
    else:
        threshold = max(spread_low, spread_high)
        result["threshold"] = threshold
        result["verdict"] = ("difference exceeds spread"
                             if abs(result["delta"]) > threshold
                             else "no measured difference")
    return result


def comparison(summaries, low, high):
    by_count = {low: [], high: []}
    for summary in summaries:
        by_count[viewer_count(summary)].append(summary)
    roles = sorted({g["group"] for s in summaries for g in s["groups"]})
    return {
        "conditions": {
            str(count): {
                "captures": len(by_count[count]),
                "files": [s["file"] for s in by_count[count]],
                "viewers_observed": sorted({v for s in by_count[count]
                                            for v in s["viewers_observed"]}),
            } for count in (low, high)},
        "protocol": {key: summaries[0]["metadata"].get(key, "") for key in PROTOCOL_KEYS},
        "ac_online": sorted({v for s in summaries for v in s["ac_online_observed"]}),
        "power": compare_metric(by_count[low], by_count[high], power_median),
        "roles": {role: compare_metric(by_count[low], by_count[high],
                                       lambda s, r=role: role_cpu_median(s, r))
                  for role in roles},
    }


def render_text(result, low, high):
    print("== matched-pair comparison")
    for count in (low, high):
        condition = result["conditions"][str(count)]
        print(f"   {count} viewer(s): {condition['captures']} capture(s), "
              f"observed {', '.join(condition['viewers_observed']) or 'NA'} "
              f"({', '.join(pathlib.Path(f).name for f in condition['files'])})")
    protocol = result["protocol"]
    print("   protocol: workload={workload} display_mode={display_mode} duration_s={duration_s} "
          "interval_s={interval_s} browser={browser}".format(**protocol))
    if result["ac_online"]:
        print(f"   ac_online observed: {', '.join(result['ac_online'])}")
    print(f"   {'metric':<16} {f'{low}v median':>11} {f'{high}v median':>11} "
          f"{'delta':>9} {'spread low':>10} {'spread high':>11} {'threshold':>9} verdict")
    rows = [(f"{role} cpu", metrics) for role, metrics in result["roles"].items()]
    rows.append(("system power W", result["power"]))
    for name, metrics in rows:
        values = lambda key: "NA" if metrics.get(key) is None else metrics.get(key)
        print(f"   {name:<16} {values('median_low'):>11} {values('median_high'):>11} "
              f"{values('delta'):>9} {values('spread_low'):>10} {values('spread_high'):>11} "
              f"{values('threshold'):>9} {metrics['verdict']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("captures", nargs="+", help="CSV files from collect-share-cost.sh")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a text table")
    args = ap.parse_args()

    summaries = [summarizer.capture_summary(path) for path in args.captures]
    errors = protocol_errors(summaries)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        print("error: captures do not form a matched pair; collect them under the README protocol",
              file=sys.stderr)
        return 2
    counts = sorted({viewer_count(summary) for summary in summaries})
    if len(counts) != 2:
        print(f"error: expected exactly two viewer counts, found {counts or 'none'}", file=sys.stderr)
        return 2
    result = comparison(summaries, counts[0], counts[1])
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        render_text(result, counts[0], counts[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
