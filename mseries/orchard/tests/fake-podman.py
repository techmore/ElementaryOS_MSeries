#!/usr/bin/env python3
"""Fixture standing in for the podman binary; records every call in $FAKE_PODMAN_LOG."""
import json
import os
import sys
import time

args = sys.argv[1:]
with open(os.environ["FAKE_PODMAN_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")

CONTAINERS = [
    {"Id": "a" * 64, "Names": ["web"], "Image": "nginx", "State": "running", "Status": "Up 2 hours", "Ports": None},
    {"Id": "b" * 64, "Names": ["db"], "Image": "postgres", "State": "exited", "Status": "Exited (0)", "Ports": None},
    {"Id": "c" * 64, "Names": None, "Image": "alpine", "State": "running", "Status": "Up", "Ports": None},
]
IMAGES = [{"Id": "1" * 64, "Names": ["localhost/app:1"], "Size": 1, "Containers": 1}, {"Id": "2" * 64, "Names": None, "Size": 2, "Containers": 0}]
VOLUMES = [{"Name": "data", "Driver": "local", "Mountpoint": "/v/data/_data"}]

STATS = [{"id": "a" * 12, "name": "web", "cpu_percent": "1.50%", "mem_usage": "12.5MB / 1GB", "mem_percent": "1.25%", "net_io": "1kB / 2kB", "block_io": "0B / 0B", "pids": "3"}]
INSPECT = [{"Id": "a" * 64, "Name": "web", "ImageName": "docker.io/library/nginx:1", "Image": "9" * 64, "Created": "2026-01-01T00:00:00Z",
            "State": {"Status": "running", "StartedAt": "2026-01-01T00:00:01Z", "FinishedAt": "0001-01-01T00:00:00Z", "ExitCode": 0, "Pid": 42},
            "Config": {"Entrypoint": ["nginx"], "Cmd": ["-g", "daemon off;"], "Env": ["A=1", "B=2"]},
            "HostConfig": {"Memory": 0, "NanoCpus": 0, "RestartPolicy": {"Name": "no"}},
            "Mounts": [{"Type": "volume", "Name": "data", "Source": "/v/data/_data", "Destination": "/data", "RW": True},
                       {"Type": "bind", "Source": "/srv/site", "Destination": "/usr/share/nginx/html", "RW": False}],
            "NetworkSettings": {"IPAddress": "", "Ports": {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8080"}]}, "Networks": {"podman": {"IPAddress": "10.88.0.2"}}}}]

if args[:3] == ["ps", "-a", "--format"]:
    print(json.dumps(CONTAINERS))
elif args[:2] == ["images", "--format"]:
    print(json.dumps(IMAGES))
elif args[:3] == ["volume", "ls", "--format"]:
    print(json.dumps(VOLUMES))
elif args[:4] == ["stats", "--no-stream", "--format", "json"]:
    print(json.dumps(STATS))
elif args[:4] == ["inspect", "--type", "container", "--format"] and args[5] == "a" * 64:
    print(json.dumps(INSPECT))
elif args[:4] == ["inspect", "--type", "container", "--format"]:
    sys.stderr.write("no such container\n")
    sys.exit(125)
elif args[:2] == ["volume", "rm"] and args[2] == "busy":
    sys.stderr.write("volume busy is in use by a container\n")
    sys.exit(125)
elif args and args[0] in ("start", "stop", "restart", "pause", "unpause", "rm", "rmi", "volume"):
    pass
elif args == ["hang"]:
    time.sleep(30)
else:
    sys.stderr.write("unexpected: " + " ".join(args) + "\n")
    sys.exit(2)
