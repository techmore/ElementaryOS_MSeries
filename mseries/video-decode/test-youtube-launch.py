#!/usr/bin/env python3
"""Offline tests of the actual launcher setup blocks; no browser or system writes.

Only runtime selection and external installer/process tools are stubbed. The
profile/bootstrap and proxy lifecycle shell code comes directly from the launcher.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).with_name('brave-youtube').read_text()


class YouTubeLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.profile = self.root / 'home/.config/brave-youtube'
        self.runtime = self.root / 'run'
        self.runtime.mkdir()
        self.env = dict(os.environ, HOME=str(self.root / 'home'), USER='qa',
                        BRAVE_YT_PROFILE=str(self.profile), XDG_RUNTIME_DIR=str(self.runtime),
                        PATH=str(self.bin) + ':' + os.environ['PATH'])
        self.tool('pgrep', '#!/bin/sh\ntest "${QA_RUNNING:-0}" = 1\n')
        self.launcher = self.root / 'video-decode/brave-youtube'
        self.launcher.parent.mkdir()
        prefix = SOURCE.split('\nargs=(', 1)[0]
        prefix = prefix.replace('brave=/usr/lib/mseries-brave/brave', 'brave=/bin/true')
        self.launcher.write_text(prefix)
        installer = self.root / 'install-brave-widevine.sh'
        installer.write_text('''#!/usr/bin/env bash
python3 - <<'PYINSTALL'
import json,os,sys
from pathlib import Path
p=Path(os.environ['BRAVE_PROFILE_DIR'])
(p/'installer-called').touch()
s=json.loads((p/'Local State').read_text())
if os.environ.get('QA_INSTALL_FAIL')=='1': sys.exit(1)
s.setdefault('brave',{})['widevine_opted_in']=True
(p/'Local State').write_text(json.dumps(s))
PYINSTALL
''')

    def tool(self, name, source):
        path = self.bin / name
        path.write_text(source)
        path.chmod(0o755)

    def run_setup(self, *arguments, **env):
        return subprocess.run(['bash', str(self.launcher), *arguments],
                              env=dict(self.env, **env), capture_output=True, text=True, check=True)

    def test_first_launch_provisions_before_browser_profile_exists(self):
        self.run_setup()
        state = json.loads((self.profile / 'Local State').read_text())
        self.assertTrue(state['brave']['widevine_opted_in'])
        self.assertTrue((self.profile / 'installer-called').exists())
        self.assertEqual((self.profile / 'Local State').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.profile.stat().st_mode & 0o777, 0o700)

    def test_existing_preferences_are_preserved(self):
        self.profile.mkdir(parents=True)
        (self.profile / 'Local State').write_text('{"existing":{"value":42}}')
        self.run_setup()
        state = json.loads((self.profile / 'Local State').read_text())
        self.assertEqual(state['existing'], {'value': 42})
        self.assertTrue(state['brave']['widevine_opted_in'])

    def test_running_profile_is_not_modified(self):
        self.run_setup(QA_RUNNING='1')
        self.assertFalse((self.profile / 'Local State').exists())
        self.assertFalse((self.profile / 'installer-called').exists())

    def test_probe_does_not_provision_and_network_failure_is_nonfatal(self):
        self.run_setup('--probe')
        self.assertFalse((self.profile / 'Local State').exists())
        result = self.run_setup(QA_INSTALL_FAIL='1')
        self.assertIn('DRM movies will not play', result.stderr)
        self.assertEqual(json.loads((self.profile / 'Local State').read_text()), {})

    def test_existing_registered_component_is_not_reinstalled(self):
        cdm = self.profile / 'WidevineCdm'
        cdm.mkdir(parents=True)
        (cdm / 'latest-component-updated-widevine-cdm').write_text('{"Path":"fixture"}')
        (self.profile / 'Local State').write_text('{"brave":{"widevine_opted_in":true}}')
        self.run_setup()
        self.assertFalse((self.profile / 'installer-called').exists())

    def test_concurrent_proxy_sockets_and_cleanup_are_isolated(self):
        source = self.root / 'source-bus'
        with socket.socket(socket.AF_UNIX) as bus, socket.socket(socket.AF_UNIX) as owner:
            bus.bind(str(source))
            owner_path = self.runtime / 'brave-youtube-sysbus'
            owner.bind(str(owner_path))
            original_inode = owner_path.stat().st_ino
            self.tool('xdg-dbus-proxy', '''#!/usr/bin/env python3
import socket,sys,time
s=socket.socket(socket.AF_UNIX);s.bind(sys.argv[2]);s.listen()
while True: time.sleep(1)
''')
            block = SOURCE.split('if command -v xdg-dbus-proxy', 1)[1].split('\nif [[ ${1:-} == --probe', 1)[0]
            block = 'if command -v xdg-dbus-proxy' + block
            block = block.replace('/run/dbus/system_bus_socket', str(source))
            script = 'set -eu\nruntime=$XDG_RUNTIME_DIR\nargs=()\n' + block
            script += '\nprintf "%s\\n" "$sysbus"\nread -r finish\n'
            processes = []
            try:
                paths = []
                for _ in range(2):
                    proc = subprocess.Popen(['bash', '-c', script], env=self.env, text=True,
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE)
                    processes.append(proc)
                    paths.append(Path(proc.stdout.readline().strip()))
                self.assertNotEqual(paths[0], paths[1])
                self.assertTrue(all(p.is_socket() for p in paths))
                self.assertEqual(owner_path.stat().st_ino, original_inode)
                processes[0].communicate('\n', timeout=5)
                self.assertEqual(processes[0].returncode, 0)
                self.assertFalse(paths[0].parent.exists())
                self.assertTrue(paths[1].is_socket())
                processes[1].communicate('\n', timeout=5)
                self.assertEqual(processes[1].returncode, 0)
                self.assertFalse(paths[1].parent.exists())
                self.assertEqual(owner_path.stat().st_ino, original_inode)
            finally:
                for proc in processes:
                    if proc.poll() is None:
                        proc.communicate('\n', timeout=5)


if __name__ == '__main__':
    unittest.main()
