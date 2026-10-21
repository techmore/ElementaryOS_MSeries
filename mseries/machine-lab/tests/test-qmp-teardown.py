#!/usr/bin/env python3
"""Bound the QMP fixture's parent exit AND captured-output EOF; no VM is used."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

binary, fixture = [str(Path(value).resolve()) for value in sys.argv[1:3]]
for iteration in range(20):
    with tempfile.TemporaryDirectory(prefix="ml-qmp-teardown-") as scratch:
        env = dict(os.environ, TMPDIR=scratch, FAKE_QMP=fixture)
        # The process group belongs only to this test binary and its fake peers.
        child = subprocess.Popen([binary, "-p", "/qmp/transport"], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=True)
        try:
            try:
                output, diagnostic = child.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                status = child.poll()
                os.killpg(child.pid, signal.SIGKILL)
                output, diagnostic = child.communicate(timeout=5)
                raise AssertionError(f"QMP fixture {iteration}: no output EOF; parent status={status}; "
                                     f"stdout={output!r}; stderr={diagnostic!r}") from None
            assert child.returncode == 0, (iteration, output, diagnostic)
            assert b"ok 1 /qmp/transport" in output, (iteration, output, diagnostic)
        finally:
            # Also clean owned peers if an assertion or early test exit failed.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=5)
print("PASS: 20 QMP fixture exits, reaping and captured-output EOF within 10 seconds each")
