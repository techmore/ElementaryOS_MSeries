"""Small on-disk cache shared by the M-series CodexBar helpers.

One JSON file per name under ~/.cache/codexbar-mseries (private to the user). It lets a panel restart or a
deploy reuse recent provider answers instead of fetching everything again, and it carries the failure count so
a provider that keeps failing is retried on a growing delay instead of on every timer tick.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import pathlib
import tempfile
import time
from typing import Any, Iterator

MAX_BACKOFF_SECONDS = 3600
BASE_BACKOFF_SECONDS = 60


def cache_dir() -> pathlib.Path:
    configured = os.environ.get("XDG_CACHE_HOME")
    base = pathlib.Path(configured) if configured and pathlib.Path(configured).is_absolute() else pathlib.Path.home() / ".cache"
    return base / "codexbar-mseries"


def private_dir(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def load(name: str) -> dict[str, Any]:
    try:
        data = json.loads((cache_dir() / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def store(name: str, data: dict[str, Any]) -> None:
    """Atomic and 0600; a cache that cannot be written must never break the helper."""
    try:
        directory = private_dir(cache_dir())
        descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=f".{name}-")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, separators=(",", ":"))
            os.chmod(temporary, 0o600)
            os.replace(temporary, directory / f"{name}.json")
        except BaseException:
            pathlib.Path(temporary).unlink(missing_ok=True)
            raise
    except OSError:
        pass


@contextlib.contextmanager
def locked(path: pathlib.Path, timeout: float = 10.0) -> Iterator[None]:
    """Exclusive advisory lock on a sibling .lock file, so two helpers never rewrite the same credentials at once."""
    private_dir(path.parent)
    descriptor = os.open(path.with_name(path.name + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"{path.name} is busy")
                time.sleep(0.05)
        yield
    finally:
        os.close(descriptor)  # closing drops the lock


def backoff_seconds(failures: int) -> int:
    if failures <= 0:
        return 0
    return min(BASE_BACKOFF_SECONDS * 2 ** (failures - 1), MAX_BACKOFF_SECONDS)


def is_fresh(entry: dict[str, Any] | None, ttl: float, now: float) -> bool:
    """A good answer younger than ttl. A clock that moved backwards counts as stale."""
    if not entry or "data" not in entry or entry.get("failures", 0):
        return False
    fetched = entry.get("fetchedAt")
    return isinstance(fetched, (int, float)) and 0 <= now - fetched < ttl


def in_backoff(entry: dict[str, Any] | None, now: float) -> bool:
    retry = (entry or {}).get("retryAt")
    return isinstance(retry, (int, float)) and now < retry <= now + MAX_BACKOFF_SECONDS


def succeeded(data: Any, now: float) -> dict[str, Any]:
    return {"fetchedAt": now, "failures": 0, "data": data}


def failed(previous: dict[str, Any] | None, now: float) -> dict[str, Any]:
    """Keep the last good answer, count the failure and schedule the next allowed attempt."""
    failures = int((previous or {}).get("failures", 0)) + 1
    entry = dict(previous or {})
    entry.update(failures=failures, retryAt=now + backoff_seconds(failures))
    return entry
