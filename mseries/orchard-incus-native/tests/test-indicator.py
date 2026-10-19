"""Exercise the real panel module against a disposable, read-only Incus fixture."""
import http.server
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading

if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    print("SKIP: GTK widget checks require a display (or xvfb-run).")
    sys.exit(77)

responses = [
    {"type": "sync", "metadata": [
        {"name": "web", "type": "container", "status": "Running"},
        {"name": "vm", "type": "virtual-machine", "status": "Running"},
        {"name": "stopped", "status": "Stopped"},
    ]},
    {"type": "sync", "metadata": []},
    {"type": "sync", "metadata": [{"name": "stopped", "status": "Stopped"}]},
    {"type": "error", "error": "Fixture daemon unavailable"},
    {"type": "sync", "metadata": [{"name": "recovered", "status": "Running"}]},
]


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        assert self.path == "/1.0/instances?recursion=2", self.path
        assert responses, "Unexpected extra request"
        body = json.dumps(responses.pop(0)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


with tempfile.TemporaryDirectory(prefix="orchard-test-") as directory:
    socket_path = str(Path(directory) / "incus.socket")
    with socketserver.UnixStreamServer(socket_path, Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        result = subprocess.run(
            sys.argv[1:], env={**os.environ, "INCUS_SOCKET": socket_path}, timeout=18
        )
        server.shutdown()
        if result.returncode == 0:
            assert not responses, "Not all fixture states were checked"
        sys.exit(result.returncode)
