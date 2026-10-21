#!/usr/bin/env python3
"""Dock writers read size-system tokens and behave exactly as before at the default step (#332 phase 2).

Each script that used to hard-code a dock icon size is run against a stand-in
`mseries-ui-scale` and compared with its old literal:

    display-space/dock_profile.py   40  -> "work" token (compact floating dock)
    dock-trial/dock-trial.py        48  -> "native" token
    dock-policy/enable-permanent.sh 48  -> "native" token

When the size system is absent, unmanaged (exit 3) or returns garbage the old literal
still applies. At the default step the token must equal the old literal.
"""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MSERIES = HERE.parent
SYSTEM = json.loads((HERE / "size-system.json").read_text(encoding="utf-8"))

# The literals the scripts hard-coded before this change.
OLD = {"dock_profile": 40, "dock_trial": 48, "enable_permanent": 48}
MODE = {"dock_profile": "work", "dock_trial": "native", "enable_permanent": "native"}


def step(name):
    return next(s for s in SYSTEM["steps"] if s["name"] == name)


def have_gi():
    try:
        import gi  # noqa: F401
        return True
    except ImportError:
        return False


class Sandbox(unittest.TestCase):
    """A throwaway HOME whose PATH starts with a bin directory we control."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.bin = Path(self.temp.name) / "bin"
        (self.home / ".local/bin").mkdir(parents=True)
        self.bin.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / "config"),
                        XDG_STATE_HOME=str(self.home / "state"), PATH=f"{self.bin}:/usr/bin:/bin")
        for name in ("MSERIES_UI_SCALE_SYSTEM", "XDG_DATA_HOME"):
            self.env.pop(name, None)

    def executable(self, directory, name, body):
        path = directory / name
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def install_tool(self, scenario):
        """Place a stand-in mseries-ui-scale. scenario: None (absent), 'unmanaged', 'garbage', or a step name."""
        (self.home / ".local/bin/mseries-ui-scale").unlink(missing_ok=True)
        if scenario is None:
            return
        if scenario == "unmanaged":
            body = "exit 3\n"
        elif scenario == "garbage":
            body = "echo not-a-number\n"
        else:
            tokens = step(scenario)["dock"]
            body = 'case "$2" in\n' + "".join(f"  {mode}) echo {size} ;;\n" for mode, size in tokens.items()) + \
                   "  *) exit 64 ;;\nesac\n"
        self.executable(self.home / ".local/bin", "mseries-ui-scale", 'test "$1" = --dock-size || exit 64\n' + body)

    def expectations(self, name):
        """(scenario, expected size) pairs for one script."""
        old = OLD[name]
        yield None, old
        yield "unmanaged", old
        yield "garbage", old
        yield "default", old                         # identical at the default step
        for scenario in ("compact", "large", "largest"):
            yield scenario, step(scenario)["dock"][MODE[name]]


class Tokens(unittest.TestCase):
    def test_default_step_tokens_equal_the_old_literals(self):
        default = step(SYSTEM["default_step"])["dock"]
        for name, old in OLD.items():
            self.assertEqual(default[MODE[name]], old, name)


@unittest.skipUnless(have_gi() and shutil.which("glib-compile-schemas") and shutil.which("gsettings"),
                     "needs python3-gi and GLib schema tools")
class DockProfile(Sandbox):
    SCHEMA = """<schemalist><schema id="io.elementary.dock" path="/io/elementary/dock/">
<key name="taskbar-mode" type="b"><default>false</default></key>
<key name="icon-size" type="i"><default>48</default></key>
<key name="autohide-mode" type="s"><default>'never'</default></key>
</schema></schemalist>"""

    def setUp(self):
        super().setUp()
        schemas = self.home / ".local/lib/mseries/dock/share/glib-2.0/schemas"
        schemas.mkdir(parents=True)
        (schemas / "dock.gschema.xml").write_text(self.SCHEMA, encoding="utf-8")
        subprocess.run(["glib-compile-schemas", str(schemas)], check=True)
        self.env.update(GSETTINGS_BACKEND="keyfile", GSETTINGS_SCHEMA_DIR=str(schemas))

    def run_profile(self, *args):
        return subprocess.run([sys.executable, str(MSERIES / "display-space/dock_profile.py"), *args],
                              env=self.env, capture_output=True, text=True, check=True).stdout

    def icon_size(self):
        return int(subprocess.check_output(["gsettings", "get", "io.elementary.dock", "icon-size"],
                                           env=self.env, text=True))

    def test_new_value_matches_old_at_default_and_follows_tokens(self):
        for scenario, expected in self.expectations("dock_profile"):
            with self.subTest(scenario=scenario):
                self.install_tool(scenario)
                out = self.run_profile()
                self.assertEqual(self.icon_size(), expected)
                self.assertIn(f"{expected} px icons", out)
                self.run_profile("--revert")
                self.assertEqual(self.icon_size(), 48)


@unittest.skipUnless(have_gi(), "needs python3-gi")
class DockTrial(Sandbox):
    def load(self):
        loader = importlib.machinery.SourceFileLoader("dock_trial_under_test", str(MSERIES / "dock-trial/dock-trial.py"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        module.HOME = self.home
        return module

    def test_new_value_matches_old_at_default_and_follows_tokens(self):
        trial = self.load()
        old_path = os.environ["PATH"]
        os.environ["PATH"] = self.env["PATH"]
        self.addCleanup(os.environ.__setitem__, "PATH", old_path)
        self.assertEqual(trial.DEFAULT_ICON_SIZE, OLD["dock_trial"])
        for scenario, expected in self.expectations("dock_trial"):
            with self.subTest(scenario=scenario):
                self.install_tool(scenario)
                self.assertEqual(trial.size_system_dock("native", trial.DEFAULT_ICON_SIZE), expected)


class EnablePermanent(Sandbox):
    def run_script(self):
        log = Path(self.temp.name) / "gsettings.log"
        log.write_text("")
        self.executable(self.bin, "gsettings", f'echo "$*" >> {log}\n')
        self.executable(self.bin, "systemctl", 'case "$*" in *is-active*) echo active ;; esac\n')
        self.executable(self.bin, "pgrep", "exit 1\n")
        subprocess.run(["sh", str(MSERIES / "dock-policy/enable-permanent.sh")], env=self.env,
                       capture_output=True, text=True, check=True)
        sizes = [line.split()[-1] for line in log.read_text().splitlines()
                 if line.startswith("set io.elementary.dock icon-size")]
        self.assertEqual(len(sizes), 1, log.read_text())
        return int(sizes[0])

    def test_new_value_matches_old_at_default_and_follows_tokens(self):
        for scenario, expected in self.expectations("enable_permanent"):
            with self.subTest(scenario=scenario):
                self.install_tool(scenario)
                self.assertEqual(self.run_script(), expected)


if __name__ == "__main__":
    unittest.main()
