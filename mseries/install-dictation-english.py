#!/usr/bin/python3
"""Stage or activate English-only quiet F5 speech; retain a private rollback.

Requires the existing qualified native CPU runtime and Unicode input bridge.
Does not change input-method preferences, audio routing, other profiles or windows.
--stage-only is the default. Optional MLX assets/packages are copied from explicit
local sources, never installed into the owner's Python environment.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "dictation" if (HERE / "dictation").is_dir() else HERE
HOME = Path.home()
BASE = HOME / ".local/share/mseries/stream"
STATE = HOME / ".local/state/mseries-dictation-english"
RUNTIME_FILES = (
    "stream-dictate.py", "dictation-input.py", "dictation-input-client.py", "dictation_status.py",
    "dictation_resources.py", "dictation_model.py", "dictation_ane.py", "ane-worker-shim.py",
    "dictation_mlx.py", "mlx-speech-worker.py", "dictation-engine.py", "dictation-launch.py",
    "dictation_review.py", "dictation_pipeline.py", "dictation_live.py", "dictation-panel.py",
)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helper():
    source = HERE / "install-dictation-input.py"
    if not source.is_file():
        source = BASE / "dictation-manage.py"
    module = load("english_input_payload", source)
    # Helpers use module-global destinations; keep an installed manager correct.
    module.HOME, module.BASE = HOME, BASE
    module.PANEL_DESKTOP = HOME / ".local/share/applications/org.techmore.Dictation.desktop"
    return module


def selector():
    source = SOURCE / "dictation-engine.py"
    if not source.is_file():
        source = BASE / "dictation-engine.py"
    module = load("english_engine_selector", source)
    module.HOME, module.BASE = HOME, BASE
    return module


def fetch_model(engine, local_source=None, *, download=False):
    """Return a verified local artifact; pinned HTTPS download is opt-in."""
    target = BASE / "models" / engine.NEMOTRON
    if target.is_file():
        engine.verify_file(target, engine.NEMOTRON_SHA256)
        return target
    if local_source:
        source = Path(local_source).expanduser()
        if source.is_dir():
            source = source / engine.NEMOTRON
        engine.verify_file(source, engine.NEMOTRON_SHA256)
        return source
    if not download:
        raise ValueError("Provide --model-source for the pinned uppercase-Q8_0 artifact, or --download-model")
    url = ("https://huggingface.co/handy-computer/nemotron-speech-streaming-en-0.6b-gguf/resolve/"
           "7df420cc3fb915a3b334560dac712af44fc41ef5/" + engine.NEMOTRON)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    fd, name = tempfile.mkstemp(prefix="nemotron-", suffix=".part", dir=STATE)
    try:
        with os.fdopen(fd, "wb") as output, urllib.request.urlopen(url, timeout=60) as response:
            shutil.copyfileobj(response, output, length=4 * 1024 * 1024)
        engine.verify_file(Path(name), engine.NEMOTRON_SHA256)
        final = STATE / engine.NEMOTRON
        os.replace(name, final)
        return final
    finally:
        if os.path.exists(name):
            os.unlink(name)


def optional_mlx(payload, model_source, modules_source):
    if bool(model_source) != bool(modules_source):
        raise ValueError("Provide both --mlx-model-dir and --mlx-modules to retain the optional MLX engine")
    if not model_source:
        return
    worker = load("english_optional_mlx", SOURCE / "mlx-speech-worker.py")
    directory = Path(model_source).expanduser()
    modules = Path(modules_source).expanduser()
    worker.verify_assets(directory)
    if not (modules / "mlx_audio-0.5.6.dist-info/METADATA").is_file() or not (modules / "mlx_audio").is_dir():
        raise ValueError("Optional Parakeet engine requires the separate pinned mlx-audio0.5.6 overlay")
    for name in worker.MODEL_FILES:
        install_file(payload, BASE / "optional-mlx/model" / name, directory / name)
    for package in (modules / "mlx_audio", modules / "mlx_audio-0.5.6.dist-info"):
        for source in sorted(package.rglob("*")):
            if source.is_symlink():
                raise ValueError("Optional MLX package overlay contains a symlink")
            if source.is_file() and "__pycache__" not in source.parts and source.suffix != ".pyc":
                payload.install(BASE / "optional-mlx/modules" / source.relative_to(modules), source.read_bytes(), 0o600)


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def install_file(payload, path, source, mode=0o600):
    """Payload-compatible transaction without materializing gigabyte weights."""
    key = str(path)
    if path.is_symlink():
        raise ValueError("Refusing a managed model symlink")
    if key not in payload.data["files"]:
        row = {"existed": path.exists()}
        if path.exists():
            backup = hashlib.sha256(key.encode()).hexdigest() + ".backup"
            payload.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
            with path.open("rb") as reader, (payload.directory / backup).open("wb") as writer:
                os.fchmod(writer.fileno(), 0o600)
                shutil.copyfileobj(reader, writer, length=4 * 1024 * 1024)
            row.update(backup=backup, sha256=file_sha(path), mode=stat.S_IMODE(path.stat().st_mode))
        payload.data["files"][key] = row
        payload.save()
    row = payload.data["files"][key]
    expected = row.get("installed_sha256", row.get("sha256"))
    if path.exists() != bool(row.get("installed_sha256") or row["existed"]) or (path.exists() and file_sha(path) != expected):
        raise ValueError("Owner changed a managed model; reconcile before upgrading")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as writer, source.open("rb") as reader:
            os.fchmod(writer.fileno(), mode)
            shutil.copyfileobj(reader, writer, length=4 * 1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    row["installed_sha256"] = file_sha(path)
    payload.save()


def validate_restore(payload):
    """Validate every file and backup using bounded reads, including model weights."""
    for name, row in payload.data["files"].items():
        path = Path(name)
        expected = row.get("installed_sha256", row.get("sha256"))
        exists = bool(row.get("installed_sha256") or row["existed"])
        if path.is_symlink() or path.exists() != exists or (path.exists() and file_sha(path) != expected):
            raise ValueError("Owner changed a managed file; rollback preserved it")
        if row["existed"] and file_sha(payload.directory / row["backup"]) != row["sha256"]:
            raise ValueError("Private payload backup digest mismatch")


def restore_files(payload):
    validate_restore(payload)
    for name, row in payload.data["files"].items():
        path = Path(name)
        if row["existed"]:
            fd, temporary = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as writer, (payload.directory / row["backup"]).open("rb") as reader:
                    os.fchmod(writer.fileno(), row["mode"])
                    shutil.copyfileobj(reader, writer, length=4 * 1024 * 1024)
                    writer.flush()
                    os.fsync(writer.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        elif path.exists():
            path.unlink()
        row.pop("installed_sha256", None)
    payload.save()


def input_engine():
    return subprocess.run(["ibus", "engine"], capture_output=True, text=True,
                          check=False, timeout=5).stdout.strip()


def restore_input_engine(previous):
    # Preserve any already valid selection (including an owner change).
    current = input_engine()
    if current not in {"", "dummy", "mseries-dictation"}:
        return
    client = ["/usr/bin/python3", str(BASE / "dictation-input-client.py")]
    if previous not in {"", "dummy", "mseries-dictation"}:
        subprocess.run([*client, "select", previous], check=True, capture_output=True, timeout=5)
    else:
        subprocess.run([*client, "repair-native"], check=True, capture_output=True, timeout=5)


def restart_bridge(engine, previous):
    engine.systemctl("restart", engine.INPUT_SERVICE)
    restore_input_engine(previous)
    engine.bridge_ready()


def stage(payload, manager, engine, *, model_source=None, download=False, mlx_model=None, mlx_modules=None, speech_only=False):
    engine.idle_capture()
    if engine.active():
        raise ValueError("Stop the owned idle F5 service or use --activate before staging its live payload")
    if not (BASE / "venv/bin/python").is_file():
        raise ValueError("Install the pinned native streaming runtime first")
    artifact = fetch_model(engine, model_source, download=download)
    # Preserve the first pre-upgrade payload and previous active state.
    if not payload.data["metadata"]:
        payload.data["metadata"] = {"stream_active": engine.active(), "activation_started": False,
            "input_active": engine.systemctl("is-active", "--quiet", engine.INPUT_SERVICE, check=False).returncode == 0,
            "input_engine": input_engine()}
        payload.save()
    for name in RUNTIME_FILES:
        payload.install(BASE / name, (SOURCE / name).read_bytes(), 0o755 if name.endswith(".py") else 0o644)
    for name in (() if speech_only else ("dictation_voice.py", "voice-assistant.py")):
        if (SOURCE / name).is_file():
            payload.install(BASE / name, (SOURCE / name).read_bytes(), 0o755)
    machine = HERE / "local-ai/machine.py"
    if not machine.is_file():
        machine = BASE / "machine.py"
    payload.install(BASE / "machine.py", machine.read_bytes(), 0o644)
    input_source = HERE / "install-dictation-input.py"
    if input_source.is_file():
        payload.install(BASE / "dictation-manage.py", input_source.read_bytes(), 0o755)
    payload.install(BASE / "dictation-english-manage.py", Path(__file__).read_bytes(), 0o755)
    # Payload.install validates owner edits and retains backups. This model is
    # large: only materialize bytes when a copy is actually needed.
    target = BASE / "models" / engine.NEMOTRON
    if artifact != target:
        install_file(payload, target, artifact)
    if not speech_only:
        optional_mlx(payload, mlx_model, mlx_modules)
    manager.install_panel(payload, speech_only=speech_only)
    payload.install(HOME / ".config/systemd/user" / engine.INPUT_SERVICE,
                    (SOURCE / engine.INPUT_SERVICE).read_bytes(), 0o644)
    if not speech_only and (SOURCE / "voice-assistant.py").is_file():
        def quote(value):
            return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$") + '"'
        desktop = ("[Desktop Entry]\nType=Application\nName=Voice Assistant\n"
                   "Comment=Optional English voice replies from the local assistant\n"
                   "Icon=audio-input-microphone\nExec=" + " ".join(quote(value) for value in (
                       "/usr/bin/python3", BASE / "dictation-launch.py", "/usr/bin/python3", BASE / "voice-assistant.py")) +
                   "\nTerminal=false\nCategories=Utility;Accessibility;\nStartupNotify=true\n")
        payload.install(HOME / ".local/share/applications/org.techmore.VoiceAssistant.desktop", desktop.encode(), 0o644)


def state_directory(speech_only=False):
    return HOME / ".local/state/mseries-dictation-stt-v0.0.1" if speech_only else STATE


def selector_marker(engine):
    path, change = engine.latest_change()
    if path is None:
        if change is not None:
            raise ValueError("Ambiguous selector checkpoint; configuration preserved")
        return None
    return {"name": path.name, "sha256": file_sha(path)}


def dropin_digest(engine):
    if engine.DROPIN.is_symlink():
        raise ValueError("Owner changed the managed engine file; configuration preserved")
    return file_sha(engine.DROPIN) if engine.DROPIN.exists() else None


def remember_selector(payload, engine):
    metadata = payload.data["metadata"]
    metadata.update(selector_schema=1, selector_before=selector_marker(engine),
                    selector_owned=None, selector_before_dropin=dropin_digest(engine))
    # A pre-existing managed selection must itself still match its receipt.
    path, change = engine.latest_change()
    if change and not change.get("rolled_back"):
        engine.assert_managed(change)
    payload.save()


def capture_selector(payload, engine):
    """Called only under the shared selector lock, after our select attempt."""
    metadata = payload.data["metadata"]
    marker = selector_marker(engine)
    if marker != metadata["selector_before"]:
        if marker is None or (metadata["selector_before"] and marker["name"] == metadata["selector_before"]["name"]):
            raise ValueError("Owner changed the previous selector receipt; rollback preserved it")
        metadata["selector_owned"] = marker
        payload.save()


def validate_selector_restore(payload, engine):
    metadata = payload.data["metadata"]
    if metadata.get("selector_schema") != 1 or "selector_before_dropin" not in metadata:
        raise ValueError("Legacy ambiguous engine checkpoint: no service was stopped; reconcile the previous deployment first")
    expected = metadata.get("selector_owned") or metadata.get("selector_before")
    if selector_marker(engine) != expected:
        raise ValueError("Owner selected or changed another engine; rollback preserved it")
    path, change = engine.latest_change()
    if metadata.get("selector_owned") and change and not change.get("rolled_back"):
        engine.assert_managed(change)
        # Verify the rollback bytes before any service is touched.
        original = base64.b64decode(change["before"], validate=True) if change["before"] is not None else None
        original_sha = hashlib.sha256(original).hexdigest() if original is not None else None
        if original is not None and original_sha != change["before_sha256"]:
            raise ValueError("Private engine backup digest mismatch; configuration preserved")
        if original_sha != metadata["selector_before_dropin"]:
            raise ValueError("Engine rollback does not match this update's baseline")
        return path, change
    if dropin_digest(engine) != metadata["selector_before_dropin"]:
        raise ValueError("Owner changed the previous engine configuration; rollback preserved it")
    return None, None


def restore_payload(payload, engine):
    validate_restore(payload)  # Check all owner edits/backups before stopping anything.
    if not payload.data["metadata"].get("activation_started"):
        restore_files(payload)
        return  # A stage-only rollback never changes running services.
    path, change = validate_selector_restore(payload, engine)
    engine.idle_capture()
    engine.quiet_admission()
    engine.idle_capture()
    engine.systemctl("stop", engine.SERVICE)
    previous_input = input_engine()
    engine.systemctl("stop", engine.INPUT_SERVICE)
    if change:
        engine.restore_change(path, change, restart=False)
    restore_files(payload)
    engine.systemctl("daemon-reload")
    if payload.data["metadata"].get("input_active"):
        engine.systemctl("start", engine.INPUT_SERVICE)
        restore_input_engine(previous_input or payload.data["metadata"].get("input_engine", ""))
        engine.bridge_ready()
    if payload.data["metadata"].get("stream_active"):
        engine.quiet_admission()
        engine.systemctl("start", engine.SERVICE)
    payload.data["metadata"]["activation_started"] = False
    payload.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--stage-only", action="store_true")
    action.add_argument("--activate", choices=("nemotron", "ane", "mlx", "stream"))
    action.add_argument("--rollback", action="store_true")
    parser.add_argument("--mode", choices=("hold", "toggle"))
    parser.add_argument("--warm-seconds", type=int)
    parser.add_argument("--model-source", type=Path)
    parser.add_argument("--download-model", action="store_true")
    parser.add_argument("--mlx-model-dir", type=Path)
    parser.add_argument("--mlx-modules", type=Path)
    parser.add_argument("--speech-only", action="store_true", help="v0.0.1 CPU English STT update; exclude voice/LLM additions and retain a separate rollback")
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise SystemExit("Run as the desktop user")
    if (args.mode or args.warm_seconds is not None) and not args.activate:
        parser.error("--mode/--warm-seconds require --activate")
    if args.speech_only and (args.mlx_model_dir or args.mlx_modules or args.activate not in (None, "nemotron")):
        parser.error("--speech-only accepts only Nemotron CPU and no optional MLX asset copy")
    manager, engine = helper(), selector()
    payload = manager.Payload(state_directory(args.speech_only))
    with engine.transaction_lock():
        if args.rollback:
            if not payload.data["metadata"]:
                raise ValueError("No English deployment checkpoint exists")
            restore_payload(payload, engine)
            print("Previous English payload and engine restored; private backups retained.")
            return
        if payload.data["metadata"].get("activation_started"):
            raise ValueError("This version's deployment checkpoint is active; roll it back before applying again")
        if args.activate:
            engine.idle_capture()
            engine.quiet_admission(args.activate)
            if not payload.data["metadata"]:
                payload.data["metadata"] = {"stream_active": engine.active(), "activation_started": False,
                    "input_active": engine.systemctl("is-active", "--quiet", engine.INPUT_SERVICE, check=False).returncode == 0,
                    "input_engine": input_engine()}
            remember_selector(payload, engine)
            payload.data["metadata"]["activation_started"] = True
            payload.save()
            try:
                engine.idle_capture()
                engine.quiet_admission(args.activate)
                previous_input = input_engine()
                engine.systemctl("stop", engine.SERVICE)
                stage(payload, manager, engine, model_source=args.model_source, download=args.download_model,
                      mlx_model=args.mlx_model_dir, mlx_modules=args.mlx_modules, speech_only=args.speech_only)
                engine.systemctl("daemon-reload")
                restart_bridge(engine, previous_input)
                engine.select(args.activate, args.mode, was_active=payload.data["metadata"]["stream_active"], warm_seconds=args.warm_seconds)
                capture_selector(payload, engine)
            except Exception:
                capture_selector(payload, engine)
                restore_payload(payload, engine)
                raise
            print("English-only F5 payload and selected engine deployed; live microphone accuracy remains an owner acceptance check.")
        else:
            stage(payload, manager, engine, model_source=args.model_source, download=args.download_model,
                  mlx_model=args.mlx_model_dir, mlx_modules=args.mlx_modules, speech_only=args.speech_only)
            print("English F5 payload/model staged with private backup; services and preferences unchanged.")


if __name__ == "__main__":
    main()
