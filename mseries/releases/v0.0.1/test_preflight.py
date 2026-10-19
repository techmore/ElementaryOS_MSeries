#!/usr/bin/python3
"""Synthetic filesystem/command preflight contracts; no live host inspection."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('f5_release_preflight', Path(__file__).with_name('preflight.py'))
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mseries-preflight-package-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = self.root / 'mseries/example.py'
        self.payload.parent.mkdir()
        self.payload.write_bytes(b'print("synthetic package")\n')
        self.manifest = {'version': '0.0.1', 'source_commit': 'a' * 40,
                         'files': {'mseries/example.py': hashlib.sha256(self.payload.read_bytes()).hexdigest()}}
        self.save()

    def save(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))

    def valid(self):
        return preflight.verify_package(self.root)['passed']

    def test_exact_files_and_digests(self):
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*'))
        self.assertTrue(self.valid())
        self.assertEqual(before, sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*')))
        self.payload.write_bytes(b'changed')
        self.assertFalse(self.valid())
        self.payload.unlink()
        self.assertFalse(self.valid())

    def test_extra_unlisted_payload_and_special_file(self):
        (self.root / 'extra.txt').write_text('unlisted')
        self.assertFalse(self.valid())
        (self.root / 'extra.txt').unlink()
        os.mkfifo(self.root / 'pipe')
        self.assertFalse(self.valid())

    def test_links_cannot_escape_or_hide_as_directories(self):
        self.payload.unlink()
        self.payload.symlink_to('/etc/passwd')
        self.assertFalse(self.valid())
        self.payload.unlink()
        self.payload.write_text('safe')
        self.manifest['files']['mseries/example.py'] = hashlib.sha256(self.payload.read_bytes()).hexdigest()
        self.save()
        (self.root / 'linked-directory').symlink_to(self.root / 'mseries', target_is_directory=True)
        self.assertFalse(self.valid())
        (self.root / 'linked-directory').unlink()
        manifest = self.root / 'manifest.json'
        manifest.rename(self.root / 'manifest-real')
        manifest.symlink_to(self.root / 'manifest-real')
        self.assertFalse(self.valid())

    def test_manifest_identity_paths_digests_and_duplicates(self):
        for update in ({'version': '0.0.2'}, {'source_commit': 'branch'}, {'files': {}},
                       {'files': {'../escape': 'a' * 64}}, {'files': {'/absolute': 'a' * 64}},
                       {'files': {'mseries//example.py': 'a' * 64}},
                       {'files': {'mseries/./example.py': 'a' * 64}},
                       {'files': {'mseries\\example.py': 'a' * 64}},
                       {'files': {'manifest.json': 'a' * 64}},
                       {'files': {'mseries/example.py': 'not-a-digest'}}):
            with self.subTest(update=update):
                original = dict(self.manifest)
                self.manifest.update(update)
                self.save()
                self.assertFalse(self.valid())
                self.manifest = original
        (self.root / 'manifest.json').write_text('{"version":"0.0.1","version":"0.0.1"}')
        self.assertFalse(self.valid())

    def test_link_swap_after_inventory_is_refused(self):
        original_open = preflight.package_file
        def swapped(root, name):
            if name == 'mseries/example.py':
                self.payload.unlink()
                self.payload.symlink_to('/etc/passwd')
            return original_open(root, name)
        with patch.object(preflight, 'package_file', swapped):
            self.assertFalse(self.valid())

    def test_integrity_failure_never_inspects_host_or_exposes_paths(self):
        self.payload.write_text('tampered')
        output = io.StringIO()
        with patch.object(preflight, 'inspect', side_effect=AssertionError('Host must not be inspected')), contextlib.redirect_stdout(output):
            self.assertEqual(preflight.main(['--check', '--json', '--package-root', str(self.root)]), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report['failures'], [preflight.PACKAGE_LABEL])
        self.assertNotIn(str(self.root), output.getvalue())

    def test_verify_only_never_invokes_host_checks(self):
        output = io.StringIO()
        with patch.object(preflight, 'inspect', side_effect=AssertionError('No host check')), contextlib.redirect_stdout(output):
            self.assertEqual(preflight.main(['--verify-package', '--json', '--package-root', str(self.root)]), 0)
        self.assertTrue(json.loads(output.getvalue())['passed'])

    def test_real_verify_only_cli_is_bounded_and_keeps_package_unchanged(self):
        command = [sys.executable, str(Path(__file__).with_name('preflight.py')),
                   '--verify-package', '--json', '--package-root', str(self.root)]
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*'))
        completed = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)['passed'])
        self.assertNotIn(str(self.root), completed.stdout + completed.stderr)
        self.assertEqual(before, sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*')))


class ReleaseIdentityTests(unittest.TestCase):
    def test_qualified_native_digest_and_release_identity(self):
        self.assertEqual(preflight.VERSION, '0.0.1')
        self.assertEqual(preflight.NATIVE_SHA256,
                         '9f1f839d89a6d3a874c939ecf3108007cc0964a338596a35adb47c7e6c5c921d')


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mseries-preflight-inspect-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'
        self.home = Path(self.temp.name) / 'synthetic-private-home'
        self.base = self.home / '.local/share/mseries/stream'
        self.uid = os.getuid() or 1000
        self.calls = []
        self.overrides = {}
        self.write('sys/firmware/devicetree/base/compatible', b'apple,j314s\x00apple,t6000\x00apple,arm-platform\x00')
        self.write('proc/meminfo', b'MemTotal: 33554432 kB\nMemAvailable: 10485760 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n')
        self.write('sys/class/hwmon/hwmon0/fan1_input', b'2400\n')
        self.write('sys/class/hwmon/hwmon0/temp1_input', b'43000\n')
        self.write('etc/udev/hwdb.d/91-mseries-dictation.hwdb', b'evdev:name:Apple SPI [Kk]eyboard:*\nevdev:name:Apple MTP [Kk]eyboard:*\n KEYBOARD_KEY_7003e=f14\n')
        self.status = {'pid': 1234, 'phase': 'ready', 'output': 'ibus', 'backend': 'cpu', 'updated_at': 1.0}
        self.status_path = self.root / ('run/user/' + str(self.uid)) / 'mseries-dictation/status.json'
        self.save_status()
        self.write('proc/1234/stat', b'1234 (synthetic listener) S 1 2 3\n')
        self.write('proc/1234/environ', b'STREAM_BACKEND=cpu\x00STREAM_OUTPUT=ibus\x00PRIVATE_TOKEN=do-not-publish\x00')
        self.write('proc/1234/task/1234/children', b'')
        for name in ('stream-dictate.py', 'dictation-input.py', 'dictation-input-client.py', 'venv/bin/python'):
            self.base_write(name, b'synthetic fixture\n')
        self.base_write('venv/pyvenv.cfg', b'version = 3.14.0\n')
        self.base_write('venv/lib/python3.14/site-packages/transcribe_cpp-0.4.0.dist-info/METADATA', b'Name: transcribe_cpp\nVersion: 0.4.0\n')
        self.base_write('venv/lib/python3.14/site-packages/numpy-2.5.4.dist-info/METADATA', b'Name: numpy\nVersion: 2.5.4\n')
        self.base_write(preflight.NATIVE, b'synthetic native library - never loaded')
        expected = hashlib.sha256((self.base / preflight.NATIVE).read_bytes()).hexdigest()
        self.native_patch = patch.object(preflight, 'NATIVE_SHA256', expected)
        self.native_patch.start()
        self.addCleanup(self.native_patch.stop)

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def base_write(self, relative, data):
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def save_status(self):
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_path.write_text(json.dumps(self.status))
        self.status_path.chmod(0o600)
        if os.getuid() == 0:
            os.chown(self.status_path, self.uid, -1)

    def runner(self, args):
        command = tuple(args)
        self.calls.append(command)
        if command in self.overrides:
            override = self.overrides[command]
            if isinstance(override, BaseException):
                raise override
            return subprocess.CompletedProcess(args, 0, override, 'PRIVATE command diagnostic')
        if args == ['id', '-u']:
            value = str(self.uid)
        elif args == ['uname', '-s']:
            value = 'Linux'
        elif args == ['uname', '-m']:
            value = 'aarch64'
        elif args == ['/usr/bin/python3', '-I', '-c', preflight.PYTHON_QUERY]:
            value = json.dumps({'python': [3, 14], 'bindings': True})
        elif args == ['/usr/bin/python3', '-I', '-c', preflight.BRIDGE_QUERY]:
            value = 'ready'
        elif args[:3] == ['systemctl', '--user', 'is-active']:
            value = 'active'
        elif args[:3] == ['systemctl', '--user', 'is-enabled']:
            value = 'enabled'
        elif args == ['systemctl', '--user', 'show', preflight.STREAM_UNIT, '-p', 'MainPID', '--value']:
            value = '1234'
        elif args == ['gsettings', 'get', 'org.gnome.desktop.input-sources', 'sources']:
            value = "[('xkb', 'us')]"
        elif args == ['gsettings', 'get', 'org.gnome.desktop.input-sources', 'current']:
            value = 'uint32 0'
        elif args == ['gsettings', 'get', 'org.gnome.desktop.interface', 'toolkit-accessibility']:
            value = 'true'
        elif args == ['gsettings', 'get', 'org.gnome.desktop.interface', 'gtk-im-module']:
            value = "'ibus'"
        elif args == ['ibus', 'engine']:
            value = 'xkb:us::eng'
        else:
            raise AssertionError('Unexpected command: ' + repr(args))
        return subprocess.CompletedProcess(args, 0, value + '\n', '')

    def inspect(self):
        return preflight.inspect(root=self.root, home=self.home, runner=self.runner)

    def test_supported_fixture_is_read_only_and_private(self):
        before = {str(path): path.read_bytes() for path in Path(self.temp.name).rglob('*') if path.is_file()}
        report = self.inspect()
        self.assertTrue(report['passed'], report['failures'])
        self.assertEqual(before, {str(path): path.read_bytes() for path in Path(self.temp.name).rglob('*') if path.is_file()})
        public = json.dumps(report)
        for secret in (str(self.home), 'do-not-publish', 'PRIVATE', 'xkb:us::eng'):
            self.assertNotIn(secret, public)
        self.assertIn('NO_AUTO_START', preflight.BRIDGE_QUERY)
        self.assertTrue(all('start' not in args and 'restart' not in args and 'set' not in args for args in self.calls))

    def test_memory_and_quiet_boundary_checks(self):
        self.write('proc/meminfo', b'MemTotal: 33554432 kB\nMemAvailable: 8388608 kB\n')
        self.assertTrue(self.inspect()['passed'])
        self.write('proc/meminfo', b'MemTotal: 33554432 kB\nMemAvailable: 8388607 kB\n')
        self.assertIn('At least 8 GiB memory is currently available', self.inspect()['failures'])
        self.write('proc/meminfo', b'MemTotal: 29360128 kB\nMemAvailable: 10485760 kB\n')
        self.assertTrue(self.inspect()['passed'])
        self.write('proc/meminfo', b'MemTotal: 37748736 kB\nMemAvailable: 10485760 kB\n')
        self.assertTrue(self.inspect()['passed'])
        self.write('sys/class/hwmon/hwmon0/fan1_input', b'2700\n')
        self.write('sys/class/hwmon/hwmon0/temp1_input', b'60000\n')
        self.assertIn('All measured fans are below 2700 RPM', self.inspect()['failures'])
        self.assertIn('All measured temperatures are below 60 C', self.inspect()['failures'])
        self.write('sys/class/hwmon/hwmon0/fan1_input', b'nan\n')
        self.assertIn('All measured fans are below 2700 RPM', self.inspect()['failures'])

    def test_missing_telemetry_and_wrong_hardware_fail_closed(self):
        self.write('sys/firmware/devicetree/base/compatible', b'apple,j413\x00apple,t8112\x00')
        (self.root / 'sys/class/hwmon/hwmon0/fan1_input').unlink()
        (self.root / 'sys/class/hwmon/hwmon0/temp1_input').unlink()
        report = self.inspect()
        self.assertFalse(report['passed'])
        for label in ('Apple M1 Pro j314s machine', 'All measured fans are below 2700 RPM', 'All measured temperatures are below 60 C'):
            self.assertIn(label, report['failures'])

    def test_runtime_version_and_library_pins(self):
        self.base_write('venv/pyvenv.cfg', b'version = 3.13.9\n')
        self.base_write(preflight.NATIVE, b'wrong library')
        self.base_write('venv/lib/python3.14/site-packages/numpy-2.5.4.dist-info/METADATA', b'Name: numpy\nVersion: 2.5.5\n')
        self.overrides[('/usr/bin/python3', '-I', '-c', preflight.PYTHON_QUERY)] = '{"python":[3,13],"bindings":true}'
        report = self.inspect()
        for label in ('Existing Python 3.14 speech virtual environment', 'Qualified native speech library digest',
                      'Existing NumPy 2.5.4 metadata', 'Python 3.14 with GTK4 IBus and accessibility bindings'):
            self.assertIn(label, report['failures'])

    def test_capture_status_pid_process_and_child_guards(self):
        for status in ({'phase': 'loading'}, {'phase': 'listening'}, {'phase': 'finishing'},
                       {'phase': 'stopped'}, {'phase': 'unavailable'}, {'phase': 'unknown'},
                       {'pid': 999}, {'backend': 'ane'}):
            with self.subTest(status=status):
                original = dict(self.status)
                self.status.update(status)
                self.save_status()
                self.assertIn('F5 is idle in the existing CPU and IBus listener', self.inspect()['failures'])
                self.status = original
        self.save_status()
        self.write('proc/1234/task/1234/children', b'2345')
        self.write('proc/2345/stat', b'2345 (synthetic capture) S 1 2\n')
        self.assertIn('F5 is idle in the existing CPU and IBus listener', self.inspect()['failures'])
        self.write('proc/2345/stat', b'2345 (synthetic child) Z 1 2\n')
        self.assertTrue(self.inspect()['passed'])
        self.status_path.chmod(0o644)
        self.assertIn('F5 is idle in the existing CPU and IBus listener', self.inspect()['failures'])

    def test_terminal_idle_phases_still_require_no_capture_and_matching_runtime(self):
        self.assertEqual(preflight.IDLE_PHASES, {'ready', 'error', 'cancelled', 'waiting'})
        label = 'F5 is idle in the existing CPU and IBus listener'
        for phase in sorted(preflight.IDLE_PHASES):
            with self.subTest(phase=phase):
                self.status.update(phase=phase, pid=1234)
                self.save_status()
                self.assertTrue(self.inspect()['passed'])
                # An asynchronous insertion failure may expose phase=error
                # before cleanup; a live capture/output child must still deny.
                self.write('proc/1234/task/1234/children', b'2345')
                self.write('proc/2345/stat', b'2345 (synthetic capture) S 1 2\n')
                self.assertIn(label, self.inspect()['failures'])
                self.write('proc/1234/task/1234/children', b'')
                self.status['pid'] = 999
                self.save_status()
                self.assertIn(label, self.inspect()['failures'])
                self.status['pid'] = 1234
                self.save_status()
                self.write('proc/1234/environ', b'STREAM_BACKEND=ane\x00STREAM_OUTPUT=ibus\x00')
                self.assertIn(label, self.inspect()['failures'])
                self.write('proc/1234/environ', b'STREAM_BACKEND=cpu\x00STREAM_OUTPUT=ibus\x00')

    def test_commands_fail_closed_without_raw_output(self):
        self.overrides[('id', '-u')] = '0'
        self.overrides[('systemctl', '--user', 'is-active', preflight.STREAM_UNIT)] = 'inactive'
        self.overrides[('/usr/bin/python3', '-I', '-c', preflight.BRIDGE_QUERY)] = subprocess.TimeoutExpired('PRIVATE COMMAND', 3)
        self.overrides[('gsettings', 'get', 'org.gnome.desktop.input-sources', 'sources')] = 'PRIVATE malformed settings ['
        report = self.inspect()
        self.assertFalse(report['passed'])
        self.assertNotIn('PRIVATE', json.dumps(report))
        self.assertIn('Selected native IBus input remains valid', report['failures'])

    def test_input_accessibility_and_remap_checks(self):
        self.overrides[('ibus', 'engine')] = 'mseries-dictation'
        self.overrides[('gsettings', 'get', 'org.gnome.desktop.interface', 'toolkit-accessibility')] = 'false'
        self.write('etc/udev/hwdb.d/91-mseries-dictation.hwdb', b'KEYBOARD_KEY_7003e=micmute\n')
        report = self.inspect()
        self.assertIn('Selected native IBus input remains valid', report['failures'])
        self.assertIn('Desktop toolkit accessibility is enabled', report['failures'])
        self.assertIn('Existing F5 remap configuration metadata (not a physical key test)', report['failures'])


if __name__ == '__main__':
    unittest.main()
