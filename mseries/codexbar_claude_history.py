"""Local Claude Code history across desktop sign-ins.

Desktop's sidebar entries are account/org scoped, but its Code transcripts live in
~/.claude/projects. Export the departing account and register only missing entries
for the destination. Chat/Cowork/cloud histories and authentication are not handled
here. Call export/import only after the desktop app has fully exited.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,127}\Z")
SESSION_ID = re.compile(r"local_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\Z")
CLI_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
MAX_ENTRY_BYTES = 10 * 1024 * 1024  # same bound as the inspected desktop session loader
# Conversation/workspace fields only. Permission grants, connector settings, account
# bindings, pending actions and process/remote-control state must be initialized anew.
FIELDS = {
    "sessionId", "cliSessionId", "cwd", "originCwd", "title", "titleSource", "createdAt",
    "lastActivityAt", "lastFocusedAt", "model", "effort", "isArchived", "gitAnchors",
    "worktreePath", "worktreeName", "folderWorktrees", "worktreePinned", "sourceBranch",
    "branch", "completedTurns", "lastAssistantUuid",
}


class HistoryError(ValueError):
    """A local history export/import could not be completed."""


def child_dir(base: pathlib.Path, name: str, create: bool = False) -> pathlib.Path:
    if not SEGMENT.fullmatch(name):
        raise HistoryError("Invalid history directory identifier.")
    path = base / name
    if path.is_symlink():
        raise HistoryError("History directories must not be symbolic links.")
    if create:
        path.mkdir(mode=0o700, parents=False, exist_ok=True)
    return path


def read_entry(path: pathlib.Path) -> dict[str, Any]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ENTRY_BYTES:
                return {}
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def entries(directory: pathlib.Path) -> list[tuple[pathlib.Path, dict[str, Any]]]:
    if directory.is_symlink():
        raise HistoryError("History directories must not be symbolic links.")
    result = []
    for path in sorted(directory.glob("local_*.json")):
        if not SESSION_ID.fullmatch(path.stem):
            continue
        data = read_entry(path)
        if data.get("sessionId") == path.stem:
            result.append((path, data))
    return result


def organizations(root: pathlib.Path, account: str) -> list[pathlib.Path]:
    directory = child_dir(root, account)
    if not directory.is_dir():
        return []
    return [child_dir(directory, path.name) for path in sorted(directory.iterdir())
            if SEGMENT.fullmatch(path.name) and path.is_dir()]


def safe_record(data: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    sid = data.get("sessionId")
    cli = data.get("cliSessionId")
    cwd = data.get("cwd")
    if not isinstance(sid, str) or not SESSION_ID.fullmatch(sid) or not isinstance(cli, str) or not CLI_ID.fullmatch(cli):
        return None
    if not isinstance(cwd, str) or not pathlib.Path(cwd).is_absolute() or not pathlib.Path(cwd).is_dir():
        return None
    if any(data.get(key) for key in ("sshConfig", "wslConfig", "cloudSessionId", "movedToCloud", "stagedTranscriptPath")):
        return None  # those histories require different transport/import machinery
    record = {k: v for k, v in data.items() if k in FIELDS}
    record.update(permissionMode="default", sessionPermissionUpdates=[], alwaysAllowedReasons=[])
    return record


@dataclass
class TransferPlan:
    source: str
    target: str
    organization: str
    app_root: pathlib.Path
    projects: pathlib.Path
    sessions: list[dict[str, Any]] = field(default_factory=list)
    unavailable: int = 0
    existing: int = 0

    def summary(self) -> dict[str, int]:
        return {"exportable": len(self.sessions), "missing": len(self.sessions) - self.existing,
                "existing": self.existing, "unavailable": self.unavailable}


def plan_transfer(app_root: pathlib.Path, projects: pathlib.Path, source: str,
                  target: str, organization: str = "") -> TransferPlan:
    root = app_root / "claude-code-sessions"
    if root.is_symlink():
        raise HistoryError("History directories must not be symbolic links.")
    source_dirs = organizations(root, source)
    target_dirs = organizations(root, target)
    if organization:
        child_dir(root, organization)  # validate only; this path isn't created
    elif len(target_dirs) == 1:
        organization = target_dirs[0].name
    plan = TransferPlan(source, target, organization, app_root, projects)
    raw = [item for directory in source_dirs for item in entries(directory)]
    if not raw:
        return plan
    if not organization:
        raise HistoryError("Claude's destination organization is unknown. Sign in to that account once in the app and save it before carrying history.")
    destination = child_dir(root / target, organization)
    present = entries(destination)
    known_sessions = {d["sessionId"] for _, d in present}
    known_cli = {d.get("cliSessionId") for _, d in present}
    transcripts: dict[str, list[pathlib.Path]] = {}
    if projects.is_dir():
        for directory in projects.iterdir():
            if directory.is_dir() and not directory.is_symlink():
                for path in directory.glob("*.jsonl"):
                    if CLI_ID.fullmatch(path.stem) and not path.is_symlink():
                        transcripts.setdefault(path.stem, []).append(path)
    seen = set()
    seen_cli = set()
    # Newest source entry wins only within this export. Destination entries are never replaced.
    for path, data in sorted(raw, key=lambda item: item[0].stat().st_mtime_ns, reverse=True):
        record = safe_record(data)
        if record is None:
            plan.unavailable += 1
            continue
        if record["sessionId"] in seen or record["cliSessionId"] in seen_cli:
            continue
        seen.add(record["sessionId"])
        seen_cli.add(record["cliSessionId"])
        paths = transcripts.get(record["cliSessionId"], [])
        if len(paths) > 1:
            slug = re.sub(r"[^A-Za-z0-9]", "-", record["cwd"])
            paths = [p for p in paths if p.parent.name == slug]
        if len(paths) != 1 or paths[0].stat().st_size == 0:
            plan.unavailable += 1
            continue
        exists = record["sessionId"] in known_sessions or record["cliSessionId"] in known_cli
        # Even unreadable or symlinked destination names must never be overwritten.
        exists = exists or os.path.lexists(destination / path.name)
        plan.existing += int(exists)
        plan.sessions.append({"record": record, "transcript": paths[0], "existing": exists})
    return plan


def create_private(path: pathlib.Path, data: bytes) -> bool:
    """Publish a complete file without ever replacing an existing destination."""
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".history-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
            return True
        except FileExistsError:
            return False
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)


def export_history(plan: TransferPlan, store: pathlib.Path) -> pathlib.Path | None:
    """Private content-addressed transcript backup plus a manifest of resumable records."""
    if not plan.sessions:
        return None
    if store.is_symlink():
        raise HistoryError("The history archive must not be a symbolic link.")
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    store.chmod(0o700)
    blobs = child_dir(store, "transcripts", True)
    snapshot = child_dir(store, f"export-{time.time_ns()}-{uuid.uuid4().hex}", True)
    manifest: dict[str, Any] = {"schemaVersion": 1, "source": plan.source, "target": plan.target,
                              "organization": plan.organization, "sessions": []}
    for item in plan.sessions:
        source = item["transcript"]
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise HistoryError("A Code transcript is no longer a regular file.")
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
            destination = blobs / (digest + ".jsonl")
            if os.path.lexists(destination):
                cached_fd = os.open(destination, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(cached_fd, "rb") as cached:
                    if hashlib.file_digest(cached, "sha256").hexdigest() != digest:
                        raise HistoryError("An existing Code history backup is damaged; no account was changed.")
                content = None
            else:
                handle.seek(0)
                content = handle.read()
                if hashlib.sha256(content).hexdigest() != digest:
                    raise HistoryError("A Code transcript changed while exporting. Finish running work and retry.")
            after = os.fstat(handle.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise HistoryError("A Code transcript changed while exporting. Finish running work and retry.")
            if content is not None:
                create_private(destination, content)
        manifest["sessions"].append({"record": item["record"], "relativeTranscript": str(source.relative_to(plan.projects)),
                                     "sha256": digest, "bytes": before.st_size})
    create_private(snapshot / "manifest.json", json.dumps(manifest).encode())
    return snapshot


def import_missing(plan: TransferPlan, snapshot: pathlib.Path | None) -> dict[str, int]:
    """Add missing entries after sign-in changes and before app launch. Never replace a destination record."""
    report = {"imported": 0, "existing": 0, "unavailable": plan.unavailable}
    if snapshot is None:
        return report
    manifest = read_entry(snapshot / "manifest.json")
    if (manifest.get("schemaVersion"), manifest.get("source"), manifest.get("target"), manifest.get("organization")) != (
            1, plan.source, plan.target, plan.organization):
        raise HistoryError("The Code history export is invalid.")
    sessions = manifest.get("sessions")
    if not isinstance(sessions, list) or any(not isinstance(item, dict) for item in sessions):
        raise HistoryError("The Code history export has invalid session entries.")
    root = plan.app_root / "claude-code-sessions"
    if root.is_symlink():
        raise HistoryError("History directories must not be symbolic links.")
    account = child_dir(root, plan.target, True)
    destination = child_dir(account, plan.organization, True)
    present = entries(destination)
    known_sessions = {d["sessionId"] for _, d in present}
    known_cli = {d.get("cliSessionId") for _, d in present}
    created = []
    try:
        for item in sessions:
            record = safe_record(item.get("record"))
            if record is None:
                report["unavailable"] += 1
                continue
            if record["sessionId"] in known_sessions or record["cliSessionId"] in known_cli:
                report["existing"] += 1
                continue
            target = destination / (record["sessionId"] + ".json")
            if os.path.lexists(target):
                report["existing"] += 1
                continue
            digest = item.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise HistoryError("Invalid transcript checksum in the export.")
            blob = snapshot.parent / "transcripts" / (digest + ".jsonl")
            fd = os.open(blob, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as handle:
                content = handle.read()
            if hashlib.sha256(content).hexdigest() != digest:
                raise HistoryError("The exported transcript checksum did not match.")
            relative_value = item.get("relativeTranscript")
            if not isinstance(relative_value, str):
                raise HistoryError("Invalid transcript location in the export.")
            relative = pathlib.Path(relative_value)
            if len(relative.parts) != 2 or relative.is_absolute() or ".." in relative.parts or relative.name != record["cliSessionId"] + ".jsonl":
                raise HistoryError("Invalid transcript location in the export.")
            # Restore a transcript only if the app removed it during sign-out. Existing
            # transcripts may contain newer turns, so never replace them from a backup.
            project = plan.projects / relative.parts[0]
            if project.is_symlink():
                raise HistoryError("Transcript directories must not be symbolic links.")
            project.mkdir(mode=0o700, parents=False, exist_ok=True)
            transcript = project / relative.name
            if not os.path.lexists(transcript):
                create_private(transcript, content)
            if create_private(target, json.dumps(record).encode()):
                created.append(target)
                known_sessions.add(record["sessionId"])
                known_cli.add(record["cliSessionId"])
                report["imported"] += 1
            else:
                report["existing"] += 1
        return report
    except BaseException:
        # Undo only the index entries this operation created. Exports and any restored
        # transcript remain as recoverable data; originals and existing entries are untouched.
        for path in created:
            path.unlink(missing_ok=True)
        raise
