#!/usr/bin/env python3
"""Generate deterministic snapshot + sessions fixtures for the render probe from fixtures/live.json."""
import copy, datetime as dt, json, pathlib
import os
import tempfile

here = pathlib.Path(__file__).parent / "fixtures"
live = json.loads((here / "live.json").read_text())
NOW = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_fixture(path, value, **options):
    # Native tests generate/read these files concurrently. Never expose truncated JSON.
    descriptor, temporary = tempfile.mkstemp(dir=here, prefix=".fixture-")
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, **options)
        os.replace(temporary, path)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)


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
# Grok as upstream v0.78.0 exports it: one weekly credits window, the reported SuperGrok tier, and
# informational detail sections (product shares of the same pool, usage-limit reset coupons).
grok_ok = entry("grok", [window("primary", "7 day", 10080, 76, 4000, "On pace")], plan="SuperGrok")
grok_ok["details"] = [
    {"title": "Usage breakdown", "rows": [{"label": "Grok Build", "value": "18%", "secondaryValue": ""},
                                          {"label": "Grok Chat", "value": "6%", "secondaryValue": ""}], "chart": None},
    {"title": "Limit Reset Credits", "rows": [{"label": "Available", "value": "1 available", "secondaryValue": ""}],
     "chart": None},
    {"title": "Malformed", "rows": ["not an object", 7, {"value": None}, {"label": "", "value": ""}], "chart": None},
    "not a section",
]
grok_signed_out = entry("grok", [], error="Usage unavailable. Check this provider’s CodexBar login/configuration.",
                        plan="", age_min=0)
grok_signed_out["updatedAt"] = ""
# Signed in on a plan with no credits pool: a clean fetch, no windows, no error.
grok_free = entry("grok", [], plan="Free")

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
    "grok": snap([codex_ok, claude_ok, grok_ok]),
    "grok-signin": snap([codex_ok, grok_signed_out]),
    "grok-free": snap([codex_ok, grok_free]),
}
busy = snap([]); busy["busy"] = True
scenarios["busy"] = busy
for name, value in scenarios.items():
    write_fixture(here / f"{name}.json", value, indent=1)

sessions = {"updatedAt": iso(NOW), "sessions": [
    {"id": "codex", "name": "ChatGPT · Codex", "state": "ok", "detail": "Signed in · account quota comes from CodexBar.", "periods": [{"label":"7 days","tokens":42000000,"requests":40,"costUSD":0}]},
    {"id": "claude", "name": "Claude Code", "state": "ok", "detail": "Signed in",
     "periods": [{"label": "5 hours", "requests": 42, "tokens": 1850000, "costUSD": 0},
                 {"label": "7 days", "requests": 610, "tokens": 31200000, "costUSD": 0}],
     "note": "Local activity from Claude Code transcripts · not account quota (tokens include cache reads/writes)"},
    {"id": "opencode", "name": "OpenCode", "state": "ok", "detail": "Local activity", "periods": [{"label":"7 days","tokens":120813143,"requests":565,"costUSD":0}]},
    {"id": "grok", "name": "Grok Build", "state": "ok", "detail": "Signed in · account credits come from CodexBar.",
     "accountEmail": "me@grok.example",
     "periods": [{"label": "7 days", "tokens": 762841, "requests": 1, "costUSD": 0}],
     "note": "Local activity from Grok Build session usage · includes cached input and reasoning · not account quota"}]}
write_fixture(here / "sessions.json", sessions)
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
    write_fixture(here / f"accounts-{provider}.json", value)

write_fixture(here / "hints.json", scenarios["connected"], indent=1)
hint_accounts = copy.deepcopy(accounts)
hint_accounts["claude"]["accounts"][1]["windows"] = [
    window("primary", "5 hour", 300, 95, 190), window("secondary", "7 day", 10080, 90, 8000)]
hint_accounts["codex"]["accounts"][1]["windows"][1] = window("secondary", "7 day", 10080, 62, 45)
for provider, value in hint_accounts.items():
    write_fixture(here / f"accounts-{provider}-hints.json", value)

write_fixture(here / "opencode-compact.json", scenarios["connected"], indent=1)
write_fixture(here / "accounts-opencode-single.json", {"accounts": [accounts["opencode"]["accounts"][0]]})

# One person, three sign-ins shared across providers: the account-legend layout numbers each address once.
write_fixture(here / "shared-accounts.json", scenarios["connected"], indent=1)
shared = copy.deepcopy(accounts)
shared["codex"]["accounts"] = [
    {"email": "me@example.com", "id": "a", "active": True, "plan": "prolite", "windows": []},
    {"email": "work@example.org", "id": "b", "active": False, "plan": "plus", "windows": [
        window("primary", "5 hour", 300, 5, 65), window("secondary", "7 day", 10080, 62, 5000)]},
    {"email": "lab@example.edu", "id": "c", "active": False, "plan": "plus", "windows": [
        window("primary", "5 hour", 300, 88, 20), window("secondary", "7 day", 10080, 40, 7000)]}]
shared["claude"].update(activeEmail="me@example.com", activePlan="max20x", displayEmail="me@example.com", displayPlan="max20x")
shared["claude"]["desktop"]["email"] = "me@example.com"
shared["claude"]["accounts"][0].update(email="me@example.com", plan="max20x")
shared["claude"]["accounts"][1].update(email="work@example.org", plan="pro")
shared["opencode"]["accounts"][0]["email"] = "me@example.com"
shared["opencode"]["accounts"][1]["email"] = "work@example.org"
for provider, value in shared.items():
    write_fixture(here / f"accounts-{provider}-shared.json", value)

# Different CLI/app logins: app quota must win even when the CLI account is exhausted.
write_fixture(here / "claude-split.json", scenarios["connected"], indent=1)
split = copy.deepcopy(accounts["claude"])
split.update(activeEmail="work@claude.example", activePlan="max20x",
             displayEmail="me@claude.example", displayPlan="pro")
split["desktop"]["differs"] = True
for row in split["accounts"]:
    row["active"] = row["number"] == 2
    row["panelActive"] = row["number"] == 1
split["accounts"][1]["plan"] = "max20x"
write_fixture(here / "accounts-claude-split.json", split)
