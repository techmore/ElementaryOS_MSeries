#!/usr/bin/env python3
"""Tests for summarize-metrics.py against fixture captures. Throwaway files only."""

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


metrics = load("summarize_metrics", "summarize-metrics.py")

GALA = """# session=gala workload=idle display_mode=internal-panel duration_s=30 interval_s=5 started_utc=2026-10-19T15:37:54Z
utc,session,workload,display_mode,pid,process,cpu_percent_one_core,ram_kib,elapsed_s,battery_power_mw,battery_percent
2026-10-19T15:37:59Z,gala,idle,internal-panel,10,gala,11.20,178720,5,NA,NA
2026-10-19T15:38:04Z,gala,idle,internal-panel,10,gala,10.80,178720,10,NA,NA
2026-10-19T15:38:09Z,gala,idle,internal-panel,10,gala,11.40,178720,15,NA,NA
"""

RUST = """# session=rust workload=idle-qualification display_mode=internal-3024x1964 duration_s=30 interval_s=5 started_utc=2026-10-19T15:56:18Z
utc,session,workload,display_mode,pid,process,cpu_percent_one_core,ram_kib,elapsed_s,battery_flow_mw,battery_status,ac_online,battery_percent
2026-10-19T15:56:23Z,rust,idle-qualification,internal-3024x1964,20,pantheon-compos,11.40,173472,5,0,Not charging,1,80
2026-10-19T15:56:28Z,rust,idle-qualification,internal-3024x1964,21,pantheon-compos,NA,173472,10,0,Not charging,1,80
2026-10-19T15:56:33Z,rust,idle-qualification,internal-3024x1964,21,pantheon-compos,11.20,173488,15,0,Not charging,1,80
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

    def test_metadata_and_stats(self):
        path = self.write("gala.csv", GALA)
        summary = metrics.capture_summary(path)
        self.assertEqual(summary["metadata"]["session"], "gala")
        self.assertEqual(summary["metadata"]["workload"], "idle")
        self.assertEqual(summary["metadata"]["display_mode"], "internal-panel")
        self.assertEqual(len(summary["processes"]), 1)
        proc = summary["processes"][0]
        self.assertEqual(proc["process"], "gala")
        self.assertEqual(proc["samples"], 3)
        self.assertEqual(proc["cpu_samples"], 3)
        self.assertEqual(proc["cpu_na"], 0)
        self.assertEqual(proc["cpu_mean"], 11.13)
        self.assertEqual(proc["cpu_median"], 11.2)
        self.assertEqual(proc["cpu_min"], 10.8)
        self.assertEqual(proc["cpu_max"], 11.4)
        self.assertEqual(proc["rss_median"], 178720)

    def test_na_samples_are_excluded_and_counted(self):
        path = self.write("rust.csv", RUST)
        proc = metrics.capture_summary(path)["processes"][0]
        self.assertEqual(proc["samples"], 3)
        self.assertEqual(proc["cpu_samples"], 2)
        self.assertEqual(proc["cpu_na"], 1)
        self.assertEqual(proc["cpu_median"], 11.3)
        self.assertEqual(proc["pids"], ["20", "21"])

    def test_missing_columns_fail(self):
        path = self.write("bad.csv", "a,b\n1,2\n")
        with self.assertRaises(SystemExit):
            metrics.read_capture(path)

    def test_process_filter(self):
        gala = self.write("gala.csv", GALA)
        rust = self.write("rust.csv", RUST)
        self.assertEqual([s["metadata"]["session"] for s in
                          (metrics.capture_summary(p) for p in (gala, rust))
                          if any("pantheon-compos" in p["process"] for p in s["processes"])],
                         ["rust"])


if __name__ == "__main__":
    unittest.main()
