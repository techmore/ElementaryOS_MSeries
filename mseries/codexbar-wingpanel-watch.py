#!/usr/bin/env python3
"""Read-only Wingpanel/launcher observations; never signal or restart the desktop.

Only process metrics and journal event identifiers/categories are persisted.
Raw journal text, core contents, account data and credentials are not stored.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import time

import codexbar_cache

STATE = "wingpanel-watch-v1"
PANEL_EXE = "/usr/bin/io.elementary.wingpanel"
MAX_EVENTS = 500


def processes() -> list[dict]:
    panels = []
    for path in pathlib.Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid != os.getuid() or (path / "comm").read_text().strip() != "io.elementary.w":
                continue
            executable = os.readlink(path / "exe").removesuffix(" (deleted)")
            if pathlib.Path(executable).name != "io.elementary.wingpanel":
                continue
            fields = (path / "stat").read_text().rsplit(") ", 1)[1].split()
            parent = pathlib.Path("/proc") / fields[1]
            status = dict(line.split(":", 1) for line in (path / "status").read_text().splitlines() if ":" in line)
            try:
                launcher = {"pid": int(fields[1]), "name": (parent / "comm").read_text().strip(),
                            "exe": os.readlink(parent / "exe").removesuffix(" (deleted)"), "alive": True}
            except OSError:
                launcher = {"pid": int(fields[1]), "alive": False}
            panels.append({"pid": int(path.name), "startTicks": int(fields[19]), "launcher": launcher,
                           "cpuTicks": int(fields[11]) + int(fields[12]),
                           "rssKiB": int(status["VmRSS"].split()[0]),
                           "fds": len(list((path / "fd").iterdir()))})
        except (OSError, ValueError, KeyError, IndexError):
            continue  # An exit racing the observation appears as an absence/PID transition.
    return sorted(panels, key=lambda item: item["pid"])


def journal(since: float, *, cores: bool, launchers: set[str]) -> list[dict]:
    command = ["journalctl", "-b", "--no-pager", "-o", "json", "-n", str(MAX_EVENTS),
               "--since", f"@{since:.6f}"]
    fields = "__CURSOR,__REALTIME_TIMESTAMP,PRIORITY,_PID,COREDUMP_EXE,COREDUMP_PID"
    command += ["--output-fields=" + fields + ("" if cores else ",MESSAGE")]
    if cores:
        for executable in sorted({PANEL_EXE} | launchers):
            if command[-1].startswith("COREDUMP_EXE="):
                command.append("+")
            command.append(f"COREDUMP_EXE={executable}")
    else:
        command += ["--user", "_COMM=io.elementary.w"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise RuntimeError(f"{'Core' if cores else 'Panel'} journal unavailable (status {result.returncode})")
    if len(result.stdout) > 2 * 1024 * 1024:
        raise RuntimeError("Journal response exceeded its size bound")
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if len(rows) >= MAX_EVENTS:
        raise RuntimeError("Journal observation exceeded its event bound; inspect the full interval manually")
    return rows


def identity(panels: list[dict]) -> list[tuple[int, int]]:
    return [(item["pid"], item["startTicks"]) for item in panels]


def assess(previous: dict, current: dict, rows: list[dict], errors: list[str]) -> tuple[dict, dict]:
    same_boot = previous.get("bootId") == current["bootId"]
    baseline = not same_boot
    seen = list(previous.get("seen", [])) if same_boot else []
    events = []
    launchers = {p["launcher"].get("exe") for p in current["panels"] + previous.get("panels", [])}
    for row in rows:
        key = hashlib.sha256(str(row.get("__CURSOR", "")).encode()).hexdigest()
        if key in seen:
            continue
        seen.append(key)
        message = str(row.get("MESSAGE", "")).lower()
        category = None
        if row.get("COREDUMP_EXE") == PANEL_EXE:
            category = "panel_coredump"
        elif row.get("COREDUMP_EXE") and row["COREDUMP_EXE"] in launchers:
            category = "launcher_coredump"
        elif "gtk_flow_box_set_max_children_per_line" in message:
            continue  # Known, separately documented startup warning; not evidence of a crash.
        elif "still has children left" in message or "gtk_accessible" in message or "segfault" in message:
            category = "popup_or_crash_warning"
        elif int(row.get("PRIORITY", 7)) <= 3:
            category = "panel_error"
        if category:
            events.append({"category": category, "pid": row.get("COREDUMP_PID", row.get("_PID")),
                           "timeUs": row.get("__REALTIME_TIMESTAMP")})
    panels = current["panels"]
    old_panels = previous.get("panels", []) if same_boot else []
    if not panels and (baseline or old_panels):
        events.append({"category": "panel_missing"})
    elif panels and same_boot and identity(panels) != identity(old_panels):
        # No exit status is available from a PID change alone. Never label it a crash.
        events.append({"category": "panel_restarted_unclassified" if old_panels else "panel_recovered"})
    if len(panels) > 1 and (baseline or len(old_panels) <= 1):
        events.append({"category": "multiple_panels", "count": len(panels)})
    if any(not p["launcher"]["alive"] for p in panels) and (baseline or all(p["launcher"]["alive"] for p in old_panels)):
        events.append({"category": "launcher_missing"})
    elapsed = current["monotonic"] - previous.get("monotonic", current["monotonic"])
    prior = {(p["pid"], p["startTicks"]): p for p in old_panels}
    for panel in panels:
        old = prior.get((panel["pid"], panel["startTicks"]))
        if old and elapsed > 0:
            panel["cpuPercent"] = round(max(0, panel["cpuTicks"] - old["cpuTicks"]) /
                                        os.sysconf("SC_CLK_TCK") / elapsed * 100, 3)
    newly_unavailable = [error for error in errors if error not in previous.get("errors", [])]
    events += [{"category": "observation_unavailable", "detail": error} for error in newly_unavailable]
    state = {**current, "seen": seen[-1000:], "errors": errors}
    report = {"baseline": baseline, "panels": panels, "events": events, "errors": errors,
              "actionable": bool(events), "healthy": len(panels) == 1 and all(p["launcher"]["alive"] for p in panels)
              and not errors and not any(event["category"] in (
                  "panel_coredump", "launcher_coredump", "popup_or_crash_warning", "panel_error") for event in events)}
    return state, report


def check() -> None:
    previous = codexbar_cache.load(STATE)
    current = {"bootId": pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
               "checkedAt": time.time(), "monotonic": time.monotonic(), "panels": processes()}
    since = previous.get("checkedAt", current["checkedAt"]) if previous.get("bootId") == current["bootId"] else current["checkedAt"]
    rows, errors = [], []
    launchers = {p["launcher"]["exe"] for p in current["panels"] + previous.get("panels", []) if p["launcher"].get("exe")}
    for cores in (False, True):
        try:
            rows.extend(journal(max(0, since - 1), cores=cores, launchers=launchers))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(str(error))
    # Retry an unavailable journal interval on the next check instead of silently advancing past it.
    state, report = assess(previous, current, rows, errors)
    if errors:
        state["checkedAt"] = since
    codexbar_cache.store(STATE, state)
    if codexbar_cache.load(STATE).get("monotonic") != current["monotonic"]:
        report["errors"].append("Could not persist the monitor checkpoint")
        report.update(actionable=True, healthy=False)
    print(json.dumps(report, separators=(",", ":")))


def main() -> None:
    try:
        # A manual check and the heartbeat must not race their event checkpoints.
        with codexbar_cache.locked(codexbar_cache.cache_dir() / f"{STATE}.json", timeout=0):
            check()
    except TimeoutError:
        print(json.dumps({"skipped": "Another observation is in progress", "actionable": False}))
    except OSError:
        print(json.dumps({"errors": ["Monitor state is unavailable"], "healthy": False, "actionable": True}))


if __name__ == "__main__":
    main()
