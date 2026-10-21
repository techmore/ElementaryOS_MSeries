#!/usr/bin/env python3
"""Tests for summarize-share-cost.py against fixture captures. Throwaway files only."""

import importlib.util
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(__file__).parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cost = load("summarize_share_cost", "summarize-share-cost.py")

# One capture: a browser role with two processes plus the server, an NA row,
# whole-system power present, and viewer counts that match the expectation.
SHARE = """# session=share workload=fullscreen-video display_mode=internal-panel duration_s=30 interval_s=5 started_utc=2026-10-19T18:00:00Z viewers_expected=3 browser=brave
utc,session,workload,display_mode,pid,process,role,cpu_percent_one_core,ram_kib,elapsed_s,system_power_w,battery_flow_mw,battery_status,ac_online,battery_percent,share_live,share_viewers
2026-10-19T18:00:05Z,share,fullscreen-video,internal-panel,100,brave,browser,20.00,500000,5,21.5,0,Not charging,1,80,True,3
2026-10-19T18:00:05Z,share,fullscreen-video,internal-panel,101,brave,browser,10.00,300000,5,21.5,0,Not charging,1,80,True,3
2026-10-19T18:00:05Z,share,fullscreen-video,internal-panel,200,rupert-core,server,2.00,90000,5,21.5,0,Not charging,1,80,True,3
2026-10-19T18:00:10Z,share,fullscreen-video,internal-panel,100,brave,browser,30.00,500000,10,22.0,0,Not charging,1,80,True,3
2026-10-19T18:00:10Z,share,fullscreen-video,internal-panel,101,brave,browser,NA,300000,10,22.0,0,Not charging,1,80,True,3
2026-10-19T18:00:10Z,share,fullscreen-video,internal-panel,200,rupert-core,server,2.50,90000,10,22.0,0,Not charging,1,80,True,3
"""

# A session capture without a role column must fall back to process grouping.
SESSION = """# session=gala workload=idle display_mode=internal-panel duration_s=30 interval_s=5 started_utc=2026-10-19T15:37:54Z
utc,session,workload,display_mode,pid,process,cpu_percent_one_core,ram_kib,elapsed_s
2026-10-19T15:37:59Z,gala,idle,internal-panel,10,gala,11.20,178720,5
2026-10-19T15:38:04Z,gala,idle,internal-panel,10,gala,10.80,178720,10
"""


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def write(self, name, text):
        path = self.root / name
        path.write_text(text)
        return path

    def browser(self, summary):
        return next(g for g in summary["groups"] if g["group"] == "browser")

    def test_role_grouping_sums_processes_per_sample(self):
        summary = cost.capture_summary(self.write("share.csv", SHARE))
        self.assertEqual(summary["metadata"]["viewers_expected"], "3")
        self.assertEqual(summary["viewers_observed"], ["3"])
        browser = self.browser(summary)
        # 20+10 then 30 alone (the NA row is excluded, so that sample is 30).
        self.assertEqual(browser["cpu"]["n"], 2)
        self.assertEqual(browser["cpu"]["median"], 30.0)
        self.assertEqual(browser["cpu"]["min"], 30.0)
        self.assertEqual(browser["cpu"]["max"], 30.0)
        self.assertEqual(browser["cpu_na"], 1)
        # RSS sums both processes at every sample: 800000.
        self.assertEqual(browser["rss"]["median"], 800000)
        server = next(g for g in summary["groups"] if g["group"] == "server")
        self.assertEqual(server["cpu"]["median"], 2.25)
        self.assertEqual(sorted(server["processes"]), ["rupert-core"])

    def test_per_process_detail(self):
        path = self.write("share.csv", SHARE)
        summary = cost.capture_summary(path, per_process=True)
        brave = next(g for g in summary["groups"] if g["group"] == "browser/brave")
        self.assertEqual(brave["cpu"]["n"], 3)   # three valid rows, one NA
        self.assertEqual(brave["cpu"]["median"], 20.0)

    def test_session_capture_falls_back_to_process(self):
        summary = cost.capture_summary(self.write("gala.csv", SESSION))
        self.assertEqual([g["group"] for g in summary["groups"]], ["gala"])
        gala = summary["groups"][0]
        self.assertEqual(gala["kind"], "process")
        self.assertEqual(gala["cpu"]["median"], 11.0)
        self.assertEqual(gala["rss"]["median"], 178720)

    def test_group_filter(self):
        path = self.write("share.csv", SHARE)
        summary = cost.capture_summary(path)
        groups = [g for g in summary["groups"] if "serv" in g["group"]]
        self.assertEqual([g["group"] for g in groups], ["server"])

    def test_missing_columns_fail(self):
        path = self.write("bad.csv", "a,b\n1,2\n")
        with self.assertRaises(SystemExit):
            cost.read_capture(path)


if __name__ == "__main__":
    unittest.main()
