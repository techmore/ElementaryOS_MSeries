#!/usr/bin/env python3
"""Exercise the Rust D-Bus bridge against a private GIO Mutter fixture."""

import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

FIXTURE = Path(__file__).resolve().parent / "tests" / "mock-mutter.c"
BRIDGE_NAME = "org.gnome.Shell.Brightness"
BRIDGE_PATH = "/org/gnome/Shell/Brightness"
MOCK_NAME = "org.gnome.Mutter.DisplayConfig"
MOCK_PATH = "/org/gnome/Mutter/DisplayConfig"
MOCK_IFACE = "org.example.MockDisplay"


def run(command, env, check=True):
    result = subprocess.run(command, text=True, capture_output=True, env=env)
    if check and result.returncode:
        raise AssertionError(f"{command!r} failed ({result.returncode}): {result.stderr}")
    return result


def gdbus(env, service, path, method, *arguments, check=True):
    return run([
        "gdbus", "call", "--session", "--dest", service,
        "--object-path", path, "--method", method, *arguments,
    ], env, check=check)


def current_value(env):
    result = gdbus(env, MOCK_NAME, MOCK_PATH, f"{MOCK_IFACE}.GetValue")
    match = re.search(r"\((-?\d+),\)", result.stdout)
    if not match:
        raise AssertionError(f"unexpected mock brightness reply: {result.stdout!r}")
    return int(match.group(1))


def wait_for_service(env, process):
    deadline = time.monotonic() + 5
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"Rust bridge exited early: {process.stderr.read()}")
        result = gdbus(env, BRIDGE_NAME, BRIDGE_PATH,
            "org.freedesktop.DBus.Properties.Get", "org.gnome.Shell.Brightness",
            "HasBrightnessControl", check=False)
        if result.returncode == 0 and "true" in result.stdout:
            return
        last_error = result.stderr
        time.sleep(0.05)
    raise AssertionError(f"Rust brightness D-Bus name did not become ready: {last_error}")


def inside(binary, schema_dir, mock_binary):
    env = {
        **os.environ,
        "GSETTINGS_SCHEMA_DIR": str(schema_dir),
        "GSETTINGS_BACKEND": "keyfile",
        "XDG_CONFIG_HOME": str(schema_dir.parent / "xdg-config"),
    }
    mock = subprocess.Popen([str(mock_binary)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    bridge = None
    monitor = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if mock.poll() is not None:
                raise AssertionError(f"mock Mutter exited: {mock.stderr.read()}")
            ping = gdbus(env, MOCK_NAME, MOCK_PATH, f"{MOCK_IFACE}.Ping", check=False)
            if ping.returncode == 0:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("mock Mutter did not acquire its session-bus name")

        bridge = subprocess.Popen([str(binary)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        wait_for_service(env, bridge)
        assert current_value(env) == 315

        gdbus(env, BRIDGE_NAME, BRIDGE_PATH, f"{BRIDGE_NAME}.SetDimming", "true")
        assert current_value(env) == 150
        gdbus(env, BRIDGE_NAME, BRIDGE_PATH, f"{BRIDGE_NAME}.SetDimming", "true")
        assert current_value(env) == 150
        gdbus(env, BRIDGE_NAME, BRIDGE_PATH, f"{BRIDGE_NAME}.SetDimming", "false")
        assert current_value(env) == 315

        # An external user brightness change while dimmed must invalidate the
        # saved level, emit BrightnessChanged, and survive the later undim.
        gdbus(env, BRIDGE_NAME, BRIDGE_PATH, f"{BRIDGE_NAME}.SetDimming", "true")
        monitor = subprocess.Popen([
            "gdbus", "monitor", "--session", "--dest", BRIDGE_NAME,
            "--object-path", BRIDGE_PATH,
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        time.sleep(0.25)
        gdbus(env, MOCK_NAME, MOCK_PATH, f"{MOCK_IFACE}.ExternalSet", "220")
        time.sleep(0.25)
        monitor.terminate()
        monitor_output, monitor_error = monitor.communicate(timeout=3)
        monitor = None
        if "BrightnessChanged" not in monitor_output:
            raise AssertionError(f"missing BrightnessChanged signal: {monitor_output!r} {monitor_error!r}")
        gdbus(env, BRIDGE_NAME, BRIDGE_PATH, f"{BRIDGE_NAME}.SetDimming", "false")
        assert current_value(env) == 220

        gdbus(env, BRIDGE_NAME, BRIDGE_PATH, f"{BRIDGE_NAME}.SetAutoBrightnessTarget", "0.5")
        assert current_value(env) == 252  # Python round(252.5) uses ties-to-even.
        invalid = gdbus(env, BRIDGE_NAME, BRIDGE_PATH,
            f"{BRIDGE_NAME}.SetAutoBrightnessTarget", "1.1", check=False)
        if invalid.returncode == 0 or "org.gnome.Shell.Brightness.Error" not in invalid.stderr:
            raise AssertionError(f"invalid target did not return the bridge D-Bus error: {invalid.stderr!r}")
        assert current_value(env) == 252

        run(["gsettings", "set", "org.gnome.settings-daemon.plugins.power", "ambient-enabled", "false"], env)
        gdbus(env, BRIDGE_NAME, BRIDGE_PATH, f"{BRIDGE_NAME}.SetAutoBrightnessTarget", "0.9")
        assert current_value(env) == 252
        run(["gsettings", "set", "org.gnome.settings-daemon.plugins.power", "idle-dim", "false"], env)
        gdbus(env, BRIDGE_NAME, BRIDGE_PATH, f"{BRIDGE_NAME}.SetDimming", "true")
        assert current_value(env) == 252
    finally:
        if monitor is not None:
            monitor.terminate()
            monitor.communicate(timeout=3)
        for process in (bridge, mock):
            if process is not None and process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--inside":
        inside(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    elif len(sys.argv) == 2:
        binary = Path(sys.argv[1]).resolve()
        with tempfile.TemporaryDirectory(prefix="brightness-bridge-runtime-") as temporary:
            root = Path(temporary)
            schemas = root / "schemas"
            schemas.mkdir()
            schema = schemas / "org.gnome.settings-daemon.plugins.power.gschema.xml"
            schema.write_text('''<schemalist><schema id="org.gnome.settings-daemon.plugins.power" path="/org/gnome/settings-daemon/plugins/power/">
              <key name="idle-dim" type="b"><default>true</default></key>
              <key name="idle-brightness" type="i"><default>30</default></key>
              <key name="ambient-enabled" type="b"><default>true</default></key>
            </schema></schemalist>''')
            run(["glib-compile-schemas", str(schemas)], os.environ)
            mock = root / "mock-mutter"
            flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "gio-2.0"], text=True).split()
            run(["cc", str(FIXTURE), "-o", str(mock), *flags], os.environ)
            completed = subprocess.run([
                "dbus-run-session", "--", sys.executable, str(Path(__file__).resolve()),
                "--inside", str(binary), str(schemas), str(mock),
            ], text=True, capture_output=True, timeout=25, env=os.environ)
            if completed.returncode:
                raise SystemExit(completed.stdout + completed.stderr)
            print("Rust brightness D-Bus runtime parity passed against the private Mutter fixture")
    else:
        raise SystemExit("usage: test-dbus-runtime.py /path/to/mseries-brightness-bridge-rs")
