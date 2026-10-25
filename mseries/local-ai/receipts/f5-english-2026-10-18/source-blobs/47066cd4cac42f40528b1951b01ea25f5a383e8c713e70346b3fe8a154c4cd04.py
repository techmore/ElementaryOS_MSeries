#!/usr/bin/python3
"""Select a qualified F5 engine without changing capture/input preferences.

Only 90-english-engine.conf and this selector's private transaction receipts are
managed. Existing drop-ins, audio routing, input settings and other units stay
owned by their original installers. Selection is lazy: no model inference or
microphone capture occurs during activation.
"""
import argparse
import base64
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import uuid

HOME = Path.home()
BASE = HOME / ".local/share/mseries/stream"
SERVICE = "mseries-stream-dictate.service"
INPUT_SERVICE = "mseries-dictation-input.service"
DROPIN = HOME / ".config/systemd/user" / (SERVICE + ".d/90-english-engine.conf")
STATE = HOME / ".local/state/mseries-dictation-engine"
NEMOTRON = "nemotron-speech-streaming-en-0.6b-Q8_0.gguf"
NEMOTRON_SHA256 = "90d8c89714cd31efc88be62a40c6b2bea57e0cc2063af1ffe2c28f1a228ca110"
STREAM_MODEL = "parakeet-unified-en-0.6b-Q4_K_M.gguf"
STREAM_SHA256 = "a8bf3de2b393bd14ead5a858c3748d5e3b07a20fdeabdd3b498fba4f463fa929"


def atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing a managed symlink")
    fd, name = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def systemctl(*args, check=True):
    return subprocess.run(["systemctl", "--user", *args], text=True,
                          capture_output=True, check=check, timeout=20)


def active():
    return systemctl("is-active", "--quiet", SERVICE, check=False).returncode == 0


def environment():
    output = systemctl("show", SERVICE, "-p", "Environment", "--value").stdout
    return dict(item.split("=", 1) for item in shlex.split(output) if "=" in item)


