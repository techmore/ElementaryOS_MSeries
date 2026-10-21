#!/usr/bin/env python3
"""Drive mseries-update's real Backend (apt-get, apt-cache, dpkg, dpkg-query) against a
local file: repository and a scratch dpkg root, so the command lines, option names and
output parsing are exercised for real. No root, no network, no host package changes.
Skipped when the tools are missing."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).with_name('mseries-update.py')
SPEC = importlib.util.spec_from_file_location('mseries_update', SCRIPT)
MU = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MU)

CHILD = '''
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("mu", sys.argv[1])
mu = importlib.util.module_from_spec(spec); spec.loader.exec_module(mu)
c = json.loads(sys.argv[2])
paths = mu.Paths({"MSERIES_UPDATE_STATE": c["state"], "MSERIES_UPDATE_CONFIG": c["config"],
                  "MSERIES_UPDATE_SOURCES": c["sources"], "MSERIES_UPDATE_LOG": c["log"],
                  "MSERIES_UPDATE_DPKG_LOCK": c["lock"]})
backend = mu.Backend(paths, dpkg_args=c["dpkg_args"], query_args=c["query_args"], apt_extra=c["apt_extra"])
class System:
    def free_bytes(self, p): return 1 << 40
    def power(self): return "ac", None
    def package_manager_busy(self): return False
    def health_commands(self): return []
mu.Updater(paths, mu.Config(paths.config), backend, System(), mu.Log(paths.log, echo=False)).apply()
'''

TOOLS = ('ps', 'apt-get', 'apt-cache', 'dpkg', 'dpkg-query', 'dpkg-deb', 'dpkg-scanpackages')


class HealthySystem:
    free, healthy = 10 << 30, True

    def free_bytes(self, _path):
        return self.free

    def power(self):
        return 'ac', None

    def network_ok(self):
        return True

    def metered(self):
        return False

    def package_manager_busy(self):
        return False

    def session_healthy(self, _processes):
        return self.healthy

    def health_commands(self):
        return []


@unittest.skipUnless(all(shutil.which(tool) for tool in TOOLS), 'apt and dpkg tools are not installed')
class RealTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {'MSERIES_UPDATE_ALLOW_NONROOT': '1'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = Path(self.tmp.name)
        self.arch = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
        self.repo = self.root / 'repo'
        self.target = self.root / 'target'
        admin = self.target / 'var/lib/dpkg'
        for sub in ('info', 'updates'):
            (admin / sub).mkdir(parents=True)
        (admin / 'status').write_text('')
        env = {'MSERIES_UPDATE_STATE': str(self.root / 'state'), 'MSERIES_UPDATE_CONFIG': str(self.root / 'update.conf'),
               'MSERIES_UPDATE_SOURCES': str(self.root / 'sources.list.d'), 'MSERIES_UPDATE_LOG': str(self.root / 'log'),
               'MSERIES_UPDATE_DPKG_LOCK': str(self.root / 'nolock')}
        self.paths = MU.Paths(env)
        self.paths.sources_dir.mkdir()
        self.backend = MU.Backend(
            self.paths,
            dpkg_args=[f'--root={self.target}', f'--admindir={admin}', '--force-not-root',
                       '--force-script-chrootless', '--force-bad-path'],
            query_args=[f'--admindir={admin}'],
            apt_extra=['-o', f'Dir::State::status={admin}/status', '-o', 'Debug::NoLocking=1',
                       '-o', 'APT::Sandbox::User=', '-o', f'Dir::Log={self.root}/aptlog'])
        self.updater = MU.Updater(self.paths, MU.Config(self.paths.config), self.backend, HealthySystem(),
                                  MU.Log(self.paths.log, echo=False), sleep=lambda _s: None)
        self.build('1.0-1')
        self.publish()
        self.paths.sources_file.write_text(
            f'Types: deb\nURIs: file://{self.repo}\nSuites: stable\nComponents: main\n'
            f'Architectures: {self.arch}\nTrusted: yes\n')
        self.install_initial('1.0-1')

    def build(self, version, postinst=None):
        package = self.root / f'pkg-{version}'
        (package / 'DEBIAN').mkdir(parents=True)
        (package / 'usr/share/mseries-demo').mkdir(parents=True)
        (package / 'usr/share/mseries-demo/version').write_text(version + '\n')
        (package / 'DEBIAN/control').write_text(
            f'Package: mseries-demo\nVersion: {version}\nArchitecture: all\n'
            'Maintainer: test <test@example.invalid>\nDescription: demo\n')
        if postinst:
            (package / 'DEBIAN/postinst').write_text(postinst)
            (package / 'DEBIAN/postinst').chmod(0o755)
        (self.repo / 'pool').mkdir(parents=True, exist_ok=True)
        subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(package),
                        str(self.repo / 'pool' / f'mseries-demo_{version}_all.deb')],
                       check=True, capture_output=True)

    def publish(self):
        index = self.repo / 'dists/stable/main' / f'binary-{self.arch}'
        index.mkdir(parents=True, exist_ok=True)
        packages = subprocess.run(['dpkg-scanpackages', '-m', 'pool'], cwd=self.repo, check=True,
                                  capture_output=True, text=True).stdout.encode()
        (index / 'Packages').write_bytes(packages)
        digest = hashlib.sha256(packages).hexdigest()
        (self.repo / 'dists/stable/Release').write_text(
            f'Origin: test\nSuite: stable\nCodename: stable\nArchitectures: {self.arch}\nComponents: main\n'
            f'Date: {datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S UTC")}\n'
            f'SHA256:\n {digest} {len(packages)} main/binary-{self.arch}/Packages\n')

    def install_initial(self, version):
        self.backend.install_debs([self.repo / 'pool' / f'mseries-demo_{version}_all.deb'])

    def installed(self):
        return self.backend.installed(['mseries-*']).get('mseries-demo')

    def test_check_stage_apply_confirm_and_rollback_with_the_real_package_tools(self):
        self.assertEqual('1.0-1', self.installed())
        self.assertEqual({}, self.updater.check()['updates'])
        self.build('1.0-2')
        self.publish()
        self.assertEqual({'mseries-demo': {'from': '1.0-1', 'to': '1.0-2'}}, self.updater.check()['updates'])
        staged = self.updater.stage()
        self.assertEqual('1.0-1', self.installed(), 'staging installs nothing')
        self.assertEqual(['mseries-demo_1.0-1_all.deb'], [p.name for p in self.paths.store.glob('*.deb')])
        self.assertEqual({'mseries-demo': '1.0-2'}, staged['target'])
        self.assertEqual({'applied': {'mseries-demo': '1.0-2'}}, self.updater.apply())
        self.assertEqual('1.0-2', self.installed())
        self.assertEqual({'confirmed': True}, self.updater.confirm())
        self.updater.rollback()
        self.assertEqual('1.0-1', self.installed())
        version_file = self.target / 'usr/share/mseries-demo/version'
        self.assertEqual('1.0-1', version_file.read_text().strip())

    def test_a_package_whose_script_fails_is_rolled_back_by_the_real_dpkg(self):
        self.build('1.0-2', postinst='#!/bin/sh\nexit 1\n')
        self.publish()
        self.updater.stage()
        result = self.updater.apply()
        self.assertTrue(result['rolled_back'], result)
        self.assertEqual('1.0-1', self.installed())
        version_file = self.target / 'usr/share/mseries-demo/version'
        self.assertEqual('1.0-1', version_file.read_text().strip())
        self.assertEqual('', self.backend.audit(), 'no half-configured package is left behind')
        self.assertEqual({}, self.updater.check()['updates'], 'the failed version is not offered again')
        state = json.loads(self.paths.state_file.read_text())
        self.assertEqual('rolled-back', state['history'][-1]['outcome'])

    def test_kill_9_in_the_middle_of_dpkg_is_undone_at_the_next_boot(self):
        # The new package's postinst SIGKILLs the updater and dpkg after files are unpacked, like power loss.
        self.build('1.0-2', postinst='#!/bin/sh\nkill -9 "$(ps -o ppid= -p "$PPID" | tr -d " ")"\nkill -9 "$PPID"\nsleep 5\n')
        self.publish()
        self.updater.stage()
        child = subprocess.run([sys.executable, '-I', '-c', CHILD, str(SCRIPT), json.dumps({
            'state': str(self.paths.state), 'config': str(self.paths.config), 'sources': str(self.paths.sources_dir),
            'log': str(self.paths.log), 'lock': str(self.paths.dpkg_lock),
            'dpkg_args': self.backend.dpkg_args, 'query_args': self.backend.query_args,
            'apt_extra': self.backend.apt_extra})], capture_output=True, text=True)
        self.assertEqual(-signal.SIGKILL, child.returncode, child.stderr[-500:])
        state = json.loads(self.paths.state_file.read_text())
        self.assertIsNotNone(state['journal'], 'the write-ahead journal survived the kill')
        self.assertNotEqual('1.0-1', self.installed(), 'the new version is half-installed on disk')
        self.assertEqual({'idle': True}, self.updater.boot())
        self.assertEqual('1.0-1', self.installed())
        self.assertEqual('1.0-1', (self.target / 'usr/share/mseries-demo/version').read_text().strip())
        self.assertEqual('', self.backend.audit())
        self.assertEqual('recovered', json.loads(self.paths.state_file.read_text())['history'][-1]['outcome'])

    def test_a_repository_that_lacks_the_installed_version_cannot_be_staged(self):
        self.build('1.0-2')
        (self.repo / 'pool/mseries-demo_1.0-1_all.deb').unlink()
        self.publish()
        with self.assertRaisesRegex(MU.UpdateError, 'no rollback copy'):
            self.updater.stage()
        self.assertEqual('1.0-1', self.installed())

    def test_missing_repository_fails_closed(self):
        shutil.rmtree(self.repo / 'dists')
        with self.assertRaises(MU.BackendError):
            self.updater.check()


if __name__ == '__main__':
    unittest.main()
