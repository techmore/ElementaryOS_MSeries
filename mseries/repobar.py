#!/usr/bin/env python3
"""Read-only GitHub repository snapshot for the elementary OS RepoBar indicator."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


QUERY = """query($cursor: String) {
  viewer {
    login
    repositories(first: 100, after: $cursor,
      affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER],
      orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        nameWithOwner url isPrivate isArchived stargazerCount forkCount updatedAt
        openIssues: issues(states: OPEN) { totalCount }
        openPullRequests: pullRequests(states: OPEN) { totalCount }
        defaultBranchRef { name target { ... on Commit { statusCheckRollup { state } } } }
        latestRelease { tagName }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""

CACHE = Path.home() / ".cache/mseries/repobar/snapshot.json"
CACHE_TTL_SECONDS = 300


def _query_page(cursor: str | None) -> dict:
    command = ["gh", "api", "graphql", "-f", f"query={QUERY}"]
    if cursor:
        command.extend(["-F", f"cursor={cursor}"])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("GitHub CLI (gh) is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("GitHub did not respond before the 45 second timeout") from exc
    if result.returncode:
        message = result.stderr.strip() or "GitHub query failed"
        if "not logged" in message.lower() or "authentication" in message.lower():
            message += " — run `gh auth login` to connect your GitHub account"
        raise RuntimeError(message)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub CLI returned invalid JSON") from exc
    if payload.get("errors"):
        message = "; ".join(str(error.get("message", "GraphQL error")) for error in payload["errors"])
        raise RuntimeError(message)
    return payload


def fetch_snapshot() -> dict:
    cursor = None
    repos = []
    login = ""
    for _ in range(10):
        payload = _query_page(cursor)
        viewer = payload.get("data", {}).get("viewer")
        if not viewer:
            raise RuntimeError("GitHub did not return the signed-in account")
        login = viewer.get("login", "")
        connection = viewer.get("repositories", {})
        repos.extend(connection.get("nodes") or [])
        page = connection.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
        if not cursor:
            raise RuntimeError("GitHub pagination returned no cursor")
    else:
        raise RuntimeError("Repository list exceeded the 1,000 repository safety limit")

    normalized = []
    for repo in repos:
        branch = repo.get("defaultBranchRef") or {}
        target = branch.get("target") or {}
        rollup = target.get("statusCheckRollup") or {}
        normalized.append({
            "name": repo.get("nameWithOwner", ""),
            "url": repo.get("url", ""),
            "private": bool(repo.get("isPrivate")),
            "archived": bool(repo.get("isArchived")),
            "stars": int(repo.get("stargazerCount") or 0),
            "forks": int(repo.get("forkCount") or 0),
            "updatedAt": repo.get("updatedAt", ""),
            "openIssues": int((repo.get("openIssues") or {}).get("totalCount") or 0),
            "openPullRequests": int((repo.get("openPullRequests") or {}).get("totalCount") or 0),
            "branch": branch.get("name", ""),
            "ci": rollup.get("state", "UNKNOWN").upper(),
            "release": (repo.get("latestRelease") or {}).get("tagName", ""),
        })
    normalized.sort(key=lambda item: item["updatedAt"], reverse=True)
    now = int(time.time())
    return {"schemaVersion": 1, "account": login, "fetchedAt": now, "stale": False, "repos": normalized}


def write_cache(payload: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(CACHE.parent, 0o700)
    fd, temp_path = tempfile.mkstemp(prefix="repobar-", dir=CACHE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, CACHE)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def read_cache() -> dict | None:
    try:
        with CACHE.open(encoding="utf-8") as stream:
            payload = json.load(stream)
        if payload.get("schemaVersion") != 1 or not isinstance(payload.get("repos"), list):
            return None
        payload["stale"] = True
        return payload
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="fetch a fresh read-only GitHub snapshot")
    parser.add_argument("--max-age", type=int, default=CACHE_TTL_SECONDS, help="cache lifetime in seconds")
    args = parser.parse_args()

    cached = read_cache()
    is_fresh = False
    if cached:
        age = max(0, int(time.time()) - int(cached.get("fetchedAt", 0)))
        is_fresh = age <= max(0, args.max_age)
    if cached and is_fresh and not args.refresh:
        cached["stale"] = False
        print(json.dumps(cached, separators=(",", ":")))
        return 0

    try:
        payload = fetch_snapshot()
        write_cache(payload)
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    except (RuntimeError, OSError) as exc:
        if cached:
            cached["error"] = str(exc)
            print(json.dumps(cached, separators=(",", ":")))
            return 0
        print(json.dumps({"schemaVersion": 1, "account": "", "fetchedAt": 0,
                          "stale": True, "repos": [], "error": str(exc)}), file=sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
