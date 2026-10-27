"""Synthetic ownership/admission/API checks; never start a real worker."""
import contextlib
import importlib.util
import hashlib
import os
import copy
import subprocess
import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock
import unittest
from unittest.mock import patch

import diagnostic_runtime as runtime

spec = importlib.util.spec_from_file_location('diagnostic_worker', Path(__file__).with_name('model-worker.py'))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def config():
    return {'policy': {'reserve_gib': 6, 'max_fan_rpm': 3500, 'max_temp_c': 80},
            'profiles': {'diagnostic': {'engine': 'mlx', 'model': 'qwen3.5-9b-mlx-4bit',
                'context': 4096, 'port': 8772, 'admission_gib': 9}}}


def sample(available=20, fan=2500, temperature=50):
    return {'available_bytes': int(available * runtime.GIB), 'fans_rpm': {'fan': fan},
            'temperatures_c': {'sensor': temperature}}


class PolicyTests(unittest.TestCase):
    def test_worker_diagnostic_clamps_limits_and_immediate_stop(self):
        settings = config()
        settings['profiles']['diagnostic']['policy'] = {
            'reserve_gib': 1, 'max_fan_rpm': 9000, 'max_temp_c': 99,
            'sample_s': 9, 'stop_after_samples': 9}
        policy = worker.profile_policy(settings, settings['profiles']['diagnostic'], 'diagnostic')
        self.assertEqual(policy['reserve_gib'], 6)
        self.assertEqual(policy['max_fan_rpm'], 2700)
        self.assertEqual(policy['max_temp_c'], 63)
        self.assertEqual(policy['stop_after_samples'], 1)
        self.assertEqual(policy['sample_s'], 1)
        self.assertTrue(worker.policy_violations(sample(fan=2700), policy, strict=True))
        self.assertTrue(worker.policy_violations(sample(temperature=63), policy, strict=True))
        self.assertTrue(worker.policy_violations(sample(fan=2600), policy, admission=True))
        self.assertTrue(worker.policy_violations(sample(temperature=58), policy, admission=True))

    def test_worker_override_only_tightens_existing_policy(self):
        settings = {'policy': {'reserve_gib': 8, 'max_fan_rpm': 2400, 'max_temp_c': 57}}
        policy = worker.profile_policy(settings, {'policy': {'reserve_gib': 2, 'max_fan_rpm': 4000}}, 'diagnostic')
        self.assertEqual((policy['reserve_gib'], policy['max_fan_rpm'], policy['max_temp_c']), (8, 2400, 57))
        self.assertEqual(worker.profile_policy(config(), {}, 'everyday')['max_fan_rpm'], 3500)
        for invalid in ({'reserve_gib': float('nan')}, {'sample_s': False}, {'unknown': 2}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                worker.profile_policy(config(), {'policy': invalid}, 'diagnostic')

    def test_isolated_config_cannot_relax_owner_global_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            standard = home / '.config/mseries-ai/profiles.json'
            standard.parent.mkdir(parents=True)
            standard.write_text(json.dumps({'policy': {'reserve_gib': 8, 'max_fan_rpm': 2500, 'max_temp_c': 57}}))
            selected = standard.with_name('diagnostic-profile.json')
            selected.write_text(json.dumps(config()))
            loaded = worker.load_config(selected, home)
            self.assertEqual(loaded['policy']['reserve_gib'], 8)
            self.assertEqual(loaded['policy']['max_fan_rpm'], 2500)
            self.assertEqual(loaded['policy']['max_temp_c'], 57)
            self.assertEqual(json.loads(standard.read_text())['policy']['reserve_gib'], 8)

    def test_runtime_admission_reserve_and_exact_boundaries(self):
        with patch.object(runtime, 'read_config', return_value=config()), patch.object(runtime.Path, 'home', return_value=Path('/nonexistent-diagnostic-test-home')):
            with patch.object(runtime, 'snapshot', return_value=sample(15)):
                self.assertEqual(runtime.quiet_reasons(9 * runtime.GIB, admission=True), [])
            for measured in (sample(14.99), sample(20, 2600), sample(20, 2500, 58),
                             sample(20, float('nan')), {'available_bytes': 30 * runtime.GIB, 'fans_rpm': {}, 'temperatures_c': {}}):
                with self.subTest(measured=measured), patch.object(runtime, 'snapshot', return_value=measured):
                    self.assertTrue(runtime.quiet_reasons(9 * runtime.GIB, admission=True))

    def test_worker_stops_owned_child_on_first_limit_or_mid_generation_f5(self):
        import io
        for reason in ('f5', 'fan', 'temperature'):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                settings = config()
                # Synthetic command construction only; Popen is always mocked.
                settings['profiles']['diagnostic'].update(engine='llama', model='/synthetic/not-real.gguf')
                path = home / '.config/mseries-ai/profiles.json'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(settings))
                child = MagicMock(pid=99999999)
                child.returncode = 0
                stopped = []
                child.poll.side_effect = lambda: 0 if stopped else None
                child.terminate.side_effect = lambda: stopped.append(True)
                measured = sample(fan=2700) if reason == 'fan' else sample(temperature=63) if reason == 'temperature' else sample()
                output = io.StringIO()
                with patch.object(worker.Path, 'home', return_value=home), \
                     patch('sys.argv', ['model-worker.py', 'diagnostic']), \
                     patch.object(worker, 'snapshot', side_effect=[sample(), measured]), \
                     patch.object(worker, 'diagnostic_speech_busy', side_effect=[False, reason == 'f5']), \
                     patch.object(worker.subprocess, 'Popen', return_value=child), \
                     patch.object(worker.signal, 'signal'), patch.object(worker.os, 'killpg') as group_signal, \
                     patch.object(worker.time, 'sleep') as sleep, contextlib.redirect_stdout(output):
                    self.assertEqual(worker.main(), 0)
                child.terminate.assert_called_once()
                sleep.assert_not_called()
                self.assertTrue(all(call.args[0] == child.pid for call in group_signal.call_args_list))
                self.assertIn('F5 priority' if reason == 'f5' else 'QUIET POLICY STOP', output.getvalue())
                if reason == 'f5':
                    self.assertIn('unscored', output.getvalue())

    def test_unavailable_speech_guard_is_busy(self):
        with patch.object(runtime, 'speech_idle', side_effect=OSError('unavailable')):
            self.assertTrue(worker.diagnostic_speech_busy())


