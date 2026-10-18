#!/usr/bin/env python3
"""Generate deterministic snapshot + sessions fixtures for the render probe from fixtures/live.json."""
import copy, datetime as dt, json, pathlib

here = pathlib.Path(__file__).parent / "fixtures"
live = json.loads((here / "live.json").read_text())
NOW = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")


def window(key, label, minutes, remaining, reset_in_min, pace=""):
    return {"displaySuffix": "left", "displayValue": remaining, "key": key, "label": label, "minutes": minutes,
            "pace": pace, "paceDelta": 0, "paceExpected": 0, "remaining": remaining,
            "resetText": "Resets in %dh %dm" % divmod(reset_in_min, 60) if reset_in_min < 1440
            else "Resets in %dd %dh" % (reset_in_min // 1440, reset_in_min % 1440 // 60),
            "resetsAt": iso(NOW + dt.timedelta(minutes=reset_in_min)), "warning": remaining <= 20}


def entry(provider, windows, error="", plan="pro", age_min=1):
    return {"credits": None, "error": error, "extraUsage": None, "plan": plan, "provider": provider,
            "resetCredits": None, "status": "All Systems Operational" if windows else "", "statusLevel": "none",
            "updatedAt": iso(NOW - dt.timedelta(minutes=age_min)), "windows": windows}


def snap(entries, **extra):
    s = copy.deepcopy(live)
    s.update({"entries": entries, "busy": False, "stale": False, "error": "", "updated": "just now", **extra})
    return s


codex_ok = entry("codex", [window("primary", "5 hour", 300, 72, 190, "Expected 40% used | On pace"),
                           window("secondary", "7 day", 10080, 64, 5000, "On pace")])
claude_ok = entry("claude", [window("primary", "5 hour", 300, 55, 120, "On pace"),
                             window("secondary", "7 day", 10080, 81, 8000, "On pace")], plan="max")
go_err = entry("opencodego", [], error="Usage unavailable. Check this provider’s CodexBar login/configuration.", plan="", age_min=0)
go_err["updatedAt"] = ""

scenarios = {
    "healthy": snap([codex_ok, claude_ok]),
    "live": snap(live["entries"]),
    "depleting": snap([entry("codex", [window("primary", "5 hour", 300, 18, 240, "56% in deficit | Runs out in 1h 10m"),
                                       window("secondary", "7 day", 10080, 60, 6000, "On pace")]), claude_ok]),
    "exhausted": snap([entry("codex", [window("primary", "5 hour", 300, 0, 75, "Exhausted"),
                                       window("secondary", "7 day", 10080, 35, 6000, "On pace")]), claude_ok]),
    "provider-error": snap([codex_ok, go_err]),
    "connected": snap([codex_ok, entry("opencodego", [window("primary", "5 hour", 300, 83, 240),
        window("secondary", "7 day", 10080, 68, 8000), window("tertiary", "30 day", 43200, 91, 30000)], plan="go")]),
    "stale": snap([codex_ok, claude_ok], stale=True, error="Network unreachable"),
    "empty": snap([]),
}
busy = snap([]); busy["busy"] = True
scenarios["busy"] = busy
for name, value in scenarios.items():
    (here / f"{name}.json").write_text(json.dumps(value, indent=1))

sessions = {"updatedAt": iso(NOW), "sessions": [
    {"id": "codex", "name": "ChatGPT · Codex", "state": "ok", "detail": "Signed in · account quota comes from CodexBar."},
    {"id": "claude", "name": "Claude Code", "state": "ok", "detail": "Signed in",
     "periods": [{"label": "5 hours", "requests": 42, "tokens": 1850000, "costUSD": 0},
                 {"label": "7 days", "requests": 610, "tokens": 31200000, "costUSD": 0}],
     "note": "Local activity from Claude Code transcripts · not account quota (tokens exclude cache reads)"},
    {"id": "opencode", "name": "OpenCode", "state": "warn", "detail": "OpenCode history uses an unsupported schema."}]}
(here / "sessions.json").write_text(json.dumps(sessions))
print("fixtures:", ", ".join(sorted(scenarios)))

# Complete saved-account fixtures exercise short-window exhaustion beside healthy totals.
accounts = {
    "codex": {"accounts": [
        {"email": "me@codex.example", "id": "a", "active": True, "plan": "pro", "windows": []},
        {"email": "work@codex.example", "id": "b", "active": False, "plan": "plus", "windows": [
            window("primary", "5 hour", 300, 5, 65), window("secondary", "7 day", 10080, 62, 5000)]}]},
    "claude": {"available": True, "activeEmail": "me@claude.example", "activePlan": "pro", "desktop": {
        "installed": True, "email": "me@claude.example", "differs": False}, "desktopNote": "", "accounts": [
        {"number": 1, "email": "me@claude.example", "plan": "pro", "active": True, "desktopReady": True, "desktopActive": True,
         "windows": [window("primary", "5 hour", 300, 80, 130), window("secondary", "7 day", 10080, 55, 5000)]},
        {"number": 2, "email": "work@claude.example", "plan": "max", "active": False, "desktopReady": True, "desktopActive": False,
         "windows": [window("primary", "5 hour", 300, 0, 190), window("secondary", "7 day", 10080, 72, 8000)]}]},
    "opencode": {"accounts": [
        {"email": "me@opencode.example", "id": "a", "active": True, "plan": "Go Plus", "planSource": "console", "windows": []},
        {"email": "work@opencode.example", "workspace": "Work", "id": "b", "active": False, "plan": "Go", "planSource": "console", "windows": [
            window("primary", "5 hour", 300, 0, 220), window("secondary", "7 day", 10080, 51, 6000),
            window("tertiary", "30 day", 43200, 63, 30000)]}]},
}
for provider, value in accounts.items():
    (here / f"accounts-{provider}.json").write_text(json.dumps(value))

(here / "hints.json").write_text(json.dumps(scenarios["connected"], indent=1))
hint_accounts = copy.deepcopy(accounts)
hint_accounts["claude"]["accounts"][1]["windows"] = [
    window("primary", "5 hour", 300, 95, 190), window("secondary", "7 day", 10080, 90, 8000)]
hint_accounts["codex"]["accounts"][1]["windows"][1] = window("secondary", "7 day", 10080, 62, 45)
for provider, value in hint_accounts.items():
    (here / f"accounts-{provider}-hints.json").write_text(json.dumps(value))
