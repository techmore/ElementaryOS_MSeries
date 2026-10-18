#!/usr/bin/python3
"""Bounded framed optional English Parakeet MLX worker; no microphone or network.

Lazy model-family import and initial silence warm-up follow Joshua Warren /
mlx-omarchy's MIT gpu_stt_worker.py. Only the pinned mlx-audio0.5.6 Parakeet
snapshot is accepted. A wedged native call is terminated by the owning parent.
No unsolicited stdout ready messages; every request has one matching response.
"""
import argparse
import contextlib
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys

MAX_HEADER = 256 * 1024
MAX_PCM_BYTES = 30 * 16000 * 4
MODEL_FILES = {
    "config.json": (244093, "f320f1292511f34ec47f513755fe20fd01dbfc09a925d42730e66059a6e1ef4c"),
    "model.safetensors": (2508288736, "05e01c7f396c298cf7d23f61da7b504adeab698f0aaeafd9c82d198625464592"),
    "tokenizer.model": (360916, "eacec2b0a77f336d4a2ca4a25a7047575d3c2b74de47e997f4c205126ed3135e"),
    "tokenizer.vocab": (101024, "41130ff456706304a1adec782ccc9e003c4d417e8e324353d281be958cac4e17"),
    "vocab.txt": (46772, "3cde1409fd78783a79b29ed4d32da57c746993856f7c8263bcb905d2e5839db7"),
}


def verify_assets(directory):
    for name, (size, digest) in MODEL_FILES.items():
        path = directory / name
        if not path.is_file() or path.stat().st_size != size:
            raise RuntimeError("Pinned MLX speech assets absent or wrong-sized: " + name)
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                raise RuntimeError("Pinned MLX speech asset hash mismatch: " + name)


def read_exact(stream, size):
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(size - len(result))
        if not chunk:
            raise EOFError("MLX speech request truncated")
        result.extend(chunk)
    return bytes(result)


def read_request(stream):
    raw = stream.read(8)
    if not raw:
        return None
    if len(raw) != 8:
        raw += read_exact(stream, 8 - len(raw))
    size, = struct.unpack("<Q", raw)
    if not 0 < size <= MAX_HEADER:
        raise ValueError("MLX speech request header exceeds limit")
    header = json.loads(read_exact(stream, size))
    if not isinstance(header, dict):
        raise ValueError("MLX speech request must be an object")
    size = header.get("payload_bytes", 0)
    if type(size) is not int or not 0 <= size <= MAX_PCM_BYTES or size % 4:
        raise ValueError("MLX speech payload exceeds30s or is malformed")
    if type(header.get("id")) is not int:
        raise ValueError("MLX speech request id must be an integer")
    return header, read_exact(stream, size)


def send(stream, header):
    encoded = json.dumps(dict(header, payload_bytes=0)).encode()
    if len(encoded) > MAX_HEADER:
        raise ValueError("MLX speech reply exceeds limit")
    stream.write(struct.pack("<Q", len(encoded)) + encoded)
    stream.flush()


class Runtime:
    def __init__(self, directory):
        self.directory = directory
        self.model = None

    def warm(self):
        if self.model is not None:
            return
        if importlib.metadata.version("mlx-audio") != "0.5.6":
            raise RuntimeError("Optional Parakeet MLX speech requires pinned mlx-audio0.5.6")
        verify_assets(self.directory)
        import mlx.core as mx
        if "gpu" not in str(mx.default_device()):
            raise RuntimeError("Optional MLX speech requires the qualified GPU device")
        name = "mlx_audio.stt.models"
        if name not in sys.modules:
            spec = importlib.util.find_spec(name)
            if spec is None:
                raise ModuleNotFoundError(name)
            sys.modules[name] = importlib.util.module_from_spec(spec)
        from mlx_audio.stt.utils import load_model
        with mx.stream(mx.gpu):
            model = load_model(self.directory, strict=True)
            # Parakeet's first call can be empty on this qualified stack; warm on
            # silence, never by secretly retrying a completed quality utterance.
            model.generate(mx.zeros((16000,), dtype=mx.float32), verbose=False)
        self.model = model

    def transcribe(self, payload):
        self.warm()
        import numpy as np
        import mlx.core as mx
        samples = np.frombuffer(payload, dtype="<f4")
        if not np.isfinite(samples).all():
            raise ValueError("MLX speech requires finite PCM")
        with mx.stream(mx.gpu):
            result = self.model.generate(mx.array(samples), verbose=False)
        text = getattr(result, "text", None)
        if not isinstance(text, str):
            raise RuntimeError("MLX speech model returned no text value")
        return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--modules", type=Path)
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    if args.modules:
        sys.path.insert(0, str(args.modules))
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    runtime = Runtime(args.model_dir)
    while True:
        try:
            item = read_request(stdin)
        except (EOFError, ValueError, TypeError, json.JSONDecodeError):
            return 2  # Invalid framing cannot be safely resynchronized.
        if item is None:
            return 0
        header, payload = item
        request_id = header["id"]
        if header.get("op") == "close":
            send(stdout, {"ok": True, "id": request_id})
            return 0
        try:
            # Libraries may print progress; keep stdout exclusively framed.
            with contextlib.redirect_stdout(sys.stderr):
                if header.get("op") == "warm" and not payload:
                    runtime.warm()
                    reply = {"ok": True}
                elif header.get("op") == "transcribe" and header.get("sample_rate") == 16000:
                    reply = {"ok": True, "transcript": runtime.transcribe(payload)}
                else:
                    raise ValueError("Unsupported MLX speech operation/sample rate")
        except Exception as error:
            # Do not include paths, a transcript, or native diagnostics in status.
            reply = {"ok": False, "kind": type(error).__name__,
                     "error": "Optional pinned MLX speech runtime unavailable; inspect local setup"}
        send(stdout, dict(reply, id=request_id))


if __name__ == "__main__":
    raise SystemExit(main())
