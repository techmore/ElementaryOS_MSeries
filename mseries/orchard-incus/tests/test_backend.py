"""Unit tests for the display-free backend. Run: python3 -m unittest discover -s tests -v"""
import json
import os
import subprocess
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from orchard_incus import backend as b  # noqa: E402  (imports no GTK)


class ProgressParsing(unittest.TestCase):
    # lines captured from a real `incus launch images:debian/trixie` (progress goes to stdout, \r separated)
    def test_download_line(self):
        self.assertEqual(b.parse_progress("Retrieving image: rootfs: 42% (6.97MB/s)"), ("rootfs", 42, "6.97MB/s"))

    def test_metadata_and_unpack(self):
        self.assertEqual(b.parse_progress("Retrieving image: metadata: 100% (2.01GB/s)"), ("metadata", 100, "2.01GB/s"))
        self.assertEqual(b.parse_progress("Retrieving image: Unpacking image: 100% (1.84GB/s)"), ("Unpacking image", 100, "1.84GB/s"))

    def test_lines_without_a_percentage(self):
        for line in ("Launching oi-p1", "Creating oi-p1", "", "Error: Failed instance creation: boom"):
            self.assertIsNone(b.parse_progress(line))

    def test_no_speed(self):
        self.assertEqual(b.parse_progress("Retrieving image: rootfs: 7%"), ("rootfs", 7, None))

    def test_text(self):
        self.assertEqual(b.progress_text("rootfs", 42, "6.97MB/s"), "Downloading image 42% · 6.97MB/s")
        self.assertEqual(b.progress_text("Unpacking image", 100), "Unpacking image 100%")
        self.assertEqual(b.progress_text("weird", 5), "weird 5%")


class Names(unittest.TestCase):
    def test_valid(self):
        for n in ("a", "web-1", "Debian13", "a" * 63, "x1"):
            self.assertTrue(b.valid_name(n), n)

    def test_invalid(self):
        for n in ("", "-a", "a-", "bad name", "bad_name", "a" * 64, "naïve", "x.y", "a/b"):
            self.assertFalse(b.valid_name(n), n)

    def test_auto_name_is_valid_and_derived_from_the_image(self):
        fixed = lambda n: b"\xab\xcd"
        self.assertEqual(b.auto_name("images:debian/trixie", fixed), "debian-trixie-abcd")
        self.assertEqual(b.auto_name("images:ubuntu/24.04", fixed), "ubuntu-24-04-abcd")
        for img in ("images:alpine/edge", "local:abc", "weird!!!", "", "images:" + "x" * 80):
            self.assertTrue(b.valid_name(b.auto_name(img)), img)


class Numbers(unittest.TestCase):
    def test_human(self):
        self.assertEqual(b.human(0), "0 B")
        self.assertEqual(b.human(1023), "1023 B")
        self.assertEqual(b.human(1024), "1.0 KiB")
        self.assertEqual(b.human(11 * 1024 * 1024 + 400000), "11.4 MiB")
        self.assertEqual(b.human(None), "0 B")

    def test_cpu_percent(self):
        self.assertAlmostEqual(b.cpu_percent(0, 0.0, 3_000_000_000, 3.0), 100.0)  # one core busy
        self.assertAlmostEqual(b.cpu_percent(0, 0.0, 6_000_000_000, 3.0), 200.0)  # two cores busy
        self.assertAlmostEqual(b.cpu_percent(1_000_000_000, 10.0, 1_300_000_000, 13.0), 10.0)

    def test_cpu_percent_edge_cases(self):
        self.assertEqual(b.cpu_percent(None, None, 5, 1.0), 0.0)  # first sample
        self.assertEqual(b.cpu_percent(5, 1.0, 9, 1.0), 0.0)  # no time elapsed
        self.assertEqual(b.cpu_percent(9, 1.0, 5, 4.0), 0.0)  # counter reset after a restart never goes negative

    def test_contrast(self):
        rgb = lambda r, g, bl: types.SimpleNamespace(red=r, green=g, blue=bl)
        self.assertAlmostEqual(b.contrast(rgb(0, 0, 0), rgb(1, 1, 1)), 21.0, places=1)
        self.assertAlmostEqual(b.contrast(rgb(1, 1, 1), rgb(1, 1, 1)), 1.0, places=2)
        # elementary's pastel light-mode accent against its light background, measured on the real theme
        self.assertLess(b.contrast(rgb(169 / 255, 200 / 255, 232 / 255), rgb(250 / 255, 250 / 255, 250 / 255)), 3.0)


