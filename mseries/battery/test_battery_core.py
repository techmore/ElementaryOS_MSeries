#!/usr/bin/python3 -I
"""Offline tests for battery_core: sessions, usage bands, power events, suspend gaps, runtime estimates."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import battery_core as core  # noqa: E402

FULL = 60_000_000  # 60 Wh in µWh


def row(ts, pct, watts, cpu=10.0, ac=0, bright=50.0, top=None):
    return {"ts": ts, "status": "Charging" if ac else "Discharging", "ac": ac, "pct": pct,
            "energy_uwh": int(FULL * pct / 100), "full_uwh": FULL, "batt_w": -watts, "sys_w": watts,
            "cpu_pct": cpu, "cpu_mhz": 1500.0, "load1": 1.0, "temp_c": 30.0, "bright_pct": bright,
            "top": json.dumps(top or [["firefox", cpu / 2]])}


class CoreTests(unittest.TestCase):
    def test_session_energy_and_projection(self):
        rows = [row(1000 + i * 15, 100 - i * 0.0125, 10.0) for i in range(241)]  # one hour, 3 %
        found = core.sessions(rows)
        self.assertEqual(len(found), 1)
        run = found[0]
        self.assertEqual(run["seconds"], 3600)
        self.assertAlmostEqual(run["wh_used"], 1.8, places=1)  # 3 % of 60 Wh
        self.assertAlmostEqual(run["avg_w"], 1.8, places=1)
        self.assertAlmostEqual(run["projected_hours"], 60 / run["avg_w"], places=0)

    def test_sessions_split_on_gap_and_on_charger(self):
        rows = [row(0, 90, 8), row(15, 89.9, 8), row(5000, 80, 8), row(5015, 79.9, 8),
                row(5030, 79.9, 8, ac=1), row(5045, 80, 8, ac=1)]
        self.assertEqual(len(core.sessions(rows)), 2)

    def test_usage_profile_bands(self):
        rows = [row(i * 15, 90, 4.0, cpu=5) for i in range(240)] + [row(10000 + i * 15, 70, 20.0, cpu=80) for i in range(240)]
        bands = {b["band"]: b for b in core.usage_profile(rows)}
        self.assertAlmostEqual(bands["Idle"]["avg_w"], 4.0)
        self.assertAlmostEqual(bands["Heavy"]["runtime_h"], 3.0)
        self.assertEqual(bands["Moderate"]["samples"], 0)

    def test_power_step_event_names_cause(self):
        conn = core.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
        det = core.EventDetector()
        for i in range(5):
            det.feed(conn, row(i * 15, 90, 5.0, cpu=5))
        det.feed(conn, row(75, 90, 17.0, cpu=70, top=[["ffmpeg", 60.0]]))
        found = core.events(conn, 0)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["kind"], "rise")
        self.assertEqual(found[0]["culprit"], "ffmpeg")
        self.assertIn("CPU load", found[0]["detail"])
        for i in range(5):  # settle, then drop
            det.feed(conn, row(200 + i * 15, 90, 17.0, cpu=70))
        det.feed(conn, row(300, 90, 5.0, cpu=5))
        self.assertEqual(core.events(conn, 0)[0]["kind"], "drop")

    def test_suspend_gap_recorded(self):
        conn = core.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
        det = core.EventDetector()
        det.feed(conn, row(0, 90, 5.0))
        det.feed(conn, row(8 * 3600, 88, 5.0))
        gap = core.events(conn, 0)[0]
        self.assertEqual(gap["kind"], "gap")
        self.assertEqual(json.loads(gap["detail"])["seconds"], 8 * 3600)

    def test_runtime_estimate_only_on_battery(self):
        rows = [row(i * 15, 50, 10.0) for i in range(20)]
        est = core.estimate_runtime(rows)
        self.assertAlmostEqual(est["hours_left"], 3.0)
        self.assertAlmostEqual(est["hours_full"], 6.0)
        self.assertEqual(core.estimate_runtime(rows + [row(400, 50, 10.0, ac=1)]), {})

    def test_sampler_reads_this_machine(self):
        sampler = core.Sampler()
        sampler.sample()
        snap = sampler.sample()
        self.assertEqual(set(snap), set(core.COLUMNS))

    def test_fmt_hours(self):
        self.assertEqual(core.fmt_hours(7.5), "7h 30m")
        self.assertEqual(core.fmt_hours(0.5), "30 min")
        self.assertEqual(core.fmt_hours(None), "—")


if __name__ == "__main__":
    unittest.main()
