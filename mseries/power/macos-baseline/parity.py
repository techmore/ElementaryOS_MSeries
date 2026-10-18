#!/usr/bin/env python3
"""Fill parity.json from a macOS run and from Linux measurements, then score each item.

    python3 parity.py --mac results/macos-<stamp>/summary.json      # macOS column
    python3 parity.py --linux-run results/linux-<stamp>/summary.json  # Linux column, from linux_profile.py
    python3 parity.py --linux W1=8.9 --source W1="powerlab ab.py 2026-10-18" --kind W1=measured
    python3 parity.py --check A2 --note A2="PCM suspends after 30 s"  # mark a yes/no item as passed
    python3 parity.py                                               # just re-score and rewrite PARITY.md

Expressions: s:<scen>.<metric> median, d:<a>-<b> difference, p:<scen>:<proc>:<field> per process,
b:<field> cpu burst, i:<key> inventory, k:<number> fixed target, v:<scen>.<mpv property> playback stats.
Status per item: pass (within 10%), close (within 1.5x, tier 2), gap, awaiting-mac, awaiting-linux, info.
"""
import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "parity.json"
MD = HERE / "PARITY.md"


def dig(obj, dotted):
    for part in dotted.split("."):
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            return None
    return obj


def metric(summary, scen_metric):
    scen, m = scen_metric.split(".", 1)
    return dig(summary, f"scenarios.{scen}.metrics.{m}.median")


def resolve(summary, expr):
    if not expr or not summary:
        return None
    kind, rest = expr.split(":", 1)
    if kind == "s":
        return metric(summary, rest)
    if kind == "d":
        a, b = rest.split("-", 1)
        va, vb = metric(summary, a), metric(summary, b)
        return round(va - vb, 3) if va is not None and vb is not None else None
    if kind == "p":
        scen, proc, field = rest.split(":")
        sc = dig(summary, f"scenarios.{scen}")
        if not sc:
            return None
        for row in sc.get("top_processes", []):
            if row["process"].lower().startswith(proc.lower()):
                return row.get(field)
        return None                               # omitted from a truncated top list is unmeasured
    if kind == "b":
        return dig(summary, f"scenarios.cpu_burst.burst.{rest}")
    if kind == "i":
        return dig(summary, f"inventory.{rest}")
    if kind == "k":                               # a fixed target, e.g. k:0 dropped frames
        return float(rest)
    if kind == "v":                               # mpv playback stats (Linux): v:<scenario>.<property>
        scen, prop = rest.split(".", 1)
        val = dig(summary, f"scenarios.{scen}.playback")
        if not val:
            return None
        val = val.get(prop)
        if prop == "hwdec-current":               # 1 when a hardware decoder is really in use
            return None if val is None else (0.0 if val in ("", "no") else 1.0)
        return val
    return None


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def score(item):
    item.pop("ratio", None)
    if item.get("checked"):
        return "pass"
    mac, lin, d = item.get("mac_value"), item["linux"].get("value"), item["dir"]
    if d == "info":
        return "info"
    if not numeric(mac):
        return "awaiting-mac"
    if not numeric(lin):
        return "awaiting-linux"
    if d == "lower":
        ratio = lin / mac if mac > 0 else (1.0 if lin <= 0 else float("inf"))
    else:
        ratio = mac / lin if lin > 0 else float("inf")
    item["ratio"] = round(ratio, 2) if ratio != float("inf") else None
    if ratio <= 1.10:
        return "pass"
    if ratio <= 1.5:
        return "close"
    return "gap"


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def fmt(v, unit=""):
    if v is None:
        return "–"
    if isinstance(v, float):
        v = f"{v:,.2f}" if abs(v) < 100 else f"{v:,.0f}"
    elif isinstance(v, (dict, list)):
        v = json.dumps(v)[:60]
    return f"{v} {unit}".strip()


