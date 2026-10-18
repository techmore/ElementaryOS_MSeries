#!/usr/bin/env python3
"""Pass the signed-in OpenCode Go API key to CodexBar without copying it."""

import json
from contextlib import closing
import os
import pathlib
import sqlite3
import sys
import time


def selected_provider(arguments: list[str]) -> str | None:
    for index, argument in enumerate(arguments):
        if argument == "--provider" and index + 1 < len(arguments):
            return arguments[index + 1]
        if argument.startswith("--provider="):
            return argument.partition("=")[2]
    return None


def opencode_go_key() -> str | None:
    data_home = os.environ.get("XDG_DATA_HOME")
    data_dir = (
        pathlib.Path(data_home)
        if data_home and pathlib.Path(data_home).is_absolute()
        else pathlib.Path.home() / ".local/share"
    )
    # OpenCode v2's browser sign-in uses the credential table rather than auth.json.
    # Prefer its active account so auth switch also changes CodexBar; legacy keys are a fallback.
    # Read only; refreshing/rotating credentials remains OpenCode's responsibility.
    try:
        with closing(sqlite3.connect((data_dir / "opencode/opencode.db").as_uri() + "?mode=ro", uri=True,
                                    timeout=1)) as db:
            rows = db.execute("SELECT value FROM credential WHERE integration_id='opencode' AND active=1 "
                              "ORDER BY time_updated DESC")
            for (value,) in rows:
                try:
                    credential = json.loads(value)
                    if not isinstance(credential, dict) or credential.get("type") != "oauth":
                        continue
                    access, expires = credential.get("access"), credential.get("expires")
                    if isinstance(expires, bool) or not isinstance(expires, (int, float)):
                        continue
                    refreshable = isinstance(credential.get("refresh"), str) and bool(credential["refresh"])
                    if isinstance(access, str) and access.strip() and (expires > (time.time() + 60) * 1000 or refreshable):
                        # Keep the selected identity while OpenCode refreshes it; never use a legacy account instead.
                        return access.strip()
                except (TypeError, ValueError):
                    continue
    except (OSError, sqlite3.Error):
        pass
    auth_file = data_dir / "opencode" / "auth.json"
    try:
        credentials = json.loads(auth_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        credentials = {}
    entry = credentials.get("opencode-go") if isinstance(credentials, dict) else None
    key = entry.get("key") if isinstance(entry, dict) else None
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def main(arguments: list[str]) -> None:
    if arguments and arguments[0] == "usage" and not os.environ.get("OPENCODE_API_KEY"):
        provider = selected_provider(arguments)
        if provider in {"opencodego", "all"}:
            api_key = opencode_go_key()
            if api_key:
                os.environ["OPENCODE_API_KEY"] = api_key

    cli = pathlib.Path.home() / ".local/lib/codexbar-cli/codexbar-upstream"
    if not cli.exists():
        print(f"codexbar: upstream CLI missing at {cli}; rerun mseries/install-codexbar.sh", file=sys.stderr)
        raise SystemExit(127)
    os.execvpe(str(cli), [str(cli), *arguments], os.environ)


if __name__ == "__main__":
    main(sys.argv[1:])
