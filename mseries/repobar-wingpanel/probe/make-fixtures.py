#!/usr/bin/env python3
"""Write deterministic RepoBar snapshots for the headless render probe (synthetic repositories only)."""
import json, pathlib, time

here = pathlib.Path(__file__).parent / "fixtures"
here.mkdir(exist_ok=True)
NOW = int(time.time())


def repo(name, issues=0, prs=0, ci="SUCCESS", stars=0, release="", lang="Vala", state="visible",
         counts=(0, 0, 0), activity=None, local=None, private=False, archived=False, desc="", pages="", homepage=""):
    return {"name": name, "url": "https://github.com/" + name, "description": desc, "private": private,
            "archived": archived, "fork": False, "stars": stars, "forks": 0, "updatedAt": "",
            "openIssues": issues, "openPullRequests": prs, "branch": "main",
            "commitCounts": {"1h": counts[0], "24h": counts[1], "30d": counts[2]}, "ci": ci,
            "release": release, "language": lang, "topics": [], "recentActivity": activity,
            "local": local, "repoState": state, "pagesUrl": pages, "homepage": homepage}


repos = [
    repo("example/panel-suite", 8, 5, "SUCCESS", 42, "v2.3.0", "Python", "pinned", (11, 400, 974),
         {"kind": "commit", "title": "Battery app: remembered window state and shortcuts", "url": "https://github.com/example/panel-suite"},
         {"branch": "main", "ahead": 1, "behind": 3, "dirtyFileCount": 2, "path": "/home/me/Projects/panel-suite"},
         desc="Desktop panel indicators", pages="https://example.github.io/panel-suite/"),
    repo("example/kernel-notes", 2, 1, "FAILURE", 7, "", "C", counts=(0, 6, 88),
         activity={"kind": "pull request", "title": "Fix display link training timeout", "url": "https://github.com/example/kernel-notes/pull/3"}),
    repo("example/dock", 0, 2, "PENDING", 3, "v0.4.1", "Vala", counts=(2, 14, 61), private=True),
    repo("example/dotfiles", 0, 0, "UNKNOWN", 0, "", "Shell", counts=(0, 0, 4)),
    repo("example/website", 1, 0, "SUCCESS", 120, "v1.0.0", "TypeScript", counts=(0, 1, 30), homepage="https://example.org"),
    repo("example/old-tool", 0, 0, "SUCCESS", 1, "", "Go", archived=True),
]

base = {"schemaVersion": 1, "account": "example", "host": "github.com", "fetchedAt": NOW - 120,
        "rateLimits": {"resources": {"core": {"remaining": 4876, "limit": 5000}}}, "stale": False,
        "settings": {"refreshInterval": 300, "repoLimit": 5, "showForks": False, "showArchived": False}}
scenarios = {
    "healthy": {**base, "repos": repos},
    "empty": {**base, "repos": []},
    "error": {**base, "repos": repos[:3], "stale": True, "error": "gh: HTTP 502 from api.github.com"},
}
for name, value in scenarios.items():
    (here / f"{name}.json").write_text(json.dumps(value, indent=1))
