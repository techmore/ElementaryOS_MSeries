#!/usr/bin/env python3
"""Compare Rust and Python keyboard lighting against fake UPower/logind."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "mseries/keyboard-backlight/backlight.py"
BINARY = None

GI_STUB = r'''from pathlib import Path
import json, os

def state():
    path = Path(os.environ["MSERIES_FIXTURE_STATE"])
    return path, json.loads(path.read_text())

class Variant:
    def __init__(self, signature, value): self.value = value
    def unpack(self): return self.value

class Bus:
    def call_sync(self, destination, path, interface, method, params, *args):
        _, data = state()
        if method == "Get": return Variant("v", (data["lid_closed"],))
        if method == "ListSessions":
            uid = int(os.environ["MSERIES_FIXTURE_UID"])
            return Variant("a", ([ ("c1", uid, "fixture", "seat0", "/session/c1") ],))
        if method == "GetAll":
            props = {"Type": "wayland", "Active": data["session_active"],
                     "LockedHint": data["locked"]}
            return Variant("a", (props,))
        raise RuntimeError(method)

class Proxy:
    def call_sync(self, method, args, *unused):
        path, data = state()
        if method == "GetMaxBrightness": return Variant("i", (data["maximum"],))
        if method == "GetBrightness": return Variant("i", (data["current"],))
        if method == "SetBrightness":
            data["current"] = args.unpack()[0]
            data["writes"] += 1
            path.write_text(json.dumps(data))
            return Variant("()", ())
        raise RuntimeError(method)

class Gio:
    class BusType: SYSTEM = 0
    class DBusProxyFlags: NONE = 0
    class DBusCallFlags: NONE = 0
    @staticmethod
    def bus_get_sync(*args): return Bus()
    class DBusProxy:
        @staticmethod
        def new_sync(*args): return Proxy()

class GLib:
    Error = Exception
    Variant = Variant
'''

BUSCTL = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
path = Path(os.environ["MSERIES_FIXTURE_STATE"])
data = json.loads(path.read_text())
args = sys.argv[1:]
if "get-property" in args:
    print("b", "true" if data["lid_closed"] else "false")
elif "call" in args:
    method = args[args.index("call") + 4]
    if method == "GetMaxBrightness": print("i", data["maximum"])
    elif method == "GetBrightness": print("i", data["current"])
    elif method == "SetBrightness":
        value = int(args[-1]); data["current"] = value; data["writes"] += 1
        path.write_text(json.dumps(data))
        print()
    else: raise SystemExit("unexpected busctl method " + method)
'''

LOGINCTL = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
data = json.loads(Path(os.environ["MSERIES_FIXTURE_STATE"]).read_text())
if sys.argv[1] == "list-sessions":
    print("c1", os.environ["MSERIES_FIXTURE_UID"], "fixture seat0 -")
elif sys.argv[1] == "show-session":
    print("Type=wayland")
    print("Active=" + ("yes" if data["session_active"] else "no"))
    print("LockedHint=" + ("yes" if data["locked"] else "no"))
'''


class KeyboardBacklightParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="keyboard-backlight-parity-")
        cls.root = Path(cls.temp.name)
        cls.path = cls.root / "als"
        (cls.path / "iio:device0").mkdir(parents=True)
        (cls.path / "iio:device0/name").write_text("aop-sensors-als\n")
        (cls.path / "iio:device0/in_illuminance_input").write_text("8\n")
        cls.bin = cls.root / "bin"
        cls.bin.mkdir()
        for name, body in (("busctl", BUSCTL), ("loginctl", LOGINCTL)):
            tool = cls.bin / name
            tool.write_text(body)
            tool.chmod(0o755)
        stub = cls.root / "stub/gi/repository"
        stub.mkdir(parents=True)
        (stub.parent / "__init__.py").write_text("")
        (stub / "__init__.py").write_text(GI_STUB + "\n")
        cls.env = {
            **os.environ,
            "PATH": f"{cls.bin}:{os.environ.get('PATH', '')}",
            "PYTHONPATH": str(stub.parents[1]),
            "MSERIES_FIXTURE_UID": str(os.getuid()),
        }
        cls.binary = BINARY

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def compare(self, label, **overrides):
        baseline = {
            "maximum": 255,
            "current": 100,
            "lid_closed": False,
            "session_active": True,
            "locked": False,
            "writes": 0,
            **overrides,
        }
        results = []
        states = []
        for implementation in ("python", "rust"):
            state_path = self.root / f"{label}-{implementation}.json"
            state_path.write_text(json.dumps(baseline))
            env = {**self.env, "MSERIES_FIXTURE_STATE": str(state_path)}
            if implementation == "python":
                command = [sys.executable, str(PYTHON), "--once", "--sensor-root", str(self.path)]
            else:
                command = [str(self.binary), "--once", "--sensor-root", str(self.path)]
            result = subprocess.run(command, text=True, capture_output=True, env=env)
            results.append((result.returncode, result.stdout, result.stderr))
            states.append(json.loads(state_path.read_text()))
        self.assertEqual(results[0], results[1])
        self.assertEqual(states[0], states[1])
        return results[0], states[0]

    def test_adjusts_only_for_active_unlocked_open_lid(self):
        result, state = self.compare("adjust")
        self.assertEqual(result[0], 0)
        self.assertEqual((state["current"], state["writes"]), (255, 1))
        for label, overrides in (
            ("closed", {"lid_closed": True}),
            ("locked", {"locked": True}),
            ("inactive", {"session_active": False}),
        ):
            _, state = self.compare(label, **overrides)
            self.assertEqual((state["current"], state["writes"]), (100, 0))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test-parity.py /path/to/mseries-keyboard-backlight-rs")
    BINARY = Path(sys.argv[1]).resolve()
    sys.argv = [sys.argv[0]]
    unittest.main()
