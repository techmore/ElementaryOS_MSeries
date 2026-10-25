"""Missing compositor feedback and partial visibility must not produce a pass."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from frame_metrics import summarize_frames


def frame(counter, start, presentation, complete=True, refresh=8333):
    return dict(counter=counter, start_us=start, presentation_us=presentation,
                complete=complete, refresh_us=refresh)


class FrameMetricsTests(unittest.TestCase):
    def test_no_feedback_is_explicitly_unavailable_without_fabricated_latency(self):
        for raw in ([], [frame(1, 1000, 0, False)]):
            result = summarize_frames(raw, [(1100, 1)])
            self.assertEqual(result['status'], 'unavailable')
            self.assertIsNone(result['refresh_interval_us'])
            self.assertIsNone(result['programmatic_action_to_presentation_ms']['p95'])

    def test_sparse_navigation_is_not_a_complete_probe(self):
        result = summarize_frames([frame(1, 1000, 5000)], [(2000, 1)])
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['programmatic_action_to_presentation_ms']['p95'], 3)

    def test_missing_action_presentation_is_not_a_complete_probe(self):
        result = summarize_frames([frame(1, 1000, 5000)], [(2000, 1), (6000, 2)], 2)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['programmatic_action_to_presentation_ms']['samples'], 1)

    def test_counter_and_timestamp_must_both_follow_action(self):
        raw = [frame(1, 1000, 10000), frame(2, 2000, 5000), frame(3, 6000, 12000)]
        result = summarize_frames(raw, [(7000, 2)], 1)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['programmatic_action_to_presentation_ms']['p95'], 5)

    def test_long_stalls_remain_in_complete_measurements(self):
        result = summarize_frames([frame(1, 1000, 5000), frame(2, 6000, 3006000)],
                                  [(2000, 1), (7000, 2)], 2)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['frame_start_to_presentation_ms']['max'], 3000)
        self.assertEqual(result['presentation_gap_ms']['max'], 3001)

    def test_unknown_refresh_is_not_assumed_to_be_120hz(self):
        result = summarize_frames([frame(1, 1000, 5000, refresh=0)], [(2000, 1)], 1)
        self.assertIsNone(result['refresh_interval_us'])
