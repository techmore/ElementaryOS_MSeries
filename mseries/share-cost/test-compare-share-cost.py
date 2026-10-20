#!/usr/bin/env python3
"""Tests for compare-share-cost.py against fixture captures. Throwaway files only."""

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


compare = load("compare_share_cost", "compare-share-cost.py")

HEADER = ("# session=share workload={workload} display_mode=internal-panel "
          "duration_s=60 interval_s=5 started_utc=2026-10-19T18:00:00Z "
          "viewers_expected={expected} browser=brave")
COLUMNS = ("utc,session,workload,display_mode,pid,process,role,cpu_percent_one_core,"
           "ram_kib,elapsed_s,system_power_w,battery_flow_mw,battery_status,ac_online,"
           "battery_percent,share_live,share_viewers")


def capture_text(expected, samples, workload="fullscreen-video", ac="1"):
    """samples: [(browser CPU percent, whole-system watts), ...]"""
    lines = [HEADER.format(workload=workload, expected=expected), COLUMNS]
    for index, (cpu, watts) in enumerate(samples, start=1):
        elapsed = index * 5
        utc = f"2026-10-19T18:00:{elapsed:02d}Z"
        for pid, process, role, value, rss in (
                (100, "brave", "browser", cpu, 500000),
                (200, "rupert-core", "server", 2.0, 90000)):
            lines.append(
                f"{utc},share,{workload},internal-panel,{pid},{process},{role},"
                f"{value:.2f},{rss},{elapsed},{watts:.2f},0,Not charging,{ac},80,True,{expected}")
    return "\n".join(lines) + "\n"


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.count = 0

    def capture(self, expected, samples, **kwargs):
        self.count += 1
        path = self.root / f"capture-{self.count}.csv"
        path.write_text(capture_text(expected, samples, **kwargs))
        return path

    def summary(self, expected, samples, **kwargs):
        return compare.summarizer.capture_summary(self.capture(expected, samples, **kwargs))

    def test_summarizer_now_reports_system_power(self):
        summary = self.summary(1, [(20.0, 12.0), (22.0, 13.0)])
        self.assertEqual(summary["power"]["n"], 2)
        self.assertEqual(summary["power"]["median"], 12.5)
        self.assertEqual(summary["ac_online_observed"], ["1"])

    def test_difference_above_spread(self):
        low = [self.summary(1, [(20.0, 12.0)] * 3),
               self.summary(1, [(22.0, 12.2)] * 3)]
        high = [self.summary(3, [(60.0, 18.0)] * 3),
                self.summary(3, [(64.0, 18.2)] * 3)]
        result = compare.comparison(low + high, 1, 3)
        self.assertEqual(result["roles"]["browser"]["median_low"], 21.0)
        self.assertEqual(result["roles"]["browser"]["median_high"], 62.0)
        self.assertEqual(result["roles"]["browser"]["delta"], 41.0)
        self.assertEqual(result["roles"]["browser"]["threshold"], 4.0)
        self.assertEqual(result["roles"]["browser"]["verdict"], "difference exceeds spread")
        self.assertEqual(result["roles"]["server"]["verdict"], "no measured difference")
        self.assertEqual(result["power"]["verdict"], "difference exceeds spread")

    def test_difference_within_spread(self):
        low = [self.summary(1, [(20.0, 12.0)] * 3),
               self.summary(1, [(30.0, 12.0)] * 3)]
        high = [self.summary(3, [(28.0, 12.0)] * 3),
                self.summary(3, [(32.0, 12.0)] * 3)]
        result = compare.comparison(low + high, 1, 3)
        self.assertEqual(result["roles"]["browser"]["delta"], 5.0)
        self.assertEqual(result["roles"]["browser"]["threshold"], 10.0)
        self.assertEqual(result["roles"]["browser"]["verdict"], "no measured difference")

    def test_one_capture_per_condition_is_insufficient(self):
        low = [self.summary(1, [(20.0, 12.0)] * 3)]
        high = [self.summary(3, [(60.0, 18.0)] * 3)]
        result = compare.comparison(low + high, 1, 3)
        self.assertEqual(result["roles"]["browser"]["verdict"], "insufficient repeats")
        self.assertEqual(result["power"]["verdict"], "insufficient repeats")

    def test_mismatched_conditions_are_refused(self):
        low = self.summary(1, [(20.0, 12.0)] * 3, workload="fullscreen-video")
        high = self.summary(3, [(60.0, 18.0)] * 3, workload="windowed-slides")
        errors = compare.protocol_errors([low, high])
        self.assertTrue(any("workload differs" in error for error in errors), errors)

    def test_wrong_observed_viewer_count_is_refused(self):
        path = self.capture(3, [(20.0, 12.0)] * 3)
        text = path.read_text().replace(",True,3\n", ",True,1\n")
        path.write_text(text)
        errors = compare.protocol_errors([compare.summarizer.capture_summary(path)])
        self.assertTrue(any("expected 3 viewer(s), observed 1" in error for error in errors), errors)

    def test_battery_capture_is_refused(self):
        low = self.summary(1, [(20.0, 12.0)] * 3, ac="0")
        errors = compare.protocol_errors([low])
        self.assertTrue(any("AC power was not on" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