def write_md(doc):
    icon = {"pass": "✅", "close": "🟡", "gap": "🔴", "awaiting-mac": "⏳ mac", "awaiting-linux": "⏳ linux", "info": "ℹ️"}
    lines = [f"# {doc['title']}", "", f"Updated {doc['updated']}. macOS run: `{doc.get('mac_run') or 'not yet'}`.", "",
             f"Pass = {doc['rules']['pass']}. Close = {doc['rules']['close']}. {doc['rules']['conditions']}.", ""]
    totals = {}
    for c in doc["categories"]:
        for it in c["items"]:
            totals[it["status"]] = totals.get(it["status"], 0) + 1
    lines.append("Scoreboard: " + ", ".join(f"{icon.get(k, k)} {v}" for k, v in sorted(totals.items())))
    for c in doc["categories"]:
        done = sum(1 for it in c["items"] if it["status"] == "pass")
        scored = sum(1 for it in c["items"] if it["status"] != "info")
        lines += ["", f"## {c['name']} ({done}/{scored} passed)", "", c["blurb"], "",
                  "| | ID | Item | macOS | Linux now | Status |", "|---|---|---|---|---|---|"]
        for it in c["items"]:
            box = "[x]" if it["status"] == "pass" else "[ ]"
            lin = it["linux"]
            lv = fmt(lin.get("value"), it["unit"]) if lin.get("value") is not None else ""
            ltxt = f"{lv} ({lin['kind']}) {lin.get('text', '')}".strip()
            lines.append(f"| {box} | {it['id']} | {it['name']} | {cell(fmt(it.get('mac_value'), it['unit']))} | "
                         f"{cell(ltxt)} | {icon.get(it['status'], it['status'])} |")
    MD.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mac", help="summary.json from macos_profile.py")
    ap.add_argument("--linux-run", help="summary.json from linux_profile.py (fills every item it can measure)")
    ap.add_argument("--linux", action="append", default=[], help="ID=value")
    ap.add_argument("--source", action="append", default=[], help="ID=where the Linux number came from")
    ap.add_argument("--kind", action="append", default=[], help="ID=measured|estimate")
    ap.add_argument("--check", action="append", default=[], help="ID to mark passed by hand (yes/no items)")
    ap.add_argument("--uncheck", action="append", default=[], help="ID to clear a manual pass")
    ap.add_argument("--note", action="append", default=[], help="ID=text replaces the Linux description")
    ap.add_argument("--date", help="date stamp for this update")
    args = ap.parse_args()

    doc = json.loads(DATA.read_text())
    summary = json.loads(Path(args.mac).read_text()) if args.mac else None
    if summary:
        doc["mac_run"] = str(Path(args.mac).parent.name)
        doc["mac_inventory"] = {k: summary["inventory"].get(k) for k in
                                ("macos", "model", "chip", "brightness", "on_battery", "process_count")}
    lsum = json.loads(Path(args.linux_run).read_text()) if args.linux_run else None
    if lsum:
        doc["linux_run"] = str(Path(args.linux_run).parent.name)
        doc["linux_inventory"] = {k: lsum["inventory"].get(k) for k in
                                  ("os", "kernel", "brightness", "on_battery", "power_profile", "system_power_source")}
    items = {it["id"]: it for c in doc["categories"] for it in c["items"]}
    def kv(pairs):
        result = {}
        for pair in pairs:
            key, sep, value = pair.partition("=")
            if not sep or key not in items:
                ap.error(f"expected known ID=value, got {pair!r}")
            result[key] = value
        return result
    lin, src, kind, note = kv(args.linux), kv(args.source), kv(args.kind), kv(args.note)
    for i, value in lin.items():
        try:
            value = float(value)
        except ValueError:
            ap.error(f"{i}: expected a finite number")
        if not numeric(value):
            ap.error(f"{i}: expected a finite number")
    if any(value not in ("measured", "estimate") for value in kind.values()):
        ap.error("--kind must be measured or estimate")
    for i in args.check + args.uncheck:
        if i not in items:
            ap.error(f"unknown item {i}")
        if i in args.check and (items[i].get("mac") is not None or items[i]["dir"] == "info"):
            ap.error(f"{i}: numeric/informational items cannot be passed by hand")
    for c in doc["categories"]:
        for it in c["items"]:
            i = it["id"]
            if summary:
                it["mac_value"] = resolve(summary, it.get("mac"))
            if lsum:
                expr = it.get("lx", it.get("mac"))
                v = resolve(lsum, expr) if expr else None
                if expr:
                    # A partial new run must not silently reuse an older run's measurements.
                    it.pop("checked", None)
                    it["linux"].update(value=None, kind="unmeasured",
                                       source=f"linux_profile.py {doc['linux_run']}",
                                       text="not measured in this run")
                if numeric(v):
                    old = it["linux"].get("text", "")
                    it["linux"].update(value=round(float(v), 3), kind="measured",
                                       source=f"linux_profile.py {doc['linux_run']}",
                                       text=f"linux_profile.py run (was: {old})" if old and "was:" not in old else old)
            if i in lin:
                it["linux"]["value"] = float(lin[i])
                it["linux"]["kind"] = kind.get(i, "measured")
            if i in src:
                it["linux"]["source"] = src[i]
            if i in note:
                it["linux"]["text"] = note[i]
            if i in args.check:
                it["checked"] = True
            if i in args.uncheck:
                it.pop("checked", None)
            it["status"] = score(it)
    if args.date:
        doc["updated"] = args.date
    DATA.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    write_md(doc)
    print(next(l for l in MD.read_text().splitlines() if l.startswith("Scoreboard")))


if __name__ == "__main__":
    main()
