#!/usr/bin/env python3
"""Render a synthetic T3 repo chat row against a different live Git checkout branch."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
EXPECTED_CONTEXT = "T3 branch feature/t3-saved · checkout now live-checkout"
REPOSITORY_COUNT = 10


def websocket_frame(opcode: int, payload: bytes = b"") -> bytes:
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65_536:
        header.append(126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", length))
    return bytes(header) + payload


def read_exact(stream, size: int) -> bytes:
    parts = bytearray()
    while len(parts) < size:
        chunk = stream.read(size - len(parts))
        if not chunk:
            raise EOFError
        parts.extend(chunk)
    return bytes(parts)


def read_client_frame(stream) -> tuple[int, bytes]:
    first, second = read_exact(stream, 2)
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", read_exact(stream, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", read_exact(stream, 8))[0]
    mask = read_exact(stream, 4) if second & 0x80 else b""
    payload = read_exact(stream, length)
    if mask:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return opcode, payload


def fixture_snapshot(root: Path) -> dict:
    checkout = str(root / "checkout-0")
    return {
        "projects": [
            {"project": {"id": "fixture-project", "title": "Fixture repository", "workspaceRoot": checkout}}
        ],
        "threads": [
            {
                "thread": {
                    "id": "fixture-thread",
                    "projectId": "fixture-project",
                    "title": "Synthetic review thread with a long title for row wrapping",
                    "providerInstanceId": "codex",
                    "modelSelection": {"model": "gpt-5.6-sol"},
                    "runtimeMode": "approval-required",
                    "createdAt": "2026-10-22T00:00:00Z",
                    "updatedAt": "2026-10-23T00:00:00Z",
                    "status": "completed",
                    "branch": "feature/t3-saved",
                }
            }
        ],
    }


class FakeT3Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "T3Fixture/1"

    @property
    def fixture_root(self) -> Path:
        return self.server.fixture_root  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        if self.path != "/api/auth/websocket-ticket":
            self.send_error(404)
            return
        body = b'{"ticket":"fixture-ticket"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self) -> None:
        if not self.path.startswith("/ws?") or self.headers.get("Upgrade", "").lower() != "websocket":
            self.send_error(404)
            return
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(400)
            return
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        self.send_response_only(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.wfile.flush()
        self.close_connection = True
        self.serve_rpc()

    def serve_rpc(self) -> None:
        while True:
            try:
                opcode, payload = read_client_frame(self.rfile)
                if opcode == 8:
                    self.wfile.write(websocket_frame(8, payload))
                    self.wfile.flush()
                    return
                if opcode == 9:
                    self.wfile.write(websocket_frame(10, payload))
                    self.wfile.flush()
                    continue
                if opcode != 1:
                    continue
                request = json.loads(payload)
                if request.get("_tag") != "Request":
                    continue
                tag, request_id = request.get("tag"), request.get("id")
                if tag == "server.getConfig":
                    reply = {
                        "_tag": "Exit",
                        "requestId": request_id,
                        "exit": {"_tag": "Success", "value": {"cwd": str(self.fixture_root), "providers": []}},
                    }
                elif tag == "orchestration.subscribeShell":
                    reply = {
                        "_tag": "Chunk",
                        "requestId": request_id,
                        "values": [{"kind": "snapshot", "snapshot": fixture_snapshot(self.fixture_root)}],
                    }
                else:
                    reply = {
                        "_tag": "Exit",
                        "requestId": request_id,
                        "exit": {"_tag": "Success", "value": {}},
                    }
                self.wfile.write(websocket_frame(1, json.dumps(reply).encode()))
                self.wfile.flush()
            except (EOFError, OSError, ValueError, json.JSONDecodeError):
                return


def write_executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(0o755)


def make_fixture(root: Path) -> tuple[ThreadingHTTPServer, str]:
    home = root / "home"
    config = root / "config" / "claude-pantheon-rs"
    cache = root / "cache"
    bin_dir = root / "bin"
    for directory in (home, config, cache, bin_dir):
        directory.mkdir(parents=True, exist_ok=True)

    repos = []
    for index in range(REPOSITORY_COUNT):
        checkout = root / f"checkout-{index}"
        checkout.mkdir()
        if index == 0:
            subprocess.run(["git", "init", "--quiet", "--initial-branch=live-checkout"], cwd=checkout, check=True)
            subprocess.run(
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/layout-owner/repository-with-a-long-name-0.git",
                ],
                cwd=checkout,
                check=True,
            )
        repos.append(
            {"repo": f"layout-owner/repository-with-a-long-name-{index}", "path": str(checkout)}
        )

    (config / "workflow.json").write_text(json.dumps({"repos": repos}))
    write_executable(bin_dir / "gh", "#!/bin/sh\nprintf '[]\\n'\n")
    write_executable(bin_dir / "secret-tool", "#!/bin/sh\nexit 1\n")

    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeT3Handler)
    server.daemon_threads = True
    server.fixture_root = root  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    server_url = f"http://127.0.0.1:{server.server_address[1]}"
    slug = "".join(character if character.isascii() and character.isalnum() else "-" for character in server_url)
    slug = slug.strip("-")
    (config / "environments.json").write_text(
        json.dumps(
            {
                "current": "fixture",
                "list": [
                    {"id": "fixture", "name": "Temporary T3 fixture", "route": {"kind": "direct", "url": server_url}}
                ],
            }
        )
    )
    (config / f"credentials-{slug}.json").write_text(
        json.dumps(
            {
                "server": server_url,
                "access_token": "fixture-token",
                "label": "Temporary T3 fixture",
                "environment_id": "fixture-environment",
            }
        )
    )
    return server, server_url


def main() -> None:
    host_home = Path.home()
    with tempfile.TemporaryDirectory(prefix="t3r-branch-row-") as temp:
        root = Path(temp)
        server, server_url = make_fixture(root)

        env = os.environ.copy()
        env.setdefault("RUSTUP_HOME", str(host_home / ".rustup"))
        env.setdefault("CARGO_HOME", str(host_home / ".cargo"))
        env.update(
            {
                "HOME": str(root / "home"),
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_CACHE_HOME": str(root / "cache"),
                "PATH": str(root / "bin") + os.pathsep + env.get("PATH", "/usr/bin:/bin"),
                "GSETTINGS_BACKEND": "memory",
                "GSK_RENDERER": "cairo",
                "CLAUDE_PANTHEON_REPOS_LAYOUT_ONLY": "1",
                "CLAUDE_PANTHEON_EXPECT_REPO_THREAD_CONTEXT": EXPECTED_CONTEXT,
            }
        )
        env.pop("CLAUDE_PANTHEON_DARK", None)
        crate = Path(__file__).resolve().parents[1]
        repo = crate.parents[1]
        command = [
            "dbus-run-session",
            "--",
            "env",
            "-u",
            "WAYLAND_DISPLAY",
            "GDK_BACKEND=x11",
            "GSETTINGS_BACKEND=memory",
            "GSK_RENDERER=cairo",
            "xvfb-run",
            "-a",
            "-s",
            "-screen 0 1024x768x24",
            "cargo",
            "test",
            "--release",
            "--manifest-path",
            str(crate / "Cargo.toml"),
            "--test",
            "render",
        ]
        try:
            for theme in ("light", "dark"):
                screenshot = root / f"repo-thread-{theme}.png"
                env["CLAUDE_PANTHEON_SHOT_REPOS_LAYOUT"] = str(screenshot)
                if theme == "dark":
                    env["CLAUDE_PANTHEON_DARK"] = "1"
                else:
                    env.pop("CLAUDE_PANTHEON_DARK", None)
                subprocess.run(command, cwd=repo, env=env, check=True)
                print(f"PASS: {theme} repo thread render against {server_url} ({screenshot.name})")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