class ApiTests(unittest.TestCase):
    def test_exact_snapshot_with_cached_aliases_is_compatible(self):
        exact = str(runtime.snapshot_path())
        with patch.object(runtime, '_request', return_value={'data': [{'id': 'cached/other-model'}, {'id': exact}]}):
            self.assertEqual(runtime.verify_model(), exact)
        for ids in ([runtime.MODEL_REPO], ['/tmp/' + runtime.MODEL_REVISION],
                    [exact, '/tmp/other-snapshot'], [exact, exact]):
            with self.subTest(ids=ids), patch.object(runtime, '_request', return_value={'data': [{'id': value} for value in ids]}), self.assertRaises(runtime.Deferred):
                runtime.verify_model()

    def test_each_generation_rechecks_identity_and_quiet_before_post(self):
        exact = str(runtime.snapshot_path())
        with patch.object(runtime, 'verify_model', return_value=exact) as verify, \
             patch.object(runtime, 'quiet_reasons', return_value=[]), \
             patch.object(runtime, '_f5_idle', return_value=True), \
             patch.object(runtime, '_request', return_value={'choices': []}) as request:
            runtime.api(runtime.ENDPOINT, '/v1/chat/completions', {'model': exact})
            runtime.api(runtime.ENDPOINT, '/v1/chat/completions', {'model': exact})
            self.assertEqual(verify.call_count, 2)
            self.assertEqual(request.call_count, 2)
            with self.assertRaises(runtime.Deferred):
                runtime.api(runtime.ENDPOINT, '/v1/chat/completions', {'model': runtime.MODEL_REPO})
            self.assertEqual(request.call_count, 2)
        with patch.object(runtime, 'verify_model', return_value=exact), patch.object(runtime, 'quiet_reasons', return_value=['memory guard']), patch.object(runtime, '_request') as request, self.assertRaises(runtime.Deferred):
            runtime.api(runtime.ENDPOINT, '/v1/chat/completions', {'model': exact})
        request.assert_not_called()

    def test_unknown_endpoint_and_redirect_refused_without_network(self):
        for endpoint in ('http://localhost:8772', 'http://127.0.0.1:8766', 'https://127.0.0.1:8772', 'http://user:secret@127.0.0.1:8772'):
            with self.subTest(endpoint=endpoint), patch.object(runtime.urllib.request, 'build_opener') as opener, self.assertRaises(runtime.Deferred):
                runtime._request(endpoint, '/v1/models')
            opener.assert_not_called()
        with self.assertRaises(runtime.Deferred):
            runtime._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.test')


