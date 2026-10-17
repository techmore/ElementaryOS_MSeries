#!/usr/bin/env python3
"""Pass the signed-in OpenCode Go API key to CodexBar without copying it."""

import json
import os
import pathlib
import sys


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
    auth_file = data_dir / "opencode" / "auth.json"
    try:
        credentials = json.loads(auth_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(credentials, dict):
        return None
    entry = credentials.get("opencode-go")
    if not isinstance(entry, dict):
        return None
    key = entry.get("key")
    return key.strip() if isinstance(key, str) and key.strip() else None


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
