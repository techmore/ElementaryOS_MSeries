"""Podman client checks: only a fixture binary is executed; no real container is touched."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

fake = str(Path(__file__).with_name("fake-podman.py"))
with tempfile.TemporaryDirectory(prefix="orchard-podman-") as directory:
    log = Path(directory) / "calls.log"
    log.touch()
    env = {**os.environ, "ORCHARD_PODMAN": fake, "FAKE_PODMAN_LOG": str(log)}
    result = subprocess.run(sys.argv[1:], env=env, timeout=20)
    assert result.returncode == 0, result.returncode
    calls = log.read_text().splitlines()
    for expected in ("restart web", "rm db", "rmi 1111", "volume rm data", "volume rm busy"):
        assert expected in calls, (expected, calls)
    # Removal is never forced and unknown verbs never reach podman.
    assert not any("--force" in c or "-f" in c.split() or c.startswith("kill") for c in calls), calls