class Addresses(unittest.TestCase):
    STATE = {"network": {
        "lo": {"addresses": [{"family": "inet", "address": "127.0.0.1", "scope": "local"}]},
        "eth0": {"addresses": [
            {"family": "inet", "address": "10.169.229.233", "scope": "global"},
            {"family": "inet6", "address": "fd42::1", "scope": "global"},
            {"family": "inet6", "address": "fe80::1", "scope": "link"}]}}}

    def test_global_only_no_loopback(self):
        self.assertEqual(b.addrs(self.STATE, "inet"), ["10.169.229.233"])
        self.assertEqual(b.addrs(self.STATE, "inet6"), ["fd42::1"])

    def test_missing_state(self):
        self.assertEqual(b.addrs(None, "inet"), [])
        self.assertEqual(b.addrs({"network": None}, "inet"), [])

    def test_state_key_and_last(self):
        self.assertEqual([b.state_key(s) for s in ("Running", "Frozen", "Stopped", "Error", "")], ["running", "frozen", "stopped", "stopped", "stopped"])
        self.assertEqual(b.last([]), 0.0)
        self.assertEqual(b.last([1, 2, 3]), 3)


class NewInstanceForm(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(b.validate_new("", "images:alpine/edge", "", ""), [])
        self.assertEqual(b.validate_new("web-1", "images:debian/trixie", "2", "512MiB"), [])
        self.assertEqual(b.validate_new("web", "i:a", "1-4", "1.5 GiB"), [])
        self.assertEqual(b.validate_new("web", "i:a", "", "50%"), [])

    def test_each_problem_reported(self):
        self.assertEqual(len(b.validate_new("bad name", "", "abc", "lots")), 4)
        self.assertIn("Choose or enter an image.", b.validate_new("", "  ", "", ""))
        self.assertTrue(any(m.startswith("CPU") for m in b.validate_new("", "i:a", "two", "")))
        self.assertTrue(any(m.startswith("Memory") for m in b.validate_new("", "i:a", "", "1 gig")))

    def test_create_args(self):
        self.assertEqual(b.create_args(False, "", ""), [])
        self.assertEqual(b.create_args(True, " 2 ", "1GiB"), ["--vm", "-c", "limits.cpu=2", "-c", "limits.memory=1GiB"])


class EventsAndImages(unittest.TestCase):
    def test_parse_event_real_lines(self):
        line = '{"type":"lifecycle","timestamp":"2026-10-16T01:00:00Z","metadata":{"action":"instance-started","source":"/1.0/instances/oi-m1"}}'
        self.assertEqual(b.parse_event(line), ("instance-started", "/1.0/instances/oi-m1"))
        self.assertEqual(b.parse_event('{"metadata":{"action":"instance-snapshot-created","source":"/1.0/instances/a/snapshots/s1"}}'),
                         ("instance-snapshot-created", "/1.0/instances/a/snapshots/s1"))

    def test_parse_event_garbage(self):
        for line in ("", "\n", "not json", "{}", '{"metadata": null}', "[1,2]", '"x"'):
            self.assertIsNone(b.parse_event(line), repr(line))

    def test_started_actions(self):
        self.assertIn("instance-started", b.STARTED_ACTIONS)
        self.assertNotIn("instance-stopped", b.STARTED_ACTIONS)

    CSV = ('debian/13 (7 more),Debian trixie arm64 (20261015_05:24),VIRTUAL-MACHINE\n'
           'debian/13 (7 more),Debian trixie arm64 (20261015_05:24),CONTAINER\n'
           'debian/13 (7 more),Debian trixie arm64 (20261015_05:24),CONTAINER\n'  # duplicate
           'debian/13/cloud (3 more),"Debian trixie, cloud (x)",CONTAINER\n'
           'broken line\n')

    def test_parse_images_csv(self):
        rows = b.parse_images_csv(self.CSV)
        self.assertEqual(rows, [("debian/13", "Debian trixie arm64 (20261015_05:24)", True),
                                ("debian/13", "Debian trixie arm64 (20261015_05:24)", False),
                                ("debian/13/cloud", "Debian trixie, cloud (x)", False)])

    def test_parse_images_csv_limit(self):
        many = "\n".join(f"a{i},d,CONTAINER" for i in range(100))
        self.assertEqual(len(b.parse_images_csv(many)), 60)
        self.assertEqual(len(b.parse_images_csv(many, limit=5)), 5)


class FakeIncus:
    """Replaces backend.incus for a test; records calls and replays scripted results."""
    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def __call__(self, *args, **kw):
        self.calls.append(args)
        r = self.script.pop(0) if self.script else ""
        if isinstance(r, Exception):
            raise r
        return r


class Preflight(unittest.TestCase):
    def setUp(self):
        self._orig = b.incus

    def tearDown(self):
        b.incus = self._orig

    def test_ok(self):
        b.incus = FakeIncus("Client version: 6.0.5\n")
        self.assertIsNone(b.preflight())

    def test_not_installed(self):
        b.incus = FakeIncus(FileNotFoundError("incus"))
        title, _, cmd = b.preflight()
        self.assertIn("installed", title)
        self.assertIn("apt install incus", cmd)

    def test_permission_denied(self):
        for msg in ("Error: permission denied", "dial unix /var/lib/incus/unix.socket: connect: Permission denied"):
            b.incus = FakeIncus(RuntimeError(msg))
            title, _, cmd = b.preflight()
            self.assertIn("permission", title.lower())
            self.assertIn("incus-admin", cmd)

    def test_not_running(self):
        b.incus = FakeIncus(RuntimeError("Error: The remote isn't reachable"))
        title, _, cmd = b.preflight()
        self.assertIn("running", title)
        self.assertIn("systemctl start incus", cmd)

    def test_timeout(self):
        b.incus = FakeIncus(subprocess.TimeoutExpired("incus", 10))
        self.assertIn("responding", b.preflight()[0])


class StopOrForce(unittest.TestCase):
    def setUp(self):
        self._orig = b.incus

    def tearDown(self):
        b.incus = self._orig

    def test_graceful_succeeds_without_force(self):
        b.incus = FakeIncus("")
        b.stop_or_force("stop", "web")
        self.assertEqual(len(b.incus.calls), 1)
        self.assertEqual(b.incus.calls[0][:3], ("stop", "--timeout", "30"))

    def test_falls_back_to_force_on_error_or_timeout(self):
        for first in (RuntimeError("busy"), subprocess.TimeoutExpired("incus", 60)):
            b.incus = FakeIncus(first, "")
            b.stop_or_force("restart", "web")
            self.assertEqual(b.incus.calls[1][:2], ("restart", "--force"))


class CleanupLoop(unittest.TestCase):
    """The cancel path: the instance may show up late, so the loop must outlast the server-side operation."""
    NAME = "oi-c1"

    def make(self, instance_appears_after):
        t = {"now": 0.0}
        log = {"ops_deleted": [], "deletes": 0}
        def run(args):
            if args[:3] == ["incus", "operation", "list"]:
                busy = t["now"] < instance_appears_after
                op = {"id": "op-1", "status": "Running" if busy else "Success", "resources": {"instances": [f"/1.0/instances/{self.NAME}"]}}
                other = {"id": "op-2", "status": "Running", "resources": {"instances": ["/1.0/instances/other"]}}
                return 0, json.dumps([op, other]), ""
            if args[:3] == ["incus", "operation", "delete"]:
                log["ops_deleted"].append(args[3])
                return 0, "", ""
            if args[:2] == ["incus", "delete"]:
                log["deletes"] += 1
                if t["now"] < instance_appears_after:
                    return 1, "", 'Error: Failed checking instance exists: Instance not found'
                return 0, "", ""
            raise AssertionError(args)
        def sleep(s):
            t["now"] += s
        return run, sleep, (lambda: t["now"]), log

    def test_instance_already_there(self):
        run, sleep, clock, log = self.make(0)
        self.assertTrue(b.cleanup_loop(self.NAME, run, sleep, clock))
        self.assertEqual(log["deletes"], 1)

    def test_waits_for_a_late_instance(self):
        run, sleep, clock, log = self.make(25)  # appears 25 simulated seconds after the cancel
        self.assertTrue(b.cleanup_loop(self.NAME, run, sleep, clock))
        self.assertGreater(log["deletes"], 5)

    def test_cancels_only_this_instances_operations(self):
        run, sleep, clock, log = self.make(5)
        b.cleanup_loop(self.NAME, run, sleep, clock)
        self.assertEqual(set(log["ops_deleted"]), {"op-1"})

    def test_gives_up_after_patience(self):
        run, sleep, clock, log = self.make(10_000)
        self.assertFalse(b.cleanup_loop(self.NAME, run, sleep, clock, patience=40))

    def test_backs_off_after_30_seconds(self):
        run, sleep, clock, log = self.make(10_000)
        b.cleanup_loop(self.NAME, run, sleep, clock, patience=120)
        # ~30 one-second rounds, then 3-second rounds: well under 120 attempts
        self.assertLess(log["deletes"], 70)
        self.assertGreater(log["deletes"], 30)

    def test_survives_garbage_from_operation_list(self):
        def run(args):
            if args[:3] == ["incus", "operation", "list"]:
                return 0, "not json", ""
            return 0, "", ""
        self.assertTrue(b.cleanup_loop(self.NAME, run, lambda s: None, lambda: 0.0))


if __name__ == "__main__":
    unittest.main()
