import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("audit", Path(__file__).with_name("audit-ane-qwen-layout.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class LayoutAuditTests(unittest.TestCase):
    def test_reports_padding_descriptor_and_unnamed_surface(self):
        surface = {"port": "t31", "anec_channel": 5, "named_in_stream": False,
                   "shape": [1, 1, 1, 50], "strides": [128, 128, 128, 2],
                   "packed_bytes": 128}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "prog_000.anec").write_bytes(struct.pack("<QII", 0, 0x300, 1))
            result = audit.audit({"programs": [{"surfaces": [surface]}]}, path)
        self.assertEqual(result["packing_mismatches"][0]["runtime_bytes"], 100)
        self.assertEqual(len(result["extended_descriptors"]), 1)
        self.assertEqual(len(result["unreferenced_surfaces"]), 1)
        self.assertFalse(result["submission_allowed"])

    def test_matching_row_and_duplicate_channel(self):
        surface = {"port": "t1", "anec_channel": 4, "named_in_stream": True,
                   "shape": [1, 1, 1, 32], "strides": [64, 64, 64, 2],
                   "packed_bytes": 64}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "prog_000.anec").write_bytes(struct.pack("<QII", 0, 0x1f8, 1))
            result = audit.audit({"programs": [{"surfaces": [surface, surface]}]}, path)
        self.assertEqual(result["packing_mismatches"], [])
        self.assertEqual(len(result["duplicate_channels"]), 1)
        self.assertEqual(result["extended_descriptors"], [])


if __name__ == "__main__":
    unittest.main()
