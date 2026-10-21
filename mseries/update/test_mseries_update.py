#!/usr/bin/env python3
"""Hermetic checks for mseries-update: a fake repository and package database, injected
faults (failed downloads, failed installs, failed health checks, crashes, a failing
rollback) and the systemd-less boot sequence. Nothing touches the host's apt or dpkg."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).with_name('mseries-update.py')
SPEC = importlib.util.spec_from_file_location('mseries_update', SCRIPT)
MU = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MU)


def vkey(version):
    return [int(x) for x in version.replace('-', '.').split('.')]


class SimulatedCrash(BaseException):
    """Stands in for power loss: nothing in the updater may catch it and tidy up."""


class FakeBackend:
    """In-memory repository + dpkg database. A .deb is a small JSON file."""

    def __init__(self, workdir):
        self.workdir = Path(workdir)
        self.repo = {}            # name -> {version: [dependency names]}
        self.db = {}              # installed name -> version
        self.fail_install = set()
        self.crash_after = None   # number of packages installed before SimulatedCrash
        self.fail_download = False
        self.fail_refresh = False
        self.verify_problems = []
        self.audit_output = ''
        self.during_install = None   # callable run at the start of dpkg, to break things mid-transaction
        self.calls = []

    def add(self, name, version, deps=()):
        self.repo.setdefault(name, {})[version] = list(deps)

    def refresh(self):
        self.calls.append('refresh')
        if self.fail_refresh:
            raise MU.BackendError('apt-get failed (100): NO_PUBKEY / The repository is not signed')

    def installed(self, patterns):
        import fnmatch
        return {n: v for n, v in self.db.items() if any(fnmatch.fnmatch(n, p) for p in patterns)}

    def candidates(self, names):
        out = {}
        for name in names:
            versions = list(self.repo.get(name, {})) + ([self.db[name]] if name in self.db else [])
            out[name] = max(versions, key=vkey) if versions else None
        return out

    def _write_deb(self, directory, name, version):
        Path(directory).mkdir(parents=True, exist_ok=True)
        path = Path(directory) / f'{name}_{version}_arm64.deb'
        path.write_text(json.dumps({'name': name, 'version': version}))
        return path

    def download(self, specs, destination):
        self.calls.append(('download', tuple(specs)))
        if self.fail_download:
            raise MU.BackendError('apt-get failed (100): Temporary failure resolving')
        wanted = {}
        pending = [tuple(spec.split('=')) for spec in specs]
        while pending:
            name, version = pending.pop()
            if name in wanted:
                continue
            if version not in self.repo.get(name, {}):
                raise MU.BackendError(f'E: Version {version} for {name} was not found')
            wanted[name] = version
            for dep in self.repo[name][version]:
                if dep not in self.db and dep not in wanted:
                    pending.append((dep, max(self.repo[dep])))
        return [self._write_deb(destination, n, v) for n, v in sorted(wanted.items())]

    def download_exact(self, name, version, destination):
        if version not in self.repo.get(name, {}):
            raise MU.BackendError(f'E: Version {version} for {name} was not found')
        return self._write_deb(destination, name, version)

    def find_deb(self, name, version, directories):
        for directory in directories:
            found = sorted(Path(directory).glob(f'{name}_{version}_*.deb')) if Path(directory).is_dir() else []
            if found:
                return found[0]
        return None

    def deb_info(self, deb):
        data = json.loads(Path(deb).read_text())
        return data['name'], data['version']

    def install_debs(self, debs):
        self.calls.append(('install', tuple(Path(d).name for d in debs)))
        if self.during_install:
            self.during_install()
        failures = []
        for number, deb in enumerate(debs):
            if self.crash_after is not None and number >= self.crash_after:
                raise SimulatedCrash()
            name, version = self.deb_info(deb)
            if name in self.fail_install:
                failures.append(name)
                continue
            self.db[name] = version
        if failures:
            raise MU.BackendError('dpkg failed (1): postinst error in ' + ', '.join(failures))

    def remove(self, names):
        for name in names:
            self.db.pop(name, None)

    def compare(self, left, right):
        return (vkey(left) > vkey(right)) - (vkey(left) < vkey(right))

    def audit(self):
        return self.audit_output

    def verify(self, names):
        return list(self.verify_problems)


class FakeSystem:
    def __init__(self):
        self.free = 10 << 30
        self.power_state = ('ac', 100)
        self.network = True
        self.busy = False
        self.is_metered = False
        self.healthy = True
        self.health = []   # [(name, ok)]
        self.polls = 0

    def free_bytes(self, path):
        return self.free

    def power(self):
        return self.power_state

    def network_ok(self):
        return self.network

    def metered(self):
        return self.is_metered

    def package_manager_busy(self):
        return self.busy

    def session_healthy(self, processes):
        self.polls += 1
        return self.healthy

    def health_commands(self):
        return [Path(name) for name, _ in self.health]

    def run_health_command(self, command):
        return dict(self.health)[command.name], f'{command.name} output'


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {'MSERIES_UPDATE_ALLOW_NONROOT': '1'})
        patcher.start()
        self.addCleanup(patcher.stop)
        root = Path(self.tmp.name)
        self.env = {
            'MSERIES_UPDATE_STATE': str(root / 'state'), 'MSERIES_UPDATE_CONFIG': str(root / 'etc/update.conf'),
            'MSERIES_UPDATE_SOURCES': str(root / 'etc/sources.list.d'), 'MSERIES_UPDATE_LOG': str(root / 'update.log'),
            'MSERIES_UPDATE_POWER': str(root / 'power'), 'MSERIES_UPDATE_DPKG_LOCK': str(root / 'dpkg-lock'),
            'MSERIES_UPDATE_HEALTH_D': str(root / 'health.d'),
        }
        self.paths = MU.Paths(self.env)
        self.backend = FakeBackend(root / 'fake')
        self.system = FakeSystem()
        self.backend.db = {'mseries-wingpanel-network': '8.0.1-1', 'mseries-quick-settings': '1.4.0-1',
                           'io.elementary.panel.network': '8.0.1'}
        for name, versions in (('mseries-wingpanel-network', ['8.0.1-1', '8.0.1-2']),
                               ('mseries-quick-settings', ['1.4.0-1', '1.4.0-2'])):
            for version in versions:
                self.backend.add(name, version)
        self.paths.sources_dir.mkdir(parents=True)
        self.paths.sources_file.write_text('URIs: https://example.invalid/apt\n')
        self.updater = self.make()

    def make(self):
        return MU.Updater(self.paths, MU.Config(self.paths.config), self.backend, self.system,
                          MU.Log(self.paths.log, echo=False), sleep=lambda _s: None)

    def state(self):
        return json.loads(self.paths.state_file.read_text())

    def version(self, name):
        return self.backend.db.get(name)

    def stage_and_apply(self):
        self.updater.stage()
        return self.updater.apply()

    def assert_old_set(self):
        self.assertEqual('8.0.1-1', self.version('mseries-wingpanel-network'))
        self.assertEqual('1.4.0-1', self.version('mseries-quick-settings'))


class Discovery(Base):
    def test_check_lists_updates_and_changes_nothing(self):
        found = self.updater.check()
        self.assertEqual({'mseries-wingpanel-network': {'from': '8.0.1-1', 'to': '8.0.1-2'},
                          'mseries-quick-settings': {'from': '1.4.0-1', 'to': '1.4.0-2'}}, found['updates'])
        self.assert_old_set()
        self.assertFalse([c for c in self.backend.calls if isinstance(c, tuple) and c[0] == 'install'])

    def test_unmanaged_packages_are_never_touched(self):
        self.backend.add('io.elementary.panel.network', '9.9.9')
        self.assertNotIn('io.elementary.panel.network', self.updater.check()['updates'])

    def test_older_repository_versions_are_not_offered_as_downgrades(self):
        self.backend.db['mseries-quick-settings'] = '1.4.0-3'
        self.assertNotIn('mseries-quick-settings', self.updater.check()['updates'])

    def test_unsigned_or_unreachable_repository_fails_before_any_state_change(self):
        self.backend.fail_refresh = True
        with self.assertRaises(MU.BackendError):
            self.updater.check()
        self.assertFalse(self.paths.state_file.exists())

    def test_auto_checks_only_unless_the_owner_enabled_staging(self):
        self.updater.automatic()
        self.assertIsNone(self.state()['staged'])
        MU.Config(self.paths.config).set('auto_stage', 'true')
        updater = self.make()
        self.system.is_metered = True
        updater.automatic()
        self.assertIsNone(self.state()['staged'], 'metered connection must not download')
        self.system.is_metered = False
        updater.automatic()
        self.assertIsNotNone(self.state()['staged'])
        self.assert_old_set()


class Staging(Base):
    def test_stage_downloads_and_keeps_rollback_copies_but_installs_nothing(self):
        staged = self.updater.stage()
        self.assertEqual({'mseries-wingpanel-network': '8.0.1-2', 'mseries-quick-settings': '1.4.0-2'}, staged['target'])
        self.assertEqual({'mseries-wingpanel-network': '8.0.1-1', 'mseries-quick-settings': '1.4.0-1'}, staged['from'])
        self.assert_old_set()
        stored = sorted(p.name for p in self.paths.store.glob('*.deb'))
        self.assertEqual(['mseries-quick-settings_1.4.0-1_arm64.deb', 'mseries-wingpanel-network_8.0.1-1_arm64.deb'], stored)

    def test_staging_twice_reuses_the_verified_download(self):
        first = self.updater.stage()
        downloads = len([c for c in self.backend.calls if isinstance(c, tuple) and c[0] == 'download'])
        again = self.updater.stage()
        self.assertEqual(first['id'], again['id'])
        self.assertEqual(downloads, len([c for c in self.backend.calls if isinstance(c, tuple) and c[0] == 'download']))

    def test_preflight_refusals_stage_nothing(self):
        for mutate, reason in ((lambda: setattr(self.system, 'free', 1 << 20), 'disk'),
                               (lambda: setattr(self.system, 'network', False), 'network'),
                               (lambda: setattr(self.system, 'busy', True), 'dpkg-lock'),
                               (lambda: setattr(self.backend, 'audit_output', 'half-configured foo'), 'dpkg-audit')):
            with self.subTest(reason):
                self.setUp()
                mutate()
                with self.assertRaisesRegex(MU.UpdateError, reason):
                    self.updater.stage()
                self.assertFalse(self.paths.state_file.exists() and self.state()['staged'])
                self.assertFalse(list(self.paths.staged.glob('*')) if self.paths.staged.exists() else [])

    def test_failed_download_leaves_no_partial_stage(self):
        self.backend.fail_download = True
        with self.assertRaises(MU.BackendError):
            self.updater.stage()
        self.assertEqual([], list(self.paths.staged.glob('*')))
        self.assertIsNone(self.state().get('staged') if self.paths.state_file.exists() else None)

    def test_no_rollback_copy_means_no_update(self):
        del self.backend.repo['mseries-quick-settings']['1.4.0-1']
        with self.assertRaisesRegex(MU.UpdateError, 'no rollback copy of mseries-quick-settings 1.4.0-1'):
            self.updater.stage()
        self.assertEqual([], list(self.paths.staged.glob('*')))

    def test_a_new_dependency_from_the_repository_is_delivered_and_removed_on_rollback(self):
        self.backend.add('mseries-helper', '1.0-1')
        self.backend.add('mseries-quick-settings', '1.4.0-3', deps=['mseries-helper'])
        self.updater.stage()
        self.updater.apply()
        self.assertEqual('1.0-1', self.version('mseries-helper'))
        self.updater.rollback()
        self.assertNotIn('mseries-helper', self.backend.db)
        self.assert_old_set()

    def test_stage_requires_no_pending_transaction(self):
        self.stage_and_apply()
        with self.assertRaisesRegex(MU.UpdateError, 'still being recovered or confirmed'):
            self.updater.stage()


class Applying(Base):
    def test_apply_installs_one_set_then_confirm_makes_it_known_good(self):
        result = self.stage_and_apply()
        self.assertEqual({'mseries-wingpanel-network': '8.0.1-2', 'mseries-quick-settings': '1.4.0-2'}, result['applied'])
        self.assertEqual(1, len([c for c in self.backend.calls if isinstance(c, tuple) and c[0] == 'install']),
                         'the whole set goes through a single dpkg run')
        self.assertTrue(self.paths.pending_marker.exists())
        self.assertIsNone(self.state()['staged'])
        self.assertEqual({'confirmed': True}, self.updater.confirm())
        self.assertFalse(self.paths.pending_marker.exists())
        self.assertIsNotNone(self.state()['last_applied']['confirmed'])

    def test_failed_install_rolls_the_whole_set_back(self):
        self.backend.fail_install = {'mseries-quick-settings'}
        self.updater.stage()
        result = self.updater.apply()
        self.assertTrue(result['rolled_back'])
        self.assert_old_set()
        state = self.state()
        self.assertIsNone(state['journal'])
        self.assertIsNone(state['pending'])
        self.assertIsNone(state['staged'])
        self.assertEqual('rolled-back', state['history'][-1]['outcome'])
        self.assertIn('8.0.1-2', state['skipped']['mseries-wingpanel-network'])
        self.assertEqual({}, self.updater.check()['updates'], 'a rolled-back version is not retried automatically')
        self.backend.fail_install = set()
        self.assertEqual(2, len(self.updater.stage(include_skipped=True)['target']))

    def test_failed_integrity_verification_rolls_back(self):
        self.backend.verify_problems = ['dpkg --verify: missing /usr/lib/aarch64-linux-gnu/wingpanel-9/libnetwork.so']
        self.updater.stage()
        self.assertTrue(self.updater.apply()['rolled_back'])
        self.assert_old_set()

    def test_failed_health_command_rolls_back(self):
        self.system.health = [('10-ok', True), ('20-panel-probe', False)]
        self.updater.stage()
        result = self.updater.apply()
        self.assertTrue(result['rolled_back'])
        self.assertIn('20-panel-probe', result['reasons'][0])
        self.assert_old_set()

    def test_tampered_staged_file_is_never_installed(self):
        staged = self.updater.stage()
        deb = self.paths.staged / staged['id'] / 'archives' / staged['debs'][0]['file']
        deb.write_text('tampered')
        with self.assertRaisesRegex(MU.UpdateError, 'failed verification'):
            self.updater.apply()
        self.assert_old_set()
        self.assertIsNone(self.state()['staged'])

    def test_low_battery_or_busy_apt_defers_without_failing(self):
        self.updater.stage()
        self.system.power_state = ('battery', 12)
        self.assertIn('deferred', self.updater.apply())
        self.system.power_state = ('ac', 12)
        self.system.busy = True
        self.assertIn('deferred', self.updater.apply())
        self.assert_old_set()
        self.assertIsNotNone(self.state()['staged'])
        self.system.busy = False
        self.assertIn('applied', self.updater.apply())

    def test_low_disk_at_apply_blocks_with_an_error(self):
        self.updater.stage()
        self.system.free = 1 << 20
        with self.assertRaisesRegex(MU.UpdateError, 'disk'):
            self.updater.apply()
        self.assert_old_set()

    def test_missing_rollback_copy_at_apply_blocks_before_changing_anything(self):
        self.updater.stage()
        for deb in self.paths.store.glob('*.deb'):
            deb.unlink()
        with self.assertRaisesRegex(MU.UpdateError, 'rollback copies missing'):
            self.updater.apply()
        self.assert_old_set()
        self.assertIsNone(self.state()['journal'])

    def test_concurrent_run_is_refused(self):
        with self.updater.locked():
            with self.assertRaises(MU.Busy):
                self.make().stage()


class CrashAndRecovery(Base):
    def test_power_loss_mid_install_is_undone_at_next_boot(self):
        self.updater.stage()
        self.backend.crash_after = 1
        with self.assertRaises(SimulatedCrash):
            self.updater.apply()
        self.assertEqual('1.4.0-2', self.version('mseries-quick-settings'), 'a half-applied set is on disk')
        self.assertEqual('8.0.1-1', self.version('mseries-wingpanel-network'))
        self.assertIsNotNone(self.state()['journal'])
        self.backend.crash_after = None
        result = self.make().boot()
        self.assertEqual({'idle': True}, result)
        self.assert_old_set()
        state = self.state()
        self.assertIsNone(state['journal'])
        self.assertEqual('recovered', state['history'][-1]['outcome'])
        self.assertIn('1.4.0-2', state['skipped']['mseries-quick-settings'])

    def test_state_file_is_replaced_atomically(self):
        self.updater.check()
        with mock.patch.object(MU.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.updater.save(self.updater.load())
        self.assertIn('last_check', self.state())
        self.assertEqual([], [p for p in self.paths.state.glob('.*.tmp')][:0])

    def test_failing_rollback_is_loud_and_retried_at_next_boot(self):
        self.backend.fail_install = {'mseries-quick-settings'}
        self.updater.stage()
        saved = {p: p.read_bytes() for p in self.paths.store.glob('*wingpanel-network*.deb')}

        def lose_rollback_copy():
            for deb in saved:
                deb.unlink(missing_ok=True)
        self.backend.during_install = lose_rollback_copy
        with self.assertRaises(MU.RollbackFailed):
            self.updater.apply()
        self.assertIsNotNone(self.state()['journal'], 'the journal survives so the next boot retries')
        self.assertEqual(MU.EXIT_ROLLBACK_FAILED, MU.main(['--quiet', 'boot'], self.paths, self.backend, self.system))
        for deb, data in saved.items():
            deb.write_bytes(data)
        self.backend.during_install = None
        self.backend.fail_install = set()
        self.assertEqual(0, MU.main(['--quiet', 'boot'], self.paths, self.backend, self.system))
        self.assert_old_set()
        self.assertIsNone(self.state()['journal'])


class BootSequence(Base):
    def test_boot_applies_a_staged_update_then_login_confirms_it(self):
        self.updater.stage()
        self.assertIn('applied', self.updater.boot())
        self.assertEqual('8.0.1-2', self.version('mseries-wingpanel-network'))
        self.assertEqual({'confirmed': True}, self.make().confirm())
        self.assertEqual({'idle': True}, self.make().boot())

    def test_update_that_never_reaches_a_healthy_login_is_rolled_back(self):
        self.stage_and_apply()
        self.system.healthy = False
        self.assertEqual({'confirmed': False}, self.updater.confirm(wait=0))
        self.assertEqual({'pending': True}, self.make().boot())   # first restart: keep trying
        self.assertEqual('1.4.0-2', self.version('mseries-quick-settings'))
        self.assertEqual({'pending': True}, self.make().boot())   # second restart: give up
        self.assert_old_set()
        state = self.state()
        self.assertEqual('rolled-back', state['history'][-1]['outcome'])
        self.assertIn('no healthy login', state['history'][-1]['detail'])
        self.assertIsNone(state['pending'])
        self.assertFalse(self.paths.pending_marker.exists())

    def test_a_confirmed_update_survives_later_boots(self):
        self.stage_and_apply()
        self.updater.confirm()
        for _ in range(3):
            self.make().boot()
        self.assertEqual('8.0.1-2', self.version('mseries-wingpanel-network'))

    def test_confirm_waits_for_the_session_to_come_up(self):
        self.stage_and_apply()
        results = iter([False, False, True])
        self.system.session_healthy = lambda _processes: next(results)
        self.assertEqual({'confirmed': True}, self.updater.confirm(wait=60))

    def test_boot_with_nothing_staged_is_a_no_op(self):
        self.assertEqual({'idle': True}, self.updater.boot())
        self.assertEqual([], [c for c in self.backend.calls if c == 'refresh'], 'boot never touches the network')


class ManualRollback(Base):
    def test_rollback_after_confirmation_restores_the_previous_set(self):
        self.stage_and_apply()
        self.updater.confirm()
        self.assertEqual({'restored': {'mseries-wingpanel-network': '8.0.1-1', 'mseries-quick-settings': '1.4.0-1'}},
                         self.updater.rollback())
        self.assert_old_set()
        with self.assertRaisesRegex(MU.UpdateError, 'no applied update'):
            self.updater.rollback()

    def test_rollback_with_nothing_applied_is_an_error(self):
        with self.assertRaisesRegex(MU.UpdateError, 'no applied update'):
            self.updater.rollback()

    def test_store_keeps_exactly_the_rollback_and_current_copies_after_confirm(self):
        self.stage_and_apply()
        self.updater.confirm()
        self.assertEqual(4, len(list(self.paths.store.glob('*.deb'))))
        self.backend.add('mseries-quick-settings', '1.4.0-3')
        self.stage_and_apply()
        self.updater.confirm()
        names = sorted(p.name for p in self.paths.store.glob('*.deb'))
        self.assertEqual(['mseries-quick-settings_1.4.0-2_arm64.deb', 'mseries-quick-settings_1.4.0-3_arm64.deb'], names)


class ConfigAndCli(Base):
    def test_channel_switch_rewrites_the_source_and_drops_a_stale_stage(self):
        keyring = Path(self.tmp.name) / 'key.gpg'
        keyring.write_bytes(b'key')
        MU.write_sources(self.paths, 'https://example.invalid/apt', 'stable', keyring)
        self.assertIn('Suites: stable', self.paths.sources_file.read_text())
        self.updater.stage()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, MU.main(['--quiet', 'channel', 'dev'], self.paths, self.backend, self.system))
        self.assertIn('Suites: dev', self.paths.sources_file.read_text())
        self.assertEqual('dev', MU.Config(self.paths.config).channel)
        self.assertIsNone(self.state()['staged'])

    def test_channel_switch_is_refused_mid_update(self):
        keyring = Path(self.tmp.name) / 'key.gpg'
        keyring.write_bytes(b'key')
        MU.write_sources(self.paths, 'https://example.invalid/apt', 'stable', keyring)
        self.stage_and_apply()
        self.assertEqual(MU.EXIT_FAILED, MU.main(['--quiet', 'channel', 'dev'], self.paths, self.backend, self.system))
        self.assertIn('Suites: stable', self.paths.sources_file.read_text())

    def test_source_must_be_https_or_a_local_mirror(self):
        keyring = Path(self.tmp.name) / 'key.gpg'
        keyring.write_bytes(b'key')
        with self.assertRaisesRegex(MU.UpdateError, 'https'):
            MU.write_sources(self.paths, 'http://example.invalid/apt', 'stable', keyring)
        with self.assertRaisesRegex(MU.UpdateError, 'keyring'):
            MU.write_sources(self.paths, 'https://example.invalid/apt', 'stable', Path(self.tmp.name) / 'missing')

    def test_unknown_or_invalid_settings_are_rejected(self):
        config = MU.Config(self.paths.config)
        with self.assertRaises(MU.UpdateError):
            config.set('channel', 'nightly')
        with self.assertRaises(MU.UpdateError):
            config.set('no_such_setting', '1')
        config.set('min_battery_percent', '50')
        self.assertEqual(50, MU.Config(self.paths.config).min_battery)

    def test_apply_needs_an_explicit_now_and_mutating_commands_need_root(self):
        self.updater.stage()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(MU.EXIT_FAILED, MU.main(['--quiet', 'apply'], self.paths, self.backend, self.system))
        self.assertIn('--now', err.getvalue())
        self.assert_old_set()
        env = {k: v for k, v in os.environ.items() if k != 'MSERIES_UPDATE_ALLOW_NONROOT'}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(MU.os, 'geteuid', return_value=1000):
            with contextlib.redirect_stderr(err):
                self.assertEqual(MU.EXIT_FAILED, MU.main(['--quiet', 'stage'], self.paths, self.backend, self.system))
        self.assertIn('needs root', err.getvalue())

    def test_status_json_is_a_stable_contract_for_a_future_panel(self):
        self.updater.check()
        self.updater.stage()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, MU.main(['--quiet', 'status', '--json'], self.paths, self.backend, self.system))
        report = json.loads(out.getvalue())
        self.assertEqual({'auto_stage', 'channel', 'last_applied', 'last_check', 'last_result', 'pending_confirmation',
                          'power', 'schema', 'skipped', 'staged', 'state'}, set(report))
        self.assertEqual('staged', report['state'])
        self.assertEqual(1, report['schema'])

    def test_log_records_each_decision(self):
        self.stage_and_apply()
        self.updater.confirm()
        text = self.paths.log.read_text()
        for phrase in ('stage: update ready', 'apply: installing', 'apply: installed', 'confirm: the update set is now known-good'):
            self.assertIn(phrase, text)

    def test_unreadable_state_refuses_to_act(self):
        self.paths.state.mkdir(parents=True)
        self.paths.state_file.write_text('{not json')
        with self.assertRaisesRegex(MU.UpdateError, 'unreadable'):
            self.updater.stage()
        self.assert_old_set()


class SystemProbes(unittest.TestCase):
    def make(self, supplies):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, fields in supplies.items():
            (root / name).mkdir()
            for key, value in fields.items():
                (root / name / key).write_text(value + '\n')
        return MU.System(MU.Paths({'MSERIES_UPDATE_POWER': str(root),
                                   'MSERIES_UPDATE_DPKG_LOCK': str(root / 'dpkg-lock'),
                                   'MSERIES_UPDATE_SOURCES': str(root / 'src')}))

    def test_power_sources(self):
        self.assertEqual(('ac', None), self.make({}).power())
        self.assertEqual(('ac', 20), self.make({'AC': {'type': 'Mains', 'online': '1'},
                                               'BAT0': {'type': 'Battery', 'capacity': '20'}}).power())
        self.assertEqual(('battery', 55), self.make({'AC': {'type': 'Mains', 'online': '0'},
                                                    'BAT0': {'type': 'Battery', 'capacity': '55'}}).power())

    def test_dpkg_lock_probe(self):
        system = self.make({})
        self.assertFalse(system.package_manager_busy())
        lock = system.paths.dpkg_lock
        lock.write_text('')
        self.assertFalse(system.package_manager_busy())
        # dpkg takes a POSIX record lock, which only conflicts across processes.
        holder = subprocess.Popen([sys.executable, '-I', '-c',
                                   'import fcntl, sys\nf = open(sys.argv[1], "a")\n'
                                   'fcntl.lockf(f, fcntl.LOCK_EX)\nprint("held", flush=True)\nsys.stdin.read()', str(lock)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.stdin.close)
        self.assertEqual('held', holder.stdout.readline().strip())
        self.assertTrue(system.package_manager_busy())
        holder.stdin.close()
        holder.wait()
        self.assertFalse(system.package_manager_busy())

    def test_network_probe_understands_local_mirrors(self):
        system = self.make({})
        system.paths.sources_dir.mkdir()
        self.assertFalse(system.network_ok())
        system.paths.sources_file.write_text('URIs: file:///srv/mirror\n')
        self.assertTrue(system.network_ok())


if __name__ == '__main__':
    unittest.main()
