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

if args[:3] == ["ps", "-a", "--format"]:
    print(json.dumps(CONTAINERS))
elif args[:2] == ["images", "--format"]:
    print(json.dumps(IMAGES))
elif args[:3] == ["volume", "ls", "--format"]:
    print(json.dumps(VOLUMES))
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
