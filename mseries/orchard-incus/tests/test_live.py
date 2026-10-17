"""Opt-in tests against a real Incus: ORCHARD_LIVE=1 python3 -m unittest tests.test_live -v

They create throwaway instances named oi-live-* (alpine, cached after the first run) and delete them again. They replay
the real problems found while building the app: stopping right after launch hangs, and a cancelled launch still
finishes server-side."""
import json
import os
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from orchard_incus import backend as b  # noqa: E402

LIVE = os.environ.get("ORCHARD_LIVE") == "1"
IMG = "images:alpine/edge"


def names():
    return {i["name"] for i in b.ijson("list")}


def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


@unittest.skipUnless(LIVE, "set ORCHARD_LIVE=1 to run against a real Incus")
class Live(unittest.TestCase):
    def setUp(self):
        self.name = f"oi-live-{os.getpid() % 10000}"
        subprocess.run(["incus", "delete", "-f", self.name], capture_output=True)

    def tearDown(self):
        subprocess.run(["incus", "delete", "-f", self.name], capture_output=True)

    def test_preflight_ok(self):
        self.assertIsNone(b.preflight())

    def test_list_json_shape(self):
        for i in b.ijson("list"):
            for key in ("name", "status", "type", "config"):
                self.assertIn(key, i)

    def test_stop_right_after_launch_does_not_hang(self):
        b.incus("launch", IMG, self.name)
        t0 = time.monotonic()
        b.stop_or_force("stop", self.name)  # a plain `incus stop` hung for 600 s here on systemd images
        self.assertLess(time.monotonic() - t0, 70)
        self.assertEqual(next(i for i in b.ijson("list") if i["name"] == self.name)["status"], "Stopped")

    def test_snapshot_roundtrip(self):
        b.incus("launch", IMG, self.name)
        b.incus("snapshot", "create", self.name, "s1")
        self.assertEqual([s["name"] for s in b.ijson("snapshot", "list", self.name)], ["s1"])
        b.incus("snapshot", "delete", self.name, "s1")
        self.assertEqual(b.ijson("snapshot", "list", self.name), [])

    def test_cancelled_launch_is_cleaned_up_even_though_the_server_finishes_it(self):
        proc = subprocess.Popen(["incus", "launch", IMG, self.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.3)
        proc.send_signal(2)  # SIGINT, what Ctrl-C and the app's Cancel send
        proc.wait(timeout=30)
        self.assertTrue(b.cleanup_loop(self.name, run, patience=90))
        self.assertNotIn(self.name, names())

    def test_monitor_emits_parseable_lifecycle_events(self):
        mon = subprocess.Popen(["incus", "monitor", "--type=lifecycle", "--format", "json"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            time.sleep(1)
            b.incus("launch", IMG, self.name)
            seen = set()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not {"instance-created", "instance-started"} <= seen:
                ev = b.parse_event(mon.stdout.readline())
                if ev and ev[1].endswith(self.name):
                    seen.add(ev[0])
            self.assertTrue({"instance-created", "instance-started"} <= seen, seen)
        finally:
            mon.terminate()
            mon.wait(timeout=10)
            mon.stdout.close()


if __name__ == "__main__":
    unittest.main()
