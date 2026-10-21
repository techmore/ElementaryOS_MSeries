#!/usr/bin/env python3
"""Read-only GitHub repository snapshot for the elementary OS RepoBar indicator."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fnmatch
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse


QUERY = """query($cursor: String, $since1h: GitTimestamp!, $since24h: GitTimestamp!, $since30d: GitTimestamp!) {
  viewer {
    login
    repositories(first: 25, after: $cursor,
      affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER],
      orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        nameWithOwner url description isPrivate isArchived isFork stargazerCount forkCount updatedAt homepageUrl
        pagesDeploy: deployments(environments: ["github-pages"], first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { latestStatus { state environmentUrl } }
        }
        primaryLanguage { name }
        repositoryTopics(first: 8) { nodes { topic { name } } }
        openIssues: issues(states: OPEN, first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) {
          totalCount
          nodes { title number updatedAt url }
        }
        openPullRequests: pullRequests(states: OPEN, first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) {
          totalCount
          nodes { title number updatedAt url }
        }
        defaultBranchRef {
          name
          target { ... on Commit {
            statusCheckRollup { state }
            history(first: 1) { nodes { committedDate messageHeadline url } }
            commits1h: history(first: 1, since: $since1h) { totalCount }
            commits24h: history(first: 1, since: $since24h) { totalCount }
            commits30d: history(first: 1, since: $since30d) { totalCount }
          } }
        }
        latestRelease { name tagName publishedAt url }
        mergedPullRequests: pullRequests(states: MERGED, first: 3, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes { title number url mergedAt }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""

CACHE = Path.home() / ".cache/mseries/repobar/snapshot.json"
CACHE_DIR = CACHE.parent
SETTINGS = Path.home() / ".config/mseries/repobar/settings.json"
CACHE_TTL_SECONDS = 300
API_TTL_SECONDS = 90
DEFAULT_SETTINGS = {
    "version": 1,
    "host": "github.com",
    "account": "",
    "showInPanel": True,
    "refreshInterval": 300,
    "repoLimit": 20,
    "menuSort": "activity",
    "showForks": False,
    "showArchived": False,
    "activityScope": "all",
    "localRoot": "",
    "localDepth": 4,
    "notifyCi": True,
    "notifyWorkflows": True,
    "mergeWindowMinutes": 60,
    "showContributions": True,
    "contributionStyle": "dots",
    "repoStates": {},
}
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def load_settings() -> dict:
    try:
        with SETTINGS.open(encoding="utf-8") as stream:
            payload = json.load(stream)
        if payload.get("version") != 1:
            raise ValueError("Unsupported RepoBar settings version")
        result = {**DEFAULT_SETTINGS, **payload}
        if not isinstance(result.get("repoStates"), dict):
            result["repoStates"] = {}
        return result
    except FileNotFoundError:
        return {**DEFAULT_SETTINGS, "repoStates": {}}
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return {**DEFAULT_SETTINGS, "repoStates": {}}


def write_private_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temp_path = tempfile.mkstemp(prefix="repobar-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def save_settings(payload: dict) -> None:
    write_private_json(SETTINGS, payload)


def _hostname(settings: dict | None = None) -> str:
    host = (settings or load_settings()).get("host", "github.com")
    host = str(host).strip().lower()
    if not re.fullmatch(r"[a-z0-9.-]+(?::[0-9]{1,5})?", host):
        raise RuntimeError("GitHub host must be a hostname, without a URL path")
    return host


def _account(settings: dict | None = None) -> str:
    """The signed-in login RepoBar reads as; empty follows the GitHub CLI's active account on the host."""
    account = str((settings or load_settings()).get("account", "")).strip()
    if account and not re.fullmatch(r"[A-Za-z0-9_.-]+", account):
        raise RuntimeError("GitHub account must be a login name")
    return account


def _gh_accounts() -> list[dict]:
    """Every account the GitHub CLI is signed in to, parsed from `gh auth status` (the CLI has no JSON for it)."""
    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=10, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("GitHub CLI (gh) is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("GitHub CLI did not respond before the timeout") from exc
    accounts: list[dict] = []
    for line in (result.stdout + result.stderr).splitlines():
        match = re.search(r"Logged in to (\S+) account (\S+)", line)
        if match and "Failed" not in line:
            accounts.append({"host": match.group(1).lower(), "login": match.group(2), "active": False})
        elif accounts and re.search(r"Active account:\s*true", line):
            accounts[-1]["active"] = True
    return accounts


@functools.lru_cache(maxsize=8)
def _token_env(host: str, account: str) -> tuple[tuple[str, str], ...]:
    """Environment that makes one `gh` call run as `account`, without switching the CLI's global active account
    (which would change what git and every other tool signs in as). The token is handed to the child process and
    is never stored or printed."""
    if not account:
        return ()
    result = subprocess.run(["gh", "auth", "token", "--hostname", host, "--user", account],
                            capture_output=True, text=True, timeout=10, check=False)
    token = result.stdout.strip()
    if result.returncode or not token:
        raise RuntimeError(f"{account} is not signed in to {host} — run `gh auth login --hostname {host}`")
    name = "GH_TOKEN" if host == "github.com" or host.endswith(".ghe.com") else "GH_ENTERPRISE_TOKEN"
    return ((name, token),)


def _gh_env() -> dict:
    host = _hostname()
    return {**os.environ, "GH_HOST": host, **dict(_token_env(host, _account()))}


def _run_gh(arguments: list[str], *, timeout: int = 45) -> subprocess.CompletedProcess:
    host = _hostname()
    command = ["gh", "api", "--hostname", host, *arguments]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False, env=_gh_env())
    except FileNotFoundError as exc:
        raise RuntimeError("GitHub CLI (gh) is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("GitHub did not respond before the timeout") from exc
    if result.returncode:
        message = result.stderr.strip() or "GitHub API request failed"
        if "not logged" in message.lower() or "authentication" in message.lower():
            message += " — run `gh auth login` to connect this GitHub host"
        raise RuntimeError(message)
    return result


def _api_json(endpoint: str, *fields: str, force: bool = False) -> tuple[object, int]:
    key = hashlib.sha256(("\0".join([_hostname(), _account(), endpoint, *fields])).encode()).hexdigest()
    cache_file = CACHE_DIR / "api" / f"{key}.json"
    if not force:
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            age = max(0, int(time.time()) - int(payload.get("fetchedAt", 0)))
            if age <= API_TTL_SECONDS:
                return payload["data"], int(payload["fetchedAt"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
    args = [endpoint]
    for field in fields:
        args.extend(["-F", field])
    response = _run_gh(args)
    try:
        data = json.loads(response.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub CLI returned invalid JSON") from exc
    fetched_at = int(time.time())
    write_private_json(cache_file, {"fetchedAt": fetched_at, "data": data})
    return data, fetched_at


def _graphql(query: str, cursor: str | None = None, variables: dict[str, str] | None = None,
             extra: list[str] | None = None) -> dict:
    args = ["graphql", "-f", f"query={query}"]
    for item in extra or []:
        args.extend(["-F", item])
    if cursor:
        args.extend(["-F", f"cursor={cursor}"])
    for name, value in (variables or {}).items():
        args.extend(["-F", f"{name}={value}"])
    response = _run_gh(args)
    try:
        payload = json.loads(response.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub CLI returned invalid JSON") from exc
    if payload.get("errors"):
        message = "; ".join(str(error.get("message", "GraphQL error")) for error in payload["errors"])
        raise RuntimeError(message)
    return payload


# Repository fields come from QUERY; listing ids first lets the expensive details load in parallel batches.
REPO_FIELDS = QUERY[QUERY.index("nodes {", QUERY.index("repositories(")) + len("nodes {"):QUERY.index("pageInfo {")].rstrip().rstrip("}")
IDS_QUERY = """query($cursor: String) {
  viewer {
    login
    repositories(first: 100, after: $cursor,
      affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER],
      orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes { id }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""
DETAILS_QUERY = ("query($ids: [ID!]!, $since1h: GitTimestamp!, $since24h: GitTimestamp!, $since30d: GitTimestamp!) {\n"
                 "  nodes(ids: $ids) { ... on Repository {" + REPO_FIELDS + "} }\n}")
DETAIL_BATCH = 25


def _query_page(cursor: str | None, since: dict[str, str]) -> dict:
    return _graphql(QUERY, cursor, since)


def _repository_ids() -> tuple[str, list[str]]:
    cursor = None
    login = ""
    ids: list[str] = []
    for _ in range(10):
        payload = _graphql(IDS_QUERY, cursor)
        viewer = (payload.get("data") or {}).get("viewer")
        if not viewer:
            raise RuntimeError("GitHub did not return the signed-in account")
        login = viewer.get("login", "")
        connection = viewer.get("repositories") or {}
        ids.extend(node["id"] for node in connection.get("nodes") or [] if node and node.get("id"))
        page = connection.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return login, ids
        cursor = page.get("endCursor")
        if not cursor:
            raise RuntimeError("GitHub pagination returned no cursor")
    raise RuntimeError("Repository list exceeded the 1,000 repository safety limit")


def _repository_details(ids: list[str], since: dict[str, str]) -> list[dict]:
    payload = _graphql(DETAILS_QUERY, None, since, [f"ids[]={value}" for value in ids])
    return [node for node in (payload.get("data") or {}).get("nodes") or [] if node]


ACTIVE_RUN_STATES = {"queued", "in_progress", "waiting", "requested", "pending"}


def _workflow_runs(repos: list[dict], now: int) -> dict:
    """Running and just-finished GitHub Actions runs (every branch and pull request) in recently active repositories."""
    cutoff = datetime.fromtimestamp(now - 7 * 24 * 60 * 60, timezone.utc).isoformat().replace("+00:00", "Z")
    working = [repo["name"] for repo in repos
               if repo["repoState"] != "hidden" and not repo["archived"] and not repo["fork"]
               and repo["updatedAt"] >= cutoff][:30]

    def runs_for(name: str) -> list[dict]:
        try:
            payload = json.loads(_run_gh([f"repos/{name}/actions/runs?per_page=15"]).stdout)
        except (RuntimeError, json.JSONDecodeError):
            return []  # Actions disabled, no access, or a transient error: that repository just has no runs.
        found = []
        for run in payload.get("workflow_runs") or []:
            found.append({
                "id": run.get("id"), "repo": name, "name": run.get("name") or run.get("display_title") or "workflow",
                "branch": run.get("head_branch") or "", "event": run.get("event") or "",
                "status": run.get("status") or "", "conclusion": run.get("conclusion") or "",
                "url": run.get("html_url") or "", "createdAt": run.get("created_at") or "",
                "updatedAt": run.get("updated_at") or "",
            })
        return found

    with ThreadPoolExecutor(max_workers=6) as pool:
        runs = [run for batch in pool.map(runs_for, working) for run in batch]
    # A run "in progress" for over six hours is stuck or abandoned, not work in flight.
    stale_cutoff = datetime.fromtimestamp(now - 6 * 60 * 60, timezone.utc).isoformat().replace("+00:00", "Z")
    running = [run for run in runs if run["status"] in ACTIVE_RUN_STATES and run["createdAt"] >= stale_cutoff]
    recent_cutoff = datetime.fromtimestamp(now - 2 * 60 * 60, timezone.utc).isoformat().replace("+00:00", "Z")
    finished = [run for run in runs if run["status"] == "completed" and run["updatedAt"] >= recent_cutoff]
    running.sort(key=lambda run: run["createdAt"], reverse=True)
    finished.sort(key=lambda run: run["updatedAt"], reverse=True)
    return {"checkedRepos": len(working), "running": running[:50], "finished": finished[:50]}


def fetch_snapshot() -> dict:
    now = int(time.time())
    since = {
        "since1h": datetime.fromtimestamp(now - 60 * 60, timezone.utc).isoformat().replace("+00:00", "Z"),
        "since24h": datetime.fromtimestamp(now - 24 * 60 * 60, timezone.utc).isoformat().replace("+00:00", "Z"),
        "since30d": datetime.fromtimestamp(now - 30 * 24 * 60 * 60, timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    login, ids = _repository_ids()
    batches = [ids[start:start + DETAIL_BATCH] for start in range(0, len(ids), DETAIL_BATCH)]
    # Detail batches and the independent extras run side by side; each is one `gh` process.
    with ThreadPoolExecutor(max_workers=6) as pool:
        detail_jobs = [pool.submit(_repository_details, batch, since) for batch in batches]
        pages_job = pool.submit(_pages_repositories)
        for_you_job = pool.submit(_for_you)
        contributions_job = pool.submit(_contributions)
        repos = [repo for job in detail_jobs for repo in job.result()]
        pages_names = pages_job.result()
        for_you = for_you_job.result()
        contributions = contributions_job.result()

    normalized = []
    settings = load_settings()
    local_by_name: dict[str, list[dict]] = {}
    if settings.get("localRoot"):
        try:
            scanned = scan_local_projects(settings["localRoot"], int(settings.get("localDepth", 4)))
        except RuntimeError:
            scanned = []
        for local_repo in scanned:
            remote_name = local_repo.get("name", "")
            if REPO_RE.fullmatch(remote_name):
                local_by_name.setdefault(remote_name, []).append(local_repo)
        # The primary checkout is the folder named after the repository; worktrees and other clones follow.
        for remote_name, checkouts in local_by_name.items():
            short = remote_name.split("/", 1)[1].casefold()
            checkouts.sort(key=lambda item: (Path(item["path"]).name.casefold() != short, item["path"]))
    for repo in repos:
        branch = repo.get("defaultBranchRef") or {}
        target = branch.get("target") or {}
        rollup = target.get("statusCheckRollup") or {}
        commit_counts = {
            "1h": int((target.get("commits1h") or {}).get("totalCount") or 0),
            "24h": int((target.get("commits24h") or {}).get("totalCount") or 0),
            "30d": int((target.get("commits30d") or {}).get("totalCount") or 0),
        }
        issue_conn = repo.get("openIssues") or {}
        pull_conn = repo.get("openPullRequests") or {}
        latest_issue = (issue_conn.get("nodes") or [{}])[0]
        latest_pull = (pull_conn.get("nodes") or [{}])[0]
        latest_commit = ((target.get("history") or {}).get("nodes") or [{}])[0]
        release = repo.get("latestRelease") or {}
        merges = [item for item in (repo.get("mergedPullRequests") or {}).get("nodes") or [] if item and item.get("mergedAt")]
        last_merge = max(merges, key=lambda item: item["mergedAt"], default=None)
        recent = [
            {"kind": "issue", **latest_issue} if latest_issue.get("updatedAt") else None,
            {"kind": "pull", **latest_pull} if latest_pull.get("updatedAt") else None,
            {"kind": "commit", "title": latest_commit.get("messageHeadline"),
             "updatedAt": latest_commit.get("committedDate"), "url": latest_commit.get("url")}
            if latest_commit.get("committedDate") else None,
        ]
        recent = [item for item in recent if item]
        recent.sort(key=lambda item: item.get("updatedAt", ""), reverse=True)
        state = settings.get("repoStates", {}).get(repo.get("nameWithOwner", ""), "visible")
        normalized.append({
            "name": repo.get("nameWithOwner", ""),
            "url": repo.get("url", ""),
            "description": repo.get("description") or "",
            "private": bool(repo.get("isPrivate")),
            "archived": bool(repo.get("isArchived")),
            "fork": bool(repo.get("isFork")),
            "stars": int(repo.get("stargazerCount") or 0),
            "forks": int(repo.get("forkCount") or 0),
            "updatedAt": repo.get("updatedAt", ""),
            "openIssues": int(issue_conn.get("totalCount") or 0),
            "openPullRequests": int(pull_conn.get("totalCount") or 0),
            "branch": branch.get("name", ""),
            "commitCounts": commit_counts,
            "ci": rollup.get("state", "UNKNOWN").upper(),
            "lastMerge": ({key: last_merge.get(key) for key in ("title", "number", "url", "mergedAt")}
                          if last_merge else None),
            "release": release.get("tagName", ""),
            "releaseName": release.get("name") or release.get("tagName", ""),
            "releaseUrl": release.get("url", ""),
            "releaseDate": release.get("publishedAt", ""),
            "language": (repo.get("primaryLanguage") or {}).get("name", ""),
            "topics": [item.get("topic", {}).get("name", "") for item in (repo.get("repositoryTopics") or {}).get("nodes", [])],
            "recentActivity": recent[0] if recent else None,
            "pagesUrl": _pages_url(repo, pages_names),
            "homepage": _web_url(repo.get("homepageUrl") or ""),
            "local": (local_by_name.get(repo.get("nameWithOwner", "")) or [None])[0],
            "localCheckouts": [{key: item.get(key) for key in ("path", "branch", "dirtyFileCount", "ahead", "behind", "detached")}
                               for item in local_by_name.get(repo.get("nameWithOwner", ""), [])],
            "repoState": state if state in {"visible", "pinned", "hidden"} else "visible",
        })
    normalized.sort(key=lambda item: item["updatedAt"], reverse=True)
    try:
        rate_limit, rate_fetched_at = _api_json("rate_limit")
        rate_error = ""
    except RuntimeError as exc:
        rate_limit, rate_fetched_at, rate_error = {}, 0, str(exc)
    try:
        actions = _workflow_runs(normalized, now)
    except RuntimeError:
        actions = None
    return {"schemaVersion": 1, "account": login, "actions": actions, "host": _hostname(), "fetchedAt": now,
            "rateFetchedAt": rate_fetched_at, "rateLimits": rate_limit, "rateError": rate_error,
            "settings": settings, "stale": False, "forYou": for_you,
            "contributions": contributions, "repos": normalized}


FOR_YOU_QUERY = """{
  reviews: search(query: "is:pr is:open archived:false review-requested:@me", type: ISSUE, first: 5) {
    issueCount
    nodes { ... on PullRequest { title number url updatedAt repository { nameWithOwner } } }
  }
  assigned: search(query: "is:issue is:open archived:false assignee:@me", type: ISSUE, first: 5) {
    issueCount
    nodes { ... on Issue { title number url updatedAt repository { nameWithOwner } } }
  }
}"""


CONTRIBUTIONS_QUERY = """{
  viewer { contributionsCollection { contributionCalendar {
    totalContributions
    weeks { contributionDays { date contributionCount contributionLevel } }
  } } }
}"""
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def _contributions() -> dict:
    """The viewer's contribution calendar for the past year, as weeks of [date, count, level 0-4] days."""
    try:
        calendar = ((((_graphql(CONTRIBUTIONS_QUERY).get("data") or {}).get("viewer") or {})
                     .get("contributionsCollection") or {}).get("contributionCalendar") or {})
    except RuntimeError:
        return {}
    weeks = [[[day.get("date", ""), int(day.get("contributionCount") or 0), LEVELS.get(day.get("contributionLevel"), 0)]
              for day in week.get("contributionDays") or []] for week in calendar.get("weeks") or []]
    return {"total": int(calendar.get("totalContributions") or 0), "weeks": weeks} if weeks else {}


def _for_you() -> dict:
    """Pull requests waiting for the viewer's review and issues assigned to them; empty when GitHub cannot answer."""
    try:
        data = _graphql(FOR_YOU_QUERY).get("data") or {}
    except RuntimeError:
        return {}
    result = {}
    for key in ("reviews", "assigned"):
        conn = data.get(key) or {}
        items = [{"title": node.get("title", ""), "number": node.get("number", 0), "url": node.get("url", ""),
                  "updatedAt": node.get("updatedAt", ""), "repo": (node.get("repository") or {}).get("nameWithOwner", "")}
                 for node in conn.get("nodes") or [] if node.get("url")]
        result[key] = {"count": int(conn.get("issueCount") or 0), "items": items}
    return result


def _pages_repositories() -> set[str]:
    """Names of repositories with a published GitHub Pages site; REST is the only listing that includes branch-built sites."""
    try:
        result = _run_gh(["--paginate", "user/repos?per_page=100&affiliation=owner,collaborator,organization_member",
                          "--jq", ".[] | select(.has_pages) | .full_name"], timeout=60)
    except RuntimeError:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if REPO_RE.fullmatch(line.strip())}


def _web_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc and "." in parsed.netloc else ""


def _pages_url(repo: dict, pages_names: set[str]) -> str:
    """The deployed Pages address (custom domains included) or, for branch-built sites, the github.io default."""
    for node in (repo.get("pagesDeploy") or {}).get("nodes") or []:
        status = node.get("latestStatus") or {}
        if status.get("state") == "SUCCESS" and _web_url(status.get("environmentUrl") or ""):
            return status["environmentUrl"]
    name = repo.get("nameWithOwner", "")
    if name not in pages_names or _hostname() != "github.com":
        return ""
    owner, repository = name.split("/", 1)
    site = f"{owner.lower()}.github.io"
    return f"https://{site}/" if repository.lower() == site else f"https://{site}/{repository}/"


def write_cache(payload: dict) -> None:
    write_private_json(CACHE, payload)


def apply_settings(snapshot: dict) -> dict:
    settings = load_settings()
    for repo in snapshot.get("repos", []):
        repo["repoState"] = settings.get("repoStates", {}).get(repo.get("name", ""), "visible")
    snapshot["settings"] = settings
    return snapshot


def read_cache() -> dict | None:
    try:
        with CACHE.open(encoding="utf-8") as stream:
            payload = json.load(stream)
        if payload.get("schemaVersion") != 1 or not isinstance(payload.get("repos"), list):
            return None
        settings = load_settings()
        account = _account(settings)
        if payload.get("host") != _hostname(settings) or (account and str(payload.get("account", "")).lower() != account.lower()):
            return None
        payload["stale"] = True
        return apply_settings(payload)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def get_snapshot(force: bool = False, max_age: int = CACHE_TTL_SECONDS) -> dict:
    cached = read_cache()
    if cached:
        age = max(0, int(time.time()) - int(cached.get("fetchedAt", 0)))
        if age <= max(0, max_age) and not force:
            cached["stale"] = False
            return cached
    try:
        return apply_settings(fetch_and_cache())
    except (RuntimeError, OSError) as exc:
        if cached:
            cached["error"] = str(exc)
            cached["stale"] = True
            return cached
        raise


def fetch_and_cache() -> dict:
    payload = fetch_snapshot()
    write_cache(payload)
    return payload


def _safe_repo_name(value: str) -> str:
    value = value.strip().removeprefix("https://github.com/").removesuffix(".git").strip("/")
    if not REPO_RE.fullmatch(value):
        raise RuntimeError("Repository must be written as owner/name")
    return value


def set_repo_state(name: str, state: str) -> dict:
    name = _safe_repo_name(name)
    if state not in {"visible", "pinned", "hidden"}:
        raise RuntimeError("Repository state must be visible, pinned, or hidden")
    settings = load_settings()
    states = dict(settings.get("repoStates", {}))
    if state == "visible":
        states.pop(name, None)
    else:
        states[name] = state
    settings["repoStates"] = states
    save_settings(settings)
    return {"repository": name, "state": state}


def _git(path: Path, *arguments: str, timeout: int = 5) -> str:
    try:
        result = subprocess.run(["git", "-C", str(path), *arguments], capture_output=True,
                                text=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Git command failed for {path}") from exc
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Git command failed for {path}")
    return result.stdout.strip()


def _remote_name(remote: str) -> str:
    remote = remote.strip()
    if remote.startswith("git@") and ":" in remote:
        host, path = remote.split(":", 1)
        host = host.split("@", 1)[-1]
    else:
        parsed = urlparse(remote if "://" in remote else "https://" + remote)
        host, path = parsed.hostname or "", parsed.path.lstrip("/")
    if host in {"github.com", _hostname()}:
        path = path.removesuffix(".git").strip("/")
        if REPO_RE.fullmatch(path):
            return path
    return ""


def _git_repo_status(path: Path) -> dict:
    root = Path(_git(path, "rev-parse", "--show-toplevel"))
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    try:
        upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    except RuntimeError:
        upstream = ""
    dirty_lines = _git(root, "status", "--porcelain=v1", "--untracked-files=normal").splitlines()
    ahead = behind = 0
    if upstream:
        counts = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        try:
            ahead, behind = [int(value) for value in counts.split()]
        except (ValueError, TypeError):
            ahead = behind = 0
    remote = ""
    try:
        remote = _git(root, "remote", "get-url", "origin")
    except RuntimeError:
        pass
    worktrees = []
    try:
        records = _git(root, "worktree", "list", "--porcelain").split("\n\n")
        for record in records:
            values = dict(line.split(" ", 1) for line in record.splitlines() if " " in line)
            worktrees.append({"path": values.get("worktree", ""), "branch": values.get("branch", "").removeprefix("refs/heads/")})
    except RuntimeError:
        pass
    return {
        "path": str(root), "name": _remote_name(remote) or root.name,
        "remote": remote, "branch": branch, "upstream": upstream,
        "dirty": bool(dirty_lines), "dirtyFiles": [line[3:] for line in dirty_lines[:3]],
        "dirtyFileCount": len(dirty_lines), "ahead": ahead, "behind": behind,
        "detached": branch == "HEAD", "worktrees": worktrees,
    }


def scan_local_projects(root: str, depth: int = 4) -> list[dict]:
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise RuntimeError(f"Local projects folder does not exist: {base}")
    found: list[dict] = []
    visited = 0

    def walk(folder: Path, level: int) -> None:
        nonlocal visited
        if level > max(0, min(10, depth)) or visited >= 500:
            return
        visited += 1
        if (folder / ".git").exists():
            try:
                found.append(_git_repo_status(folder))
            except RuntimeError:
                pass
            return
        try:
            entries = sorted(os.scandir(folder), key=lambda item: item.name.casefold())
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith(".") or entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                continue
            walk(Path(entry.path), level + 1)

    walk(base, 0)
    return found


def clone_local_repo(name: str, settings: dict) -> dict:
    """Clone a repository into the projects folder; never overwrites an existing folder."""
    name = _safe_repo_name(name)
    root = settings.get("localRoot", "")
    if not root:
        raise RuntimeError("Choose a projects folder in RepoBar Settings first")
    destination = Path(root).expanduser().resolve() / name.split("/", 1)[1]
    if destination.exists():
        raise RuntimeError(f"{destination} already exists")
    try:
        result = subprocess.run(["gh", "repo", "clone", name, str(destination)], capture_output=True, text=True,
                                timeout=600, check=False, env=_gh_env())
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Clone did not finish within 10 minutes") from exc
    if result.returncode:
        raise RuntimeError(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "Clone failed")
    return {"cloned": name, "path": str(destination)}


def sync_local_repo(path: str, confirmed: bool = False) -> dict:
    repo = _git_repo_status(Path(path).expanduser())
    if repo["dirty"]:
        raise RuntimeError("Sync stopped: the working tree has local changes")
    if repo["detached"]:
        raise RuntimeError("Sync stopped: checkout is detached")
    if not repo["upstream"]:
        raise RuntimeError("Sync stopped: the current branch has no upstream")
    if not confirmed:
        return {**repo, "wouldSync": repo["behind"] > 0 and repo["ahead"] == 0,
                "message": "Pass --yes to fetch and fast-forward this clean checkout."}
    upstream_remote = repo["upstream"].split("/", 1)[0]
    _git(Path(repo["path"]), "fetch", "--prune", upstream_remote, timeout=60)
    counts = _git(Path(repo["path"]), "rev-list", "--left-right", "--count", f"HEAD...{repo['upstream']}")
    ahead, behind = [int(value) for value in counts.split()]
    if ahead != 0 or behind == 0:
        raise RuntimeError("Sync stopped: branch is not a clean fast-forward candidate")
    _git(Path(repo["path"]), "pull", "--ff-only", timeout=60)
    return {**_git_repo_status(Path(repo["path"])), "synced": True}


def filter_repositories(snapshot: dict, scope: str = "dashboard", query: str = "", sort: str = "", limit: int = -1) -> list[dict]:
    settings = snapshot.get("settings") or load_settings()
    repos = list(snapshot.get("repos", []))
    query = query.strip().casefold()
    selected = []
    for repo in repos:
        state = repo.get("repoState", "visible")
        if not settings.get("showArchived", False) and repo.get("archived"):
            continue
        if not settings.get("showForks", False) and repo.get("fork"):
            continue
        if scope == "pinned" and state != "pinned":
            continue
        if scope == "hidden" and state != "hidden":
            continue
        if scope == "visible" and state == "hidden":
            continue
        if scope == "work" and not (repo.get("openIssues") or repo.get("openPullRequests") or repo.get("ci") in {"FAILURE", "ERROR", "PENDING"}):
            continue
        if scope == "issues" and not repo.get("openIssues"):
            continue
        if scope == "prs" and not repo.get("openPullRequests"):
            continue
        haystack = " ".join([repo.get("name", ""), repo.get("description", ""), repo.get("language", ""), *repo.get("topics", [])]).casefold()
        if query and query not in haystack:
            continue
        selected.append(repo)
    sort = sort or settings.get("menuSort", "activity")
    if sort == "issues":
        selected.sort(key=lambda item: (item.get("openIssues", 0), item.get("updatedAt", "")), reverse=True)
    elif sort == "prs":
        selected.sort(key=lambda item: (item.get("openPullRequests", 0), item.get("updatedAt", "")), reverse=True)
    elif sort == "stars":
        selected.sort(key=lambda item: (item.get("stars", 0), item.get("updatedAt", "")), reverse=True)
    elif sort == "repo":
        selected.sort(key=lambda item: item.get("name", "").casefold())
    elif sort == "pinned":
        selected.sort(key=lambda item: (item.get("repoState") != "pinned", item.get("updatedAt", "")), reverse=False)
    else:
        selected.sort(key=lambda item: item.get("updatedAt", ""), reverse=True)
    if scope == "dashboard":
        pinned = [item for item in selected if item.get("repoState") == "pinned"]
        recent = [item for item in selected if item.get("repoState") != "hidden" and item not in pinned]
        count = max(1, min(100, int(settings.get("repoLimit", 20))))
        selected = pinned + recent[:max(0, count - len(pinned))]
    if limit >= 0:
        selected = selected[:limit]
    return selected


def _repo_details(name: str, endpoint: str, limit: int = 20, force: bool = False) -> object:
    name = _safe_repo_name(name)
    if endpoint == "issues":
        route = f"repos/{name}/issues?state=open&per_page={max(1, min(100, limit))}"
        items, _ = _api_json(route, force=force)
        return [item for item in items if "pull_request" not in item]
    if endpoint == "pulls":
        return _api_json(f"repos/{name}/pulls?state=open&per_page={max(1, min(100, limit))}", force=force)[0]
    if endpoint == "ci":
        return _api_json(f"repos/{name}/actions/runs?per_page={max(1, min(100, limit))}", force=force)[0]
    if endpoint == "releases":
        return _api_json(f"repos/{name}/releases?per_page={max(1, min(100, limit))}", force=force)[0]
    if endpoint == "branches":
        return _api_json(f"repos/{name}/branches?per_page={max(1, min(100, limit))}", force=force)[0]
    if endpoint == "tags":
        return _api_json(f"repos/{name}/tags?per_page={max(1, min(100, limit))}", force=force)[0]
    if endpoint == "commits":
        return _api_json(f"repos/{name}/commits?per_page={max(1, min(100, limit))}", force=force)[0]
    if endpoint == "activity":
        return _api_json(f"repos/{name}/events?per_page={max(1, min(100, limit))}", force=force)[0]
    if endpoint == "heatmap":
        return _api_json(f"repos/{name}/stats/commit_activity", force=force)[0]
    if endpoint == "traffic":
        # GitHub only shows the last 14 days of traffic, and only to people with push access.
        try:
            views, _ = _api_json(f"repos/{name}/traffic/views", force=force)
            clones, _ = _api_json(f"repos/{name}/traffic/clones", force=force)
        except RuntimeError as exc:
            if "403" in str(exc) or "push access" in str(exc).lower() or "must have" in str(exc).lower():
                raise RuntimeError("Traffic is visible only to people with push access") from exc
            raise
        return {"views": views, "clones": clones}
    raise RuntimeError("Unsupported repository detail")


def _human_table(items: list[dict]) -> str:
    rows = []
    for item in items:
        rows.append("{:<34} {:>4} PR {:>5} issues {:<9} {}".format(
            item.get("name", item.get("full_name", ""))[:34], item.get("openPullRequests", 0),
            item.get("openIssues", 0), item.get("ci", ""), item.get("release", "")))
    return "\n".join(rows)


def _emit(payload: object, plain: bool = False) -> None:
    if plain and isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        print(_human_table(payload))
    else:
        print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))


def _find_local_repo(identifier: str, settings: dict) -> str:
    candidate = Path(identifier).expanduser()
    if candidate.is_dir():
        return str(candidate)
    root = settings.get("localRoot", "")
    if root:
        for repo in scan_local_projects(root, int(settings.get("localDepth", 4))):
            if repo["name"] == identifier or Path(repo["path"]).name == identifier:
                return repo["path"]
    raise RuntimeError("Local checkout not found; set local-root and scan or pass its path")


def _settings_set(key: str, value: str) -> dict:
    settings = load_settings()
    normalized = key.replace("_", "-").lower()
    if normalized == "host":
        settings["host"] = value.strip().removeprefix("https://").removeprefix("http://").strip("/")
        _hostname(settings)
    elif normalized == "account":
        login, _, host = value.strip().partition("@")
        if host:
            settings["host"] = host.strip().lower()
        settings["account"] = login
        _hostname(settings)
        _account(settings)
        if login and not any(a["login"].lower() == login.lower() and a["host"] == _hostname(settings) for a in _gh_accounts()):
            raise RuntimeError(f"{login} is not signed in to {_hostname(settings)} — run `gh auth login --hostname {_hostname(settings)}`")
    elif normalized == "refresh-interval":
        value = value.lower().removesuffix("m")
        seconds = int(value) * (60 if value.isdigit() and len(value) <= 2 else 1)
        if seconds not in {60, 120, 300, 900}:
            raise RuntimeError("refresh-interval must be 1m, 2m, 5m, or 15m")
        settings["refreshInterval"] = seconds
    elif normalized == "repo-limit":
        count = int(value)
        if not 1 <= count <= 100:
            raise RuntimeError("repo-limit must be between 1 and 100")
        settings["repoLimit"] = count
    elif normalized == "menu-sort":
        if value not in {"activity", "issues", "prs", "stars", "repo", "pinned"}:
            raise RuntimeError("menu-sort must be activity, issues, prs, stars, repo, or pinned")
        settings["menuSort"] = value
    elif normalized in {"show-forks", "show-archived", "notify-ci", "notify-workflows", "show-contributions", "show-in-panel"}:
        if value.lower() not in {"true", "false"}:
            raise RuntimeError(f"{normalized} must be true or false")
        member = {"show-forks": "showForks", "show-archived": "showArchived", "notify-ci": "notifyCi",
                  "notify-workflows": "notifyWorkflows", "show-contributions": "showContributions",
                  "show-in-panel": "showInPanel"}[normalized]
        settings[member] = value.lower() == "true"
    elif normalized == "merge-window":
        minutes = int(value.lower().removesuffix("m"))
        if not 5 <= minutes <= 1440:
            raise RuntimeError("merge-window must be between 5 and 1440 minutes")
        settings["mergeWindowMinutes"] = minutes
    elif normalized == "contribution-style":
        if value not in {"squares", "dots", "fine"}:
            raise RuntimeError("contribution-style must be squares, dots, or fine")
        settings["contributionStyle"] = value
    elif normalized == "activity-scope":
        if value not in {"all", "my"}:
            raise RuntimeError("activity-scope must be all or my")
        settings["activityScope"] = value
    elif normalized == "local-root":
        root = str(Path(value).expanduser().resolve()) if value.strip() else ""
        if root and not Path(root).is_dir():
            raise RuntimeError(f"Local projects folder does not exist: {root}")
        settings["localRoot"] = root
    elif normalized == "local-depth":
        depth = int(value)
        if not 1 <= depth <= 10:
            raise RuntimeError("local-depth must be between 1 and 10")
        settings["localDepth"] = depth
    else:
        raise RuntimeError("Unknown setting key")
    save_settings(settings)
    return {"key": normalized, "value": settings.get({"refresh-interval": "refreshInterval", "repo-limit": "repoLimit",
                                                        "menu-sort": "menuSort", "show-forks": "showForks",
                                                        "show-archived": "showArchived", "activity-scope": "activityScope",
                                                        "local-root": "localRoot", "local-depth": "localDepth",
                                                        "notify-ci": "notifyCi", "notify-workflows": "notifyWorkflows",
                                                        "show-contributions": "showContributions",
                                                        "show-in-panel": "showInPanel",
                                                        "contribution-style": "contributionStyle",
                                                        "merge-window": "mergeWindowMinutes"}.get(normalized, normalized))}


def _auth_status() -> dict:
    settings = load_settings()
    host = _hostname(settings)
    chosen = _account(settings)
    accounts = _gh_accounts()
    here = [a for a in accounts if a["host"] == host]
    current = next((a for a in here if a["login"].lower() == chosen.lower()), None) if chosen else \
        next((a for a in here if a["active"]), here[0] if here else None)
    message = ""
    if not current:
        message = (f"{chosen} is not signed in to {host}. " if chosen else "") + "Run `gh auth login --hostname " + host + "`."
    return {"host": host, "authenticated": current is not None, "account": current["login"] if current else chosen,
            "followsCli": not chosen, "accounts": accounts, "message": message}


def _cache_status() -> dict:
    snapshot = {}
    try:
        snapshot = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    files = list((CACHE_DIR / "api").glob("*.json")) if (CACHE_DIR / "api").is_dir() else []
    total_bytes = sum(path.stat().st_size for path in files if path.is_file())
    return {"snapshotPath": str(CACHE), "snapshotAgeSeconds": max(0, int(time.time()) - int(snapshot.get("fetchedAt", 0))) if snapshot else None,
            "snapshotRepositories": len(snapshot.get("repos", [])), "endpointResponses": len(files),
            "endpointBytes": total_bytes}


def _clear_cache() -> dict:
    removed = 0
    for path in [CACHE, *((CACHE_DIR / "api").glob("*.json") if (CACHE_DIR / "api").is_dir() else [])]:
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return {"removedFiles": removed}


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub repository dashboard and CLI for elementary OS")
    parser.add_argument("--refresh", action="store_true", help="force a fresh GitHub snapshot")
    parser.add_argument("--max-age", type=int, default=None, help="snapshot cache lifetime in seconds")
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    parser.add_argument("--plain", action="store_true", help="emit compact plain text when supported")
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("snapshot", help="read the complete cached repository snapshot")
    repos_cmd = commands.add_parser("repos", help="list repositories by activity, work, or saved view")
    repos_cmd.add_argument("--scope", choices=["dashboard", "all", "visible", "pinned", "hidden", "work", "issues", "prs"], default="dashboard")
    repos_cmd.add_argument("--sort", choices=["activity", "issues", "prs", "stars", "repo", "pinned"], default="")
    repos_cmd.add_argument("--search", default="")
    repos_cmd.add_argument("--limit", type=int, default=-1)
    repo_cmd = commands.add_parser("repo", help="show one repository summary")
    repo_cmd.add_argument("name")
    for name in ("issues", "pulls", "ci", "releases", "activity", "commits", "branches", "tags", "heatmap", "traffic"):
        item = commands.add_parser(name, help=f"show repository {name}")
        item.add_argument("name")
        item.add_argument("--limit", type=int, default=20)
    for name, state in (("pin", "pinned"), ("unpin", "visible"), ("hide", "hidden"), ("show", "visible")):
        item = commands.add_parser(name, help=f"mark a repository {state}")
        item.add_argument("name")
    rate_cmd = commands.add_parser("rate-limits", help="show GitHub REST and GraphQL quotas")
    rate_cmd.add_argument("--refresh", action="store_true")
    cache_cmd = commands.add_parser("cache", help="inspect or clear local RepoBar cache")
    cache_cmd.add_argument("action", choices=["status", "clear"])
    settings_cmd = commands.add_parser("settings", help="show or update RepoBar preferences")
    settings_cmd.add_argument("action", choices=["show", "set"], default="show", nargs="?")
    settings_cmd.add_argument("key", nargs="?")
    settings_cmd.add_argument("value", nargs="?")
    auth_cmd = commands.add_parser("auth", help="inspect or set up GitHub CLI authentication")
    auth_cmd.add_argument("action", choices=["status", "login", "accounts", "use"], default="status", nargs="?")
    auth_cmd.add_argument("account", nargs="?", help="with `use`: LOGIN or LOGIN@HOST; empty follows the GitHub CLI's active account")
    local_cmd = commands.add_parser("local", help="scan local checkouts or explicitly fast-forward one")
    local_cmd.add_argument("action", choices=["scan", "sync", "clone"], default="scan", nargs="?")
    local_cmd.add_argument("path", nargs="?")
    local_cmd.add_argument("--root", default="")
    local_cmd.add_argument("--depth", type=int, default=0)
    local_cmd.add_argument("--yes", action="store_true", help="confirm an explicit clean fast-forward sync")
    open_cmd = commands.add_parser("open", help="open a repository or URL in the default browser")
    open_cmd.add_argument("target")
    args = parser.parse_args()
    max_age = args.max_age if args.max_age is not None else int(load_settings().get("refreshInterval", CACHE_TTL_SECONDS))

    try:
        if args.command in {None, "snapshot", "refresh"}:
            _emit(get_snapshot(force=args.refresh or args.command == "refresh", max_age=max_age), args.plain)
        elif args.command == "repos":
            snapshot = get_snapshot(force=args.refresh, max_age=max_age)
            items = filter_repositories(snapshot, args.scope, args.search, args.sort, args.limit)
            _emit(items, args.plain)
        elif args.command == "repo":
            full_name = _safe_repo_name(args.name)
            snapshot = get_snapshot(force=args.refresh, max_age=max_age)
            match = next((item for item in snapshot.get("repos", []) if item.get("name") == full_name), None)
            if not match:
                raise RuntimeError("Repository is not visible to the active GitHub account")
            _emit(match, args.plain)
        elif args.command in {"issues", "pulls", "ci", "releases", "activity", "commits", "branches", "tags", "heatmap", "traffic"}:
            _emit(_repo_details(args.name, args.command, args.limit, args.refresh), args.plain)
        elif args.command in {"pin", "unpin", "hide", "show"}:
            _emit(set_repo_state(args.name, {"pin": "pinned", "unpin": "visible", "hide": "hidden", "show": "visible"}[args.command]))
        elif args.command == "rate-limits":
            _emit(_api_json("rate_limit", force=args.refresh)[0])
        elif args.command == "cache":
            _emit(_cache_status() if args.action == "status" else _clear_cache())
        elif args.command == "settings":
            if args.action == "set":
                if not args.key or args.value is None:
                    raise RuntimeError("Use `settings set KEY VALUE`")
                _emit(_settings_set(args.key, args.value))
            else:
                _emit(load_settings())
        elif args.command == "auth":
            if args.action == "login":
                subprocess.run(["gh", "auth", "login", "--hostname", _hostname()], check=True)
            elif args.action == "accounts":
                _emit({"accounts": _gh_accounts(), "host": _hostname(), "account": _account()})
                return 0
            elif args.action == "use":
                if args.account is None:
                    raise RuntimeError("Use `auth use LOGIN[@HOST]` (or an empty name to follow the GitHub CLI)")
                _settings_set("account", args.account)
            _emit(_auth_status())
        elif args.command == "local":
            settings = load_settings()
            if args.action == "clone":
                if not args.path:
                    raise RuntimeError("Use `local clone OWNER/NAME`")
                _emit(clone_local_repo(args.path, settings))
            elif args.action == "sync":
                if not args.path:
                    raise RuntimeError("Use `local sync PATH_OR_REPO [--yes]`")
                _emit(sync_local_repo(_find_local_repo(args.path, settings), args.yes))
            else:
                root = args.root or settings.get("localRoot", "")
                if not root:
                    raise RuntimeError("Choose a project folder with `settings set local-root PATH`")
                depth = args.depth or int(settings.get("localDepth", 4))
                _emit({"root": str(Path(root).expanduser().resolve()), "repos": scan_local_projects(root, depth)})
        elif args.command == "open":
            target = args.target
            if REPO_RE.fullmatch(target):
                target = f"https://{_hostname()}/{target}"
            subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _emit({"opened": target})
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        if args.json:
            _emit({"error": str(exc)})
        else:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