class PrivateFilesTests(unittest.TestCase):
    def test_unit_ownership_requires_expected_installed_command(self):
        path = runtime.worker_path()
        row = {'FragmentPath': str(Path.home() / '.config/systemd/user' / runtime.DIAGNOSTIC),
               'ExecStart': '{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 ' + str(path) +
                   ' diagnostic --config ' + str(runtime.config_path()) + ' ; ignore_errors=no ; }', 'MainPID': 123}
        runtime._validate_unit(runtime.DIAGNOSTIC, row)
        for key, value in [('FragmentPath', '/tmp/unowned.service'), ('ExecStart', '/usr/bin/unknown')]:
            bad = dict(row); bad[key] = value
            with self.subTest(key=key), self.assertRaises(runtime.Deferred):
                runtime._validate_unit(runtime.DIAGNOSTIC, bad)
        with patch.object(runtime.Path, 'read_bytes', return_value=b'/usr/bin/python3\0/tmp/unknown.py\0'), self.assertRaises(runtime.Deferred):
            runtime._validate_unit(runtime.DIAGNOSTIC, row, running=True)

    def test_configuration_is_bounded_pinned_and_never_modifies_global(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime.Path, 'home', return_value=Path(directory)):
            path = runtime.config_path()
            path.parent.mkdir(parents=True)
            path.touch(mode=0o600)
            path.write_text(json.dumps(config()))
            model = runtime.snapshot_path()
            model.mkdir(parents=True)
            (model / 'config.json').write_text('{}')
            (model / 'model.safetensors').write_bytes(b'synthetic-placeholder-not-weights')
            self.assertEqual(runtime.read_config(), config())
            before = path.read_bytes()
            for name, value in [('port', 8766), ('context', 64000), ('model', '4b'), ('admission_gib', 8), ('admission_gib', float('inf'))]:
                settings = config(); settings['profiles']['diagnostic'][name] = value
                path.write_text(json.dumps(settings))
                with self.subTest(name=name, value=value), self.assertRaises(runtime.Deferred):
                    runtime.read_config()
            path.write_bytes(before)
            target = path.with_suffix('.target'); path.rename(target); path.symlink_to(target)
            with self.assertRaises(OSError):
                runtime.read_config()

    def accepted_report(self, directory):
        identity = {'fixtures_sha256': {'synthetic': '1' * 64},
                    'source_sha256': {'diagnostic_agent.py': '2' * 64}, 'kernel': 'test-kernel'}
        metadata = {'acceptance_identity': identity}
        recorded = {'repeat': 1, 'split': 'all', 'kernel': identity['kernel'], 'endpoint': runtime.ENDPOINT,
                    'source_sha256': identity['source_sha256'], 'fixtures_sha256': identity['fixtures_sha256'],
                    'metadata_sha256': runtime._canonical_hash(metadata)}
        report = {'schema_version': 'mseries.diagnostic.qualification.v1', 'identity': recorded,
                  'metadata': metadata, 'qualified': False, 'complete': True, 'quiet_policy_passed': True,
                  'completed_trials': 1, 'automatic_passes': 1, 'trials': [
                      {'case_id': 'synthetic', 'repeat': 0, 'status': 'completed', 'automatic_pass': True,
                       'attempts': [{'status': 'completed', 'quality_scored': True,
                                     'resources': {'quiet_policy_passed': True, 'telemetry_complete': True}}]}]}
        state = Path(directory) / '.local/state/mseries-troubleshooter'
        state.mkdir(parents=True, mode=0o700)
        receipt = {'schema_version': runtime.ACCEPTANCE_SCHEMA, 'qualified': True, 'identity': identity,
                   'report': {'file': 'reviewed.json'}, 'decision': {'verdict': 'accepted', 'reviewer': 'synthetic-reviewer',
                   'reviewed_identity_sha256': runtime._canonical_hash(identity), 'reviewed_cases': ['synthetic']}}
        def save():
            raw = json.dumps(report).encode()
            digest = hashlib.sha256(raw).hexdigest()
            receipt['report']['sha256'] = digest
            receipt['decision']['reviewed_report_sha256'] = digest
            for path, data in [(state / 'reviewed.json', raw),
                               (state / 'diagnostic-qualification.json', json.dumps(receipt).encode())]:
                path.write_bytes(data); path.chmod(0o600)
        save()
        return identity, receipt, report, save, state

    def test_qualification_requires_reviewed_exact_identity_and_complete_report(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime.Path, 'home', return_value=Path(directory)):
            identity, receipt, report, save, state = self.accepted_report(directory)
            with patch.object(runtime, 'qualification_identity', return_value=identity):
                runtime.require_qualified()
                original = copy.deepcopy(report)
                mutations = [lambda: report.update(frozen_integrity_error=True),
                    lambda: report.update(qualified=True), lambda: report.update(automatic_passes=0),
                    lambda: report['identity'].update(repeat=True),
                    lambda: report['identity'].update(fixtures_sha256={}),
                    lambda: report.update(trials=[]),
                    lambda: report['trials'][0].update(automatic_pass=False),
                    lambda: report['trials'][0]['attempts'][0]['resources'].update(telemetry_complete=False)]
                for mutate in mutations:
                    report.clear(); report.update(copy.deepcopy(original)); mutate(); save()
                    with self.subTest(report=report), self.assertRaises(runtime.Deferred):
                        runtime.require_qualified()
                report.clear(); report.update(original); save()
                for key in ('reviewed_report_sha256', 'reviewed_identity_sha256', 'reviewed_cases', 'reviewer'):
                    saved = receipt['decision'].pop(key); save()
                    receipt['decision'].pop(key, None)
                    (state / 'diagnostic-qualification.json').write_text(json.dumps(receipt))
                    with self.subTest(key=key), self.assertRaises(runtime.Deferred):
                        runtime.require_qualified()
                    receipt['decision'][key] = saved
                save()
                report_file = state / 'reviewed.json'
                report_file.write_bytes(report_file.read_bytes() + b' ')
                with self.assertRaises(runtime.Deferred): runtime.require_qualified()
                save(); report_file.rename(state / 'other.json'); report_file.symlink_to('other.json')
                with self.assertRaises(runtime.Deferred): runtime.require_qualified()

    def test_automatic_harness_receipt_cannot_promote_itself(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime.Path, 'home', return_value=Path(directory)):
            identity, receipt, report, save, state = self.accepted_report(directory)
            with patch.object(runtime, 'qualification_identity', return_value=identity):
                path = state / 'diagnostic-qualification.json'
                path.write_text(json.dumps(report))
                with self.assertRaises(runtime.Deferred): runtime.require_qualified()
                for malformed in ([], None, {'qualified': True, 'identity': identity},
                                  dict(receipt, decision=[]), dict(receipt, report=[])):
                    path.write_text(json.dumps(malformed))
                    with self.subTest(malformed=malformed), self.assertRaises(runtime.Deferred):
                        runtime.require_qualified()

    def test_identity_changes_with_prompt_contract_model_config_and_fixture_bytes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime.Path, 'home', return_value=Path(directory)):
            home = Path(directory)
            selected = runtime.config_path(); selected.parent.mkdir(parents=True)
            selected.write_text(json.dumps(config()))
            (selected.parent / 'profiles.json').write_text('{}')
            source = runtime.worker_path().parent; source.mkdir(parents=True)
            for name in runtime.QUALIFICATION_SOURCES: (source / name).write_text('# synthetic ' + name)
            fixtures = source / 'fixtures/diagnostic'; fixtures.mkdir(parents=True)
            fixture = fixtures / 'synthetic.json'
            fixture.write_text(json.dumps({'fixture_schema_version': 'mseries.diagnostic.fixture.v1',
                                          'case_id': 'synthetic', 'split': 'core'}))
            model = runtime.snapshot_path(); model.mkdir(parents=True)
            for name in ('config.json', 'tokenizer.json', 'tokenizer_config.json'):
                (model / name).write_text('{}')
            shard = model / 'model-00001.safetensors'; shard.write_bytes(b'synthetic-not-weights')
            (model / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'w': shard.name}}))
            prefix = home / 'runtime'; library = prefix / 'venv/lib/python3/site-packages/mlx/lib/libmlx.so'
            library.parent.mkdir(parents=True); library.write_bytes(b'synthetic-not-a-library')
            with patch.object(runtime, 'runtime_prefix', return_value=prefix):
                original = runtime.qualification_identity()
                for path in (source / 'diagnostic_agent.py', source / 'diagnostic_contract.py',
                             source / 'diagnostic-qualification.py', shard, model / 'config.json', fixture):
                    before = path.read_bytes(); path.write_bytes(before + b' ')
                    with self.subTest(path=path.name):
                        self.assertNotEqual(runtime.qualification_identity(), original)
                    path.write_bytes(before)
                outside = home / 'outside.safetensors'; outside.write_bytes(b'outside')
                shard.unlink(); shard.symlink_to(outside)
                with self.assertRaises(runtime.Deferred): runtime.qualification_identity()

    def test_tcp_established_ipv4_and_ipv6_are_busy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('tcp', 'tcp6'):
                (root / name).write_text('header\n')
            self.assertFalse(runtime._established_local(proc=root))
            for name in ('tcp', 'tcp6'):
                (root / name).write_text('header\n0: 0100007F:223E 0100007F:ABCD 01 0 0\n')
                self.assertTrue(runtime._established_local(proc=root))
                (root / name).write_text('header\n0: 0100007F:223E 00000000:0000 0A 0 0\n')
                self.assertFalse(runtime._established_local(proc=root))

    def test_f5_busy_and_wrong_pid_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(runtime.os.environ, {'XDG_RUNTIME_DIR': directory}), patch.object(runtime, '_run', return_value='ActiveState=active\nMainPID=123\n'), patch.object(runtime, '_process_identity', return_value=(123, 'start')):
            target = Path(directory) / 'mseries-dictation/status.json'
            target.parent.mkdir()
            self.assertFalse(runtime._f5_idle())
            target.touch(mode=0o600)
            for phase in ('loading', 'listening', 'finishing'):
                target.write_text(json.dumps({'pid': 123, 'phase': phase}))
                self.assertFalse(runtime._f5_idle())
            target.write_text(json.dumps({'pid': 123, 'phase': 'ready'}))
            self.assertTrue(runtime._f5_idle())
            target.write_text(json.dumps({'pid': 456, 'phase': 'ready'}))
            self.assertFalse(runtime._f5_idle())
            target.write_text(json.dumps({'pid': 123, 'phase': 'ready'}))
            with patch.object(runtime, '_process_identity', side_effect=FileNotFoundError):
                self.assertFalse(runtime._f5_idle())
            target.chmod(0o644)
            self.assertFalse(runtime._f5_idle())


