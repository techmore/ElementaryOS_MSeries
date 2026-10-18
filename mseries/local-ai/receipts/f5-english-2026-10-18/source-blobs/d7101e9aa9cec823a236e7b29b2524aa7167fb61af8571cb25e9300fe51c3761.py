"""No-inference MLX adapter setup, framing and process retirement contracts."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from dictation_ane import FramedWorker
from dictation_mlx import MlxModel

spec = importlib.util.spec_from_file_location(
    "mlx_speech_worker", Path(__file__).with_name("mlx-speech-worker.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def frame(header, payload=b""):
    encoded = json.dumps(header).encode()
    return io.BytesIO(struct.pack("<Q", len(encoded)) + encoded + payload)


class OptionalSetup(unittest.TestCase):
    def test_missing_assets_fail_before_starting_a_worker(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "MLX_STT_PYTHON": sys.executable, "MLX_STT_MODEL_DIR": directory,
        }):
            with patch.object(FramedWorker, "__init__") as start:
                with self.assertRaisesRegex(RuntimeError, "assets absent"):
                    MlxModel()
                start.assert_not_called()

    def test_runtime_is_owned_offline_and_process_local(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in worker.MODEL_FILES:
                (root / name).touch()
            (root / "icd.json").write_text("{}")
            env = {"MLX_STT_PYTHON": sys.executable, "MLX_STT_MODEL_DIR": directory,
                   "MLX_STT_MODULES": directory, "MLX_STT_VK_ICD": str(root / "icd.json")}
            with patch.dict(os.environ, env), patch.object(FramedWorker, "__init__", return_value=None) as start:
                MlxModel()
            command = start.call_args.args[0]
            self.assertEqual(command[0], sys.executable)
            self.assertIn("--modules", command)
            self.assertEqual(start.call_args.kwargs["env"]["HF_HUB_OFFLINE"], "1")
            self.assertEqual(start.call_args.kwargs["env"]["VK_DRIVER_FILES"], str(root / "icd.json"))

    def test_partial_f32_rejected_without_request(self):
        model = object.__new__(MlxModel)
        with patch.object(model, "request") as request:
            with self.assertRaises(ValueError):
                model.transcribe(b"\x00")
            request.assert_not_called()

    def test_non_text_reply_retires_the_model(self):
        model = object.__new__(MlxModel)
        with patch.object(model, "request", return_value={"ok": True, "transcript": None}), patch.object(model, "cancel") as cancel:
            with self.assertRaisesRegex(RuntimeError, "transcript"):
                model.transcribe(bytes(8), deadline_ms=10)
            cancel.assert_called_once()


class WireAndAssets(unittest.TestCase):
    def test_request_preserves_binary_payload(self):
        header, payload = worker.read_request(frame({"id": 4, "payload_bytes": 4}, b"\x00\x00\x00\x00"))
        self.assertEqual(header["id"], 4)
        self.assertEqual(payload, bytes(4))

    def test_oversized_header_and_payload_rejected_before_allocation(self):
        with self.assertRaises(ValueError):
            worker.read_request(io.BytesIO(struct.pack("<Q", worker.MAX_HEADER + 1)))
        for bad in (worker.MAX_PCM_BYTES + 4, True, -1, 3):
            with self.subTest(size=bad), self.assertRaises(ValueError):
                worker.read_request(frame({"id": 1, "payload_bytes": bad}))

    def test_truncated_payload_is_not_decoded(self):
        with self.assertRaises(EOFError):
            worker.read_request(frame({"id": 1, "payload_bytes": 4}, b"\x00"))

    def test_asset_digest_rejects_same_size_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.safetensors"
            path.write_bytes(b"pinned")
            with patch.object(worker, "MODEL_FILES", {path.name: (6, hashlib.sha256(b"pinned").hexdigest())}):
                worker.verify_assets(path.parent)
                path.write_bytes(b"mutate")
                with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                    worker.verify_assets(path.parent)

    def test_worker_unknown_operation_returns_failure_and_is_reaped(self):
        # Starts only stdlib framing, never imports mlx or opens audio devices.
        process = FramedWorker([sys.executable, str(Path(worker.__file__)), "--model-dir", "/missing"])
        try:
            with self.assertRaises(RuntimeError):
                process.request({"op": "unsupported"}, deadline_ms=2000)
        finally:
            process.close()
        self.assertTrue(process.closed)


if __name__ == "__main__":
    unittest.main()
