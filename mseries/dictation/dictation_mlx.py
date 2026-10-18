"""Optional resident Parakeet MLX GPU model for the English F5 controller.

The explicit MLX engine uses Omarchy's qualified Vulkan runtime, not Apple's
macOS Metal binaries. It never installs dependencies, fetches model files or
falls back to an unqualified CPU device. The worker shares the ANE adapter's
bounded, cancellable IPC; idle expiry releases its native model process group.
"""
import os
from pathlib import Path

from dictation_ane import FramedWorker


class MlxModel(FramedWorker):
    def __init__(self):
        prefix = Path(os.environ.get("MLX_STT_PREFIX", "~/.local/share/mlx-omarchy")).expanduser()
        python = Path(os.environ.get("MLX_STT_PYTHON", str(prefix / "venv/bin/python"))).expanduser()
        model = Path(os.environ.get(
            "MLX_STT_MODEL_DIR", "~/.local/share/mseries/stream/models/mlx-parakeet")).expanduser()
        modules = os.environ.get("MLX_STT_MODULES")
        if not python.is_file():
            raise RuntimeError("Optional MLX speech runtime absent; configure MLX_STT_PYTHON")
        required = ("config.json", "model.safetensors", "tokenizer.model", "tokenizer.vocab", "vocab.txt")
        if not all((model / name).is_file() for name in required):
            raise RuntimeError("Optional pinned MLX speech assets absent; configure MLX_STT_MODEL_DIR")
        if modules and not Path(modules).expanduser().is_dir():
            raise RuntimeError("Optional MLX speech package overlay absent; configure MLX_STT_MODULES")
        icd = Path(os.environ.get(
            "MLX_STT_VK_ICD", str(prefix / "vulkan/honeykrisp_icd.aarch64.json"))).expanduser()
        if not icd.is_file():
            raise RuntimeError("Qualified MLX Vulkan ICD absent; configure MLX_STT_VK_ICD")
        env = dict(os.environ, HF_HUB_OFFLINE="1", OMARCHY_MLX_SYSTEM_PREFIX=str(prefix),
                   VK_DRIVER_FILES=str(icd), PYTHONUNBUFFERED="1")
        command = [str(python), str(Path(__file__).with_name("mlx-speech-worker.py")),
                   "--model-dir", str(model)]
        if modules:
            command.extend(["--modules", str(Path(modules).expanduser())])
        super().__init__(command, env=env)

    def transcribe(self, pcm_f32, deadline_ms=90000):
        if not isinstance(pcm_f32, bytes) or len(pcm_f32) % 4:
            raise ValueError("MLX speech expects f32le mono16kHz PCM bytes")
        reply = self.request({"op": "transcribe", "sample_rate": 16000}, pcm_f32,
                             deadline_ms=deadline_ms)
        text = reply.get("transcript")
        if not reply["ok"] or not isinstance(text, str):
            self.cancel()
            raise RuntimeError("Invalid MLX speech transcript reply")
        return text

    def warm(self):
        reply = self.request({"op": "warm"}, deadline_ms=90000)
        if not reply["ok"]:
            self.cancel()
            raise RuntimeError("Optional pinned MLX speech warm-up unavailable")


MLXModel = MlxModel