def lifecycle():
    spec = importlib.util.spec_from_file_location("selector_status", BASE / "dictation_status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_status()


def idle_capture():
    pid = int(systemctl("show", SERVICE, "-p", "MainPID", "--value").stdout.strip() or 0)
    if not pid:
        return
    row = lifecycle()
    if not row or row.get("pid") != pid or row.get("phase") not in {"ready", "waiting", "error", "cancelled", "stopped"}:
        raise ValueError("F5 is active or its idle status is unavailable; finish dictation before switching")


def quiet_admission(engine="nemotron"):
    source = BASE / "machine.py"
    if not source.is_file():
        source = Path(__file__).resolve().parents[1] / "local-ai/machine.py"
    spec = importlib.util.spec_from_file_location("selector_machine", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    policy = dict(module.DEFAULT_POLICY)
    settings = HOME / ".config/mseries-ai/profiles.json"
    if settings.exists():
        policy.update(json.loads(settings.read_text())["policy"])
    policy["reserve_gib"] = max(6, policy.get("reserve_gib", 6))
    extra = (6 if engine == "mlx" else 2) * 1024 ** 3
    for sample_number in range(3):
        sample = module.snapshot()
        if (module.violations(sample, policy, extra)
                or max(sample["fans_rpm"].values(), default=9999) >= 2700
                or max(sample["temperatures_c"].values(), default=999) >= 60):
            raise ValueError("Wait for cool idle admission with the six-GiB desktop reserve")
        if sample_number < 2:
            time.sleep(.25)


def verify_file(path, digest):
    if not path.is_file():
        raise ValueError("Required pinned speech model is absent; run the English installer")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != digest:
        raise ValueError("Pinned speech model digest mismatch; selection was preserved")


def check_runtime(engine, current):
    for name in ("venv/bin/python", "stream-dictate.py", "dictation-input-client.py"):
        if not (BASE / name).is_file():
            raise ValueError("Install the English F5 payload and existing Unicode bridge first")
    additions = {}
    if engine in {"nemotron", "stream"}:
        name, digest = (NEMOTRON, NEMOTRON_SHA256) if engine == "nemotron" else (STREAM_MODEL, STREAM_SHA256)
        verify_file(BASE / "models" / name, digest)
        if not (BASE / "native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so").is_file():
            raise ValueError("Pinned native CPU speech runtime is absent")
        additions["STREAM_MODEL"] = str(BASE / "models" / name)
    elif engine == "ane":
        prefix = Path(current.get("ANE_PREFIX", "~/.local/share/mlx-omarchy")).expanduser()
        sites = list((prefix / "venv/lib").glob("python*/site-packages/mlx/coreml"))
        icd = Path(current.get("ANE_VK_ICD", "~/.local/share/mseries/ane/mesa-hk/share/vulkan/icd.d/asahi_icd.aarch64.json")).expanduser()
        if not (prefix / "venv/bin/python").is_file() or len(sites) != 1 or not icd.is_file():
            raise ValueError("Native ANE runtime/ICD is unavailable; preserve or restore its qualified setup")
        site = sites[0]
        lock = json.loads((site / "parakeet-reference.lock").read_text())
        cache = Path(current.get("MLX_OMARCHY_CACHE_DIR", str(HOME / ".cache/mlx-omarchy"))) / "parakeet-reference" / lock["model_repo"] / lock["model_revision"]
        if not all((cache / item["path"]).is_file() and (cache / item["path"]).stat().st_size == item["size"] for item in lock["files"]):
            raise ValueError("Native ANE pinned reference assets are missing or wrong-sized")
        if not (site.parent / "share/mlx-omarchy/parakeet-1/parakeet-runtime-pin.json").is_file():
            raise ValueError("Native ANE runtime assets pin is absent")
        additions.update(ANE_PREFIX=str(prefix), ANE_VK_ICD=str(icd))
    elif engine == "mlx":
        directory = BASE / "optional-mlx/model"
        modules = BASE / "optional-mlx/modules"
        spec = importlib.util.spec_from_file_location("optional_mlx_worker", BASE / "mlx-speech-worker.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.verify_assets(directory)
        metadata = list(modules.glob("mlx_audio-0.5.6.dist-info/METADATA"))
        prefix = Path(current.get("MLX_STT_PREFIX", "~/.local/share/mlx-omarchy")).expanduser()
        python = Path(current.get("MLX_STT_PYTHON", str(prefix / "venv/bin/python"))).expanduser()
        icd = Path(current.get("MLX_STT_VK_ICD", str(prefix / "vulkan/honeykrisp_icd.aarch64.json"))).expanduser()
        if not metadata or not python.is_file() or not icd.is_file():
            raise ValueError("Optional pinned MLX0.5.6 package, Python or qualified Vulkan ICD is absent")
        additions.update(MLX_STT_MODEL_DIR=str(directory), MLX_STT_MODULES=str(modules),
                         MLX_STT_PREFIX=str(prefix), MLX_STT_PYTHON=str(python), MLX_STT_VK_ICD=str(icd))
    else:
        raise ValueError("Unsupported speech engine")
    return additions


def bridge_ready():
    if systemctl("is-active", "--quiet", INPUT_SERVICE, check=False).returncode:
        raise ValueError("The existing focus-bound input bridge must be active before switching")
    subprocess.run(["/usr/bin/python3", str(BASE / "dictation-input-client.py"), "ready"],
                   check=True, capture_output=True, timeout=5)


def render(engine, mode, additions, warm_seconds=60):
    values = {"STREAM_ENGINE": engine, "STREAM_MODE": mode, "STREAM_THREADS": "4",
              "STREAM_BACKEND": "cpu", "STREAM_OUTPUT": "ibus", "STREAM_UNVERIFIED_FALLBACK": "0",
              "STREAM_IDLE_SECONDS": str(warm_seconds), **additions}
    def quote(value):
        # systemd syntax, not shell syntax; percent is a systemd specifier.
        return '"' + str(value).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return ("# Managed by mseries dictation-engine; rollback keeps other drop-ins.\n[Service]\n" +
            "".join("Environment=" + quote(key + "=" + value) + "\n" for key, value in values.items())).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def latest_change():
    pointer = STATE / "latest"
    if not pointer.is_file():
        return None, None
    name = pointer.read_text().strip()
    if Path(name).name != name or not name.endswith(".json"):
        raise ValueError("Invalid private speech transaction pointer")
    path = STATE / name
    return path, json.loads(path.read_text())


def assert_managed(change):
    if DROPIN.is_symlink() or not DROPIN.is_file() or sha(DROPIN.read_bytes()) != change["installed_sha256"]:
        raise ValueError("Owner changed the managed engine file; rollback/switch preserved it")


def save_change(path, change):
    atomic(path, (json.dumps(change, indent=2) + "\n").encode())


def wait_ready(engine):
    for _ in range(40):
        if not active():
            raise ValueError("Selected F5 service did not remain active")
        pid = int(systemctl("show", SERVICE, "-p", "MainPID", "--value").stdout.strip() or 0)
        row = lifecycle()
        if row and row.get("pid") == pid and row.get("phase") == "ready" and row.get("output") == "ibus":
            actual = environment()
            if actual.get("STREAM_ENGINE") == engine and actual.get("STREAM_UNVERIFIED_FALLBACK") == "0":
                bridge_ready()
                return
        time.sleep(.25)
    raise ValueError("Selected F5 engine did not report ready with strict Unicode output")


def restore_change(path, change, *, restart=True):
    if change.get("rolled_back"):
        raise ValueError("This engine change was already rolled back")
    assert_managed(change)
    original = base64.b64decode(change["before"], validate=True) if change["before"] is not None else None
    if original is not None and sha(original) != change["before_sha256"]:
        raise ValueError("Private engine backup digest mismatch; configuration preserved")
    if change.get("activation_started"):
        idle_capture()
        quiet_admission(change.get("previous_engine", "nemotron"))
        idle_capture()
        systemctl("stop", SERVICE)
    if change["before"] is None:
        DROPIN.unlink()
    else:
        atomic(DROPIN, original, change["before_mode"])
    if change.get("activation_started"):
        systemctl("daemon-reload")
    if change.get("activation_started") and restart and change["was_active"]:
        quiet_admission(change.get("previous_engine", "nemotron"))
        systemctl("start", SERVICE)
    change["rolled_back"] = True
    save_change(path, change)
    return change["was_active"]


def select(engine, mode=None, *, stage_only=False, was_active=None, warm_seconds=None):
    idle_capture()
    current = environment()
    additions = check_runtime(engine, current)
    if mode is None:
        mode = current.get("STREAM_MODE", "hold")
    if mode not in {"hold", "toggle"}:
        raise ValueError("Existing F5 mode is unsupported; choose --mode hold or toggle")
    if warm_seconds is None:
        warm_seconds = int(current.get("STREAM_IDLE_SECONDS", "180" if engine in {"ane", "mlx"} else "60"))
    if type(warm_seconds) is not int or not 0 <= warm_seconds <= 900:
        raise ValueError("Resident warm lifetime must be between0 and900seconds")
    _, previous = latest_change()
    if previous and not previous.get("rolled_back"):
        assert_managed(previous)
    if DROPIN.is_symlink():
        raise ValueError("Refusing managed engine symlink")
    if not stage_only:
        quiet_admission(engine)
        bridge_ready()
    data = render(engine, mode, additions, warm_seconds)
    path = STATE / (str(time.time_ns()) + "-" + uuid.uuid4().hex[:8] + ".json")
    before = DROPIN.read_bytes() if DROPIN.exists() else None
    change = {"engine": engine, "mode": mode, "warm_seconds": warm_seconds,
              "previous_engine": current.get("STREAM_ENGINE", "stream"),
              "was_active": active() if was_active is None else was_active,
              "before": base64.b64encode(before).decode() if before is not None else None,
              "before_mode": (DROPIN.stat().st_mode & 0o777) if before is not None else 0o644,
              "before_sha256": sha(before) if before is not None else None,
              "installed_sha256": sha(data), "stage_only": stage_only, "rolled_back": False,
              "activation_started": False}
    save_change(path, change)
    atomic(DROPIN, data, 0o644)
    atomic(STATE / "latest", (path.name + "\n").encode())
    if stage_only:
        return
    try:
        idle_capture()
        quiet_admission(engine)
        change["activation_started"] = True
        save_change(path, change)
        systemctl("stop", SERVICE)
        systemctl("daemon-reload")
        systemctl("start", SERVICE)
        wait_ready(engine)
    except Exception:
        restore_change(path, change)
        raise


@contextlib.contextmanager
def transaction_lock():
    if STATE.is_symlink():
        raise ValueError("Refusing a private-state symlink")
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.chmod(0o700)
    fd = os.open(STATE / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", action="store_true")
    action.add_argument("--select", choices=("nemotron", "ane", "mlx", "stream"))
    action.add_argument("--rollback", action="store_true")
    parser.add_argument("--mode", choices=("hold", "toggle"))
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--warm-seconds", type=int)
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise SystemExit("Run as the desktop user")
    if (args.mode or args.stage_only or args.warm_seconds is not None) and not args.select:
        parser.error("--mode/--stage-only/--warm-seconds require --select")
    if args.status:
        current = environment()
        _, change = latest_change()
        print(json.dumps({"running": active(), "configured_engine": current.get("STREAM_ENGINE", "stream"),
                          "mode": current.get("STREAM_MODE", "hold"),
                          "warm_seconds": current.get("STREAM_IDLE_SECONDS", "180" if current.get("STREAM_ENGINE") in {"ane", "mlx"} else "60"),
                          "managed_engine": change.get("engine") if change and not change.get("rolled_back") else None,
                          "private_backup_retained": bool(change)}, indent=2))
        return
    with transaction_lock():
        if args.rollback:
            path, change = latest_change()
            if not change:
                raise ValueError("No private engine rollback checkpoint exists")
            restore_change(path, change)
            print("Prior engine drop-in and running state restored; backup retained.")
        else:
            select(args.select, args.mode, stage_only=args.stage_only, warm_seconds=args.warm_seconds)
            print("Engine staged; service unchanged." if args.stage_only else "English F5 engine selected with strict focus-bound output.")


if __name__ == "__main__":
    main()