class ExactProcessStopTests(unittest.TestCase):
    def test_pidfd_stop_checks_invocation_and_recycled_pid_before_signal(self):
        row = {'ActiveState': 'active', 'InvocationID': 'a' * 32, 'MainPID': 123, 'Restart': 'no'}
        identity = (123, 'original-starttime')
        for replacement in ('invocation', 'pid', 'starttime'):
            changed = dict(row)
            second_identity = identity
            if replacement == 'invocation': changed['InvocationID'] = 'b' * 32
            if replacement == 'pid': changed['MainPID'] = 456
            if replacement == 'starttime': second_identity = (123, 'recycled-starttime')
            with self.subTest(replacement=replacement), \
                 patch.object(runtime, 'unit_info', side_effect=[row, changed]), \
                 patch.object(runtime, '_validate_unit', side_effect=[identity, second_identity]), \
                 patch.object(runtime.os, 'pidfd_open', return_value=42), \
                 patch.object(runtime.os, 'close') as close, \
                 patch.object(runtime.signal, 'pidfd_send_signal') as send, self.assertRaises(runtime.Deferred):
                runtime._stop_owned(runtime.DIAGNOSTIC, identity, 'a' * 32)
            send.assert_not_called(); close.assert_called_once_with(42)

    def test_signal_intent_is_recorded_before_send_and_descriptor_is_closed(self):
        row = {'ActiveState': 'active', 'InvocationID': 'a' * 32, 'MainPID': 123, 'Restart': 'no'}
        events = []
        with patch.object(runtime, 'unit_info', return_value=row), \
             patch.object(runtime, '_validate_unit', return_value=(123, 'starttime')), \
             patch.object(runtime.os, 'pidfd_open', return_value=42), \
             patch.object(runtime.os, 'close') as close, \
             patch.object(runtime.signal, 'pidfd_send_signal', side_effect=lambda *args: events.append('signal')), \
             patch.object(runtime.select, 'select', return_value=([42], [], [])):
            self.assertTrue(runtime._stop_owned(runtime.DIAGNOSTIC, (123, 'starttime'), 'a' * 32,
                                               before_signal=lambda: events.append('intent')))
        self.assertEqual(events, ['intent', 'signal']); close.assert_called_once_with(42)

    def test_restart_policy_cannot_resurrect_cancelled_owned_worker(self):
        row = {'ActiveState': 'active', 'InvocationID': 'a' * 32, 'MainPID': 123, 'Restart': 'always'}
        with patch.object(runtime, 'unit_info', return_value=row), \
             patch.object(runtime, '_validate_unit', return_value=(123, 'starttime')), \
             patch.object(runtime.os, 'pidfd_open') as opened, self.assertRaises(runtime.Deferred):
            runtime._stop_owned(runtime.DIAGNOSTIC, (123, 'starttime'), 'a' * 32)
        opened.assert_not_called()


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(runtime, 'OWNED_START_READY', True))
        self.stack.enter_context(patch.object(runtime.Path, 'home', return_value=Path(self.temp.name)))
        self.state = {runtime.DIAGNOSTIC: 'inactive', runtime.EVERYDAY: 'inactive'}
        self.calls = []
        self.invocations = {runtime.DIAGNOSTIC: '', runtime.EVERYDAY: 'e' * 32}
        def info(unit):
            return {'ActiveState': self.state[unit], 'MainPID': 22 if unit == runtime.DIAGNOSTIC else 11,
                    'UnitFileState': 'enabled', 'InvocationID': self.invocations[unit], 'Job': '', 'Restart': 'no'}
        def run(*args):
            self.calls.append(args)
            if args[0] in ('start', 'stop'):
                unit = args[-1]
                self.state[unit] = 'active' if args[0] == 'start' else 'inactive'
                if args[0] == 'start': self.invocations[unit] = 'd' * 32 if unit == runtime.DIAGNOSTIC else 'f' * 32
            return ''
        self.run = run
        self.info = info
        def stop(unit, identity, invocation, *, before_signal=lambda: None):
            if self.state[unit] != 'active': return False
            if invocation != self.invocations[unit]: raise runtime.Deferred('invocation changed')
            before_signal()
            run('stop', unit)
            return True
        self.stop = stop
        self.stack.enter_context(patch.object(runtime, '_stop_owned', side_effect=stop))
        self.stack.enter_context(patch.object(runtime, 'read_config', return_value=config()))
        self.stack.enter_context(patch.object(runtime, 'require_qualified'))
        self.stack.enter_context(patch.object(runtime, 'unit_info', side_effect=info))
        self.stack.enter_context(patch.object(runtime, '_validate_unit', side_effect=lambda unit, row, running=False: (row['MainPID'], 'start') if running else None))
        self.stack.enter_context(patch.object(runtime, '_same_process', side_effect=lambda unit, identity: self.state[unit] == 'active'))
        self.stack.enter_context(patch.object(runtime, '_other_active', return_value=[]))
        self.stack.enter_context(patch.object(runtime, '_f5_idle', return_value=True))
        self.stack.enter_context(patch.object(runtime, '_port_free'))
        self.stack.enter_context(patch.object(runtime, 'quiet_reasons', return_value=[]))
        self.stack.enter_context(patch.object(runtime, '_established_local', return_value=False))
        self.stack.enter_context(patch.object(runtime, '_run', side_effect=run))
        self.stack.enter_context(patch.object(runtime, 'verify_model', return_value='pinned-model'))
        self.stack.enter_context(patch.object(runtime.time, 'sleep'))
        global_path = Path(self.temp.name) / '.config/mseries-ai/profiles.json'
        global_path.parent.mkdir(parents=True)
        global_path.write_text(json.dumps({'profiles': {'everyday': {'engine': 'mlx', 'model': 'qwen3.5-4b-mseries-4bit', 'admission_gib': 6.5}}}))

    def test_unimplemented_attribution_gate_refuses_before_any_service_mutation(self):
        with patch.object(runtime, 'OWNED_START_READY', False), self.assertRaisesRegex(runtime.Deferred, 'runtime is off'):
            with runtime.session(exclusive=True, require_qualification=False): self.fail('unexpected')
        self.assertEqual(self.calls, [])

    def test_normal_session_starts_and_stops_only_owned_diagnostic(self):
        with runtime.session() as lifecycle:
            self.assertTrue(lifecycle['diagnostic_started'])
        self.assertEqual(self.calls, [('start', '--no-block', runtime.DIAGNOSTIC), ('stop', runtime.DIAGNOSTIC)])
        self.assertIn('exact owned', lifecycle['diagnostic_stop'])

    def test_cancellation_releases_own_worker(self):
        with self.assertRaises(KeyboardInterrupt):
            with runtime.session():
                raise KeyboardInterrupt()
        self.assertEqual(self.calls[-1], ('stop', runtime.DIAGNOSTIC))

    def test_active_everyday_requires_explicit_exclusive(self):
        self.state[runtime.EVERYDAY] = 'active'
        with self.assertRaises(runtime.Deferred):
            with runtime.session():
                self.fail('unexpected session')
        self.assertEqual(self.calls, [])

    def test_explicit_exclusive_checks_three_times_restores_prior_default(self):
        self.state[runtime.EVERYDAY] = 'active'
        with patch.object(runtime, '_established_local', return_value=False) as idle:
            with runtime.session(exclusive=True) as lifecycle:
                self.assertTrue(lifecycle['everyday_released'])
            self.assertEqual(idle.call_count, 3)
        self.assertEqual(self.calls, [('stop', runtime.EVERYDAY), ('start', '--no-block', runtime.DIAGNOSTIC),
                                     ('stop', runtime.DIAGNOSTIC), ('start', runtime.EVERYDAY)])
        self.assertIn('previously enabled', lifecycle['restore'])

    def test_busy_tcp_or_f5_never_stops_everyday(self):
        self.state[runtime.EVERYDAY] = 'active'
        for name in ('_established_local', '_f5_idle'):
            with self.subTest(name=name), patch.object(runtime, name, return_value=name == '_established_local'), self.assertRaises(runtime.Deferred):
                with runtime.session(exclusive=True):
                    self.fail('unexpected session')
        self.assertEqual(self.calls, [])

    def test_selected_other_profile_or_existing_diagnostic_never_stopped(self):
        with patch.object(runtime, '_other_active', return_value=['mseries-ai-coder.service']), self.assertRaises(runtime.Deferred):
            with runtime.session(exclusive=True):
                self.fail('unexpected session')
        self.state[runtime.DIAGNOSTIC] = 'active'
        with self.assertRaises(runtime.Deferred):
            with runtime.session(exclusive=True):
                self.fail('unexpected session')
        self.assertEqual(self.calls, [])

    def test_changed_diagnostic_pid_never_receives_stop(self):
        with runtime.session() as lifecycle:
            self.state[runtime.DIAGNOSTIC] = 'inactive'
        self.assertEqual(self.calls, [('start', '--no-block', runtime.DIAGNOSTIC)])
        self.assertIn('identity changed', lifecycle['diagnostic_stop'])

    def test_restore_deferred_if_owner_changes_settings(self):
        self.state[runtime.EVERYDAY] = 'active'
        with runtime.session(exclusive=True) as lifecycle:
            path = Path(self.temp.name) / '.config/mseries-ai/profiles.json'
            path.write_text(path.read_text() + '\n')
        self.assertNotIn(('start', runtime.EVERYDAY), self.calls)
        self.assertIn('settings changed', lifecycle['restore'])

    def test_prior_model_restored_after_diagnostic_start_failure(self):
        self.state[runtime.EVERYDAY] = 'active'
        with patch.object(runtime, '_port_free', side_effect=runtime.Deferred('occupied')), self.assertRaises(runtime.Deferred):
            with runtime.session(exclusive=True):
                self.fail('unexpected session')
        self.assertEqual(self.calls, [('stop', runtime.EVERYDAY), ('start', runtime.EVERYDAY)])

    def test_cancel_before_start_does_not_mutate_services(self):
        with patch.object(runtime, '_port_free', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            with runtime.session(): self.fail('unexpected')
        self.assertEqual(self.calls, [])

    def test_interrupt_in_everyday_stop_restores_after_its_signal(self):
        self.state[runtime.EVERYDAY] = 'active'
        def stop(unit, identity, invocation, **kwargs):
            self.stop(unit, identity, invocation, **kwargs)
            if unit == runtime.EVERYDAY: raise KeyboardInterrupt()
        with patch.object(runtime, '_stop_owned', side_effect=stop), self.assertRaises(KeyboardInterrupt):
            with runtime.session(exclusive=True): self.fail('unexpected')
        self.assertEqual(self.calls, [('stop', runtime.EVERYDAY), ('start', runtime.EVERYDAY)])

    def test_validation_failure_after_accepted_start_recovers_owned_invocation(self):
        failed = []
        def validate(unit, row, running=False):
            if unit == runtime.DIAGNOSTIC and running and not failed:
                failed.append(True); raise runtime.Deferred('transient proc read failed')
            return (row['MainPID'], 'start') if running else None
        with patch.object(runtime, '_validate_unit', side_effect=validate), self.assertRaises(runtime.Deferred):
            with runtime.session(): self.fail('unexpected')
        self.assertEqual(self.calls, [('start', '--no-block', runtime.DIAGNOSTIC), ('stop', runtime.DIAGNOSTIC)])

    def test_cancel_after_accepted_start_before_identity_recovers_owned_worker(self):
        original = runtime._capture_start
        calls = []
        def capture(*args):
            calls.append(True)
            if len(calls) == 1: raise KeyboardInterrupt()
            return original(*args)
        with patch.object(runtime, '_capture_start', side_effect=capture), self.assertRaises(KeyboardInterrupt):
            with runtime.session(): self.fail('unexpected')
        self.assertEqual(self.calls[-1], ('stop', runtime.DIAGNOSTIC))

    def test_ambiguous_interrupted_start_retains_recovery_and_does_not_restore(self):
        self.state[runtime.EVERYDAY] = 'active'
        def run(*args):
            self.run(*args)
            if args == ('start', '--no-block', runtime.DIAGNOSTIC):
                raise subprocess.TimeoutExpired('synthetic-systemctl', 45)
        with patch.object(runtime, '_run', side_effect=run), self.assertRaises(subprocess.TimeoutExpired):
            with runtime.session(exclusive=True): self.fail('unexpected')
        self.assertNotIn(('stop', runtime.DIAGNOSTIC), self.calls)
        self.assertNotIn(('start', runtime.EVERYDAY), self.calls)
        paths = list((Path(self.temp.name) / '.local/state/mseries-troubleshooter').glob('runtime-recovery-*.json'))
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].stat().st_mode & 0o777, 0o600)
        self.assertIn('unsettled', json.loads(paths[0].read_text())['lifecycle']['restore'])

    def test_replacement_invocation_never_receives_stop(self):
        with runtime.session() as lifecycle:
            self.invocations[runtime.DIAGNOSTIC] = 'a' * 32
        self.assertNotIn(('stop', runtime.DIAGNOSTIC), self.calls)
        self.assertIn('deferred', lifecycle['diagnostic_stop'])

    def test_shared_analysis_lock_refuses_nested_session(self):
        with runtime.session():
            with self.assertRaisesRegex(runtime.Deferred, 'Another local analysis'):
                with runtime.session():
                    self.fail('duplicate session')
        self.assertEqual(self.calls, [('start', '--no-block', runtime.DIAGNOSTIC), ('stop', runtime.DIAGNOSTIC)])


if __name__ == '__main__':
    unittest.main()
