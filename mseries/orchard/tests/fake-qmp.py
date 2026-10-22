#!/usr/bin/env python3
"""A tiny QMP server for tests: argv[1] = socket path, argv[2] = file that receives the connection count."""
import json, os, socket, sys, threading

path, counter = sys.argv[1], sys.argv[2]
if os.path.exists(path):
    os.unlink(path)
srv = socket.socket(socket.AF_UNIX)
srv.bind(path)
srv.listen(8)
connections = 0
lock = threading.Lock()

def serve(conn):
    f = conn.makefile("rw")
    f.write(json.dumps({"QMP": {"version": {}, "capabilities": []}}) + "\n"); f.flush()
    for line in f:
        try:
            cmd = json.loads(line)["execute"]
        except Exception:
            break
        if cmd == "query-status":
            reply = {"return": {"status": "paused", "running": False}}
        else:
            reply = {"return": {}}
        if cmd != "qmp_capabilities":
            # an event before the return value must be skipped by the client
            f.write(json.dumps({"event": "RESUME"}) + "\n")
        f.write(json.dumps(reply) + "\n"); f.flush()
    conn.close()

while True:
    conn, _ = srv.accept()
    with lock:
        connections += 1
        with open(counter, "w") as c:
            c.write(str(connections))
    threading.Thread(target=serve, args=(conn,), daemon=True).start()
