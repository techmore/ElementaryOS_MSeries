import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import io
import signal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


os_mcp = load('os_mcp_test', 'os-mcp.py')
machine = load('machine_test', 'machine.py')
crash = load('crash_test', 'crash-watch.py')
branch = load('branch_test', 'branch-watch.py')
bench = load('bench_test', 'benchmark.py')
worker = load('worker_test', 'model-worker.py')
dashboard = load('dashboard_test', 'github-watch.py')
setup = load('setup_test', 'configure-assistants.py')
task_smoke = load('task_smoke_test', 'task-write-smoke.py')


class AssistantContracts(unittest.TestCase):
    def test_task_resume_retains_completed_failures_and_rejects_changed_runtime(self):
        meta = {'method': 'v1', 'kernel': 'same', 'adapter_sha256': 'same', 'harness_sha256': 'same', 'policy': {}, 'repeats': 1}
        previous = meta | {'model_cases': [{'case': 'note-to-task', 'repeat': 1, 'passed': False},
                                          {'case': 'file-injection', 'repeat': 1, 'passed': None}]}
        rows, completed, interrupted = task_smoke.resume_cases(previous, meta, 1)
        self.assertEqual(len(rows), 1)
        self.assertIn(('note-to-task', 1), completed)
        self.assertEqual(len(interrupted), 1)
        with self.assertRaises(ValueError): task_smoke.resume_cases(previous, meta | {'kernel': 'changed'}, 1)

    def test_malformed_model_task_arguments_are_quality_failure_not_interruption(self):
        model = '/pinned/32f3e8ecf65426fc3306969496342d504bfa13f3'
        for arguments in ['{invalid', '[]']:
            responses = [{'data': [{'id': model}]}, {'choices': [{'message': {'content': '', 'tool_calls': [
                {'id': 'bad-call', 'function': {'name': 'create_assistant_task', 'arguments': arguments}}]}}]}]
            with patch.object(task_smoke, 'MCP') as client, patch.object(task_smoke, 'api', side_effect=responses), \
                 patch.object(task_smoke, 'snapshot', return_value={}), patch.object(task_smoke, 'violations', return_value=[]), \
                 patch.object(task_smoke, 'cleanup', return_value=True):
                client.return_value.rpc.return_value = {'tools': []}
                result = task_smoke.model_case('http://127.0.0.1:8766/v1', 'note-to-task', 1)
            self.assertIs(result['passed'], False)
            self.assertIn('invalid_tool_call', result)

    def test_interrupted_model_request_is_not_a_completed_task_quality_failure(self):
        responses = [{'data': [{'id': '/pinned/32f3e8ecf65426fc3306969496342d504bfa13f3'}]}, TimeoutError('Interrupted')]
        with patch.object(task_smoke, 'MCP') as client, patch.object(task_smoke, 'api', side_effect=responses), \
             patch.object(task_smoke, 'snapshot', return_value={}), patch.object(task_smoke, 'violations', return_value=[]), \
             patch.object(task_smoke, 'cleanup', return_value=True):
            client.return_value.rpc.return_value = {'tools': []}
            result = task_smoke.model_case('http://127.0.0.1:8766/v1', 'note-to-task', 1)
        self.assertIsNone(result['passed'])

    def test_hermes_retirement_removes_only_stock_desktop_entry(self):
        for customized in (False, True):
            with self.subTest(customized=customized), tempfile.TemporaryDirectory() as root:
                home = Path(root)
                applications = home / '.local/share/applications'
                applications.mkdir(parents=True)
                entry = applications / 'mseries-hermes-assistant.desktop'
                stock = (f'[Desktop Entry]\nType=Application\nName=Hermes Assistant (Experimental)\n'
                         f'Exec="{home}/.local/bin/mseries-assistant" hermes\n'
                         'Icon=utilities-system-monitor\nTerminal=true\nCategories=Utility;\n')
                original = stock + ('X-User-Note=keep\n' if customized else '')
                entry.write_text(original)
                with patch.object(setup, 'HOME', home), patch.object(setup, 'LIB', home / '.local/libexec/mseries-ai'):
                    setup.app_helpers()
                if customized:
                    self.assertEqual(entry.read_text(), original)
                else:
                    self.assertFalse(entry.exists())

    def test_tool_refresh_preserves_profiles_and_other_mcp_caches(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root); lib = home / '.local/libexec/mseries-ai'; lib.mkdir(parents=True)
            (lib / 'os-mcp.py').write_text('old adapter')
            config = home / '.config/mseries-ai'; config.mkdir(parents=True)
            profiles = config / 'profiles.json'; profiles.write_text('{"user":"choice"}')
            cache = home / '.var/app/io.github.qwersyk.Newelle/cache/extensions_cache/mcp_tool_cache.json'
            cache.parent.mkdir(parents=True)
            cache.write_text(json.dumps({'stdio:/usr/bin/python3:' + str(lib / 'os-mcp.py'): 'old schema', 'other-server': 'retain'}))
            with patch.object(setup, 'HOME', home), patch.object(setup, 'CONFIG', config), patch.object(setup, 'LIB', lib), \
                 patch.object(setup.subprocess, 'run') as flatpak, patch('sys.argv', ['configure', '--refresh-tools']), \
                 patch('sys.stdout', io.StringIO()): setup.main()
            self.assertEqual(profiles.read_text(), '{"user":"choice"}')
            self.assertEqual(json.loads(cache.read_text()), {'other-server': 'retain'})
            self.assertEqual((lib / 'os-mcp.py').read_text(), (HERE / 'os-mcp.py').read_text())
            self.assertEqual(flatpak.call_count, 1)

    def test_task_input_rejects_invalid_dates_ids_and_calendar_injection(self):
        valid = {'title': 'Review battery measurements', 'request_id': 'battery-review-1'}
        for change in [{'title': ''}, {'title': 'Task\nBEGIN:VEVENT'}, {'request_id': '../private'},
                       {'due': '2026-02-30'}, {'due': '20261023'}, {'details': 'a\x00b'}]:
            with self.assertRaises(ValueError):
                os_mcp.call('create_assistant_task', valid | change)
        with self.assertRaises(ValueError):
            os_mcp.call('create_assistant_task', valid | {'title': 'x' * 241})
        self.assertEqual(os_mcp.validate_task_input(valid | {'due': '2026-10-23'})[-1], '2026-10-23')

    def test_task_scope_is_closed_and_write_is_annotated(self):
        with self.assertRaises(ValueError): os_mcp.call('list_tasks', {'scope': 'arbitrary-account'})
        spec = next(t for t in os_mcp.TOOLS if t['name'] == 'create_assistant_task')
        self.assertFalse(spec['annotations']['readOnlyHint'])
        self.assertFalse(spec['inputSchema']['additionalProperties'])

    def test_task_source_marker_stable_private_and_cannot_target_existing_personal_uid(self):
        with tempfile.TemporaryDirectory() as root, patch.object(os_mcp, 'STATE', Path(root)):
            self.assertIsNone(os_mcp.assistant_source_uid())
            uid = os_mcp.assistant_source_uid(create=True)
            self.assertEqual(os_mcp.assistant_source_uid(), uid)
            marker = Path(root) / 'task-source.json'
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
            for value in [[], {'schema': 1, 'source_uid': 'personal-existing-list'}]:
                marker.write_text(json.dumps(value))
                with self.assertRaises(ValueError): os_mcp.assistant_source_uid()
            marker.unlink(); marker.symlink_to(Path(root) / 'absent')
            with self.assertRaises(ValueError): os_mcp.assistant_source_uid(create=True)

    def test_task_writes_refuse_synced_and_non_task_sources(self):
        source = MagicMock()
        source.get_parent.return_value = 'local-stub'
        source.has_extension.return_value = True
        source.get_extension.return_value.get_backend_name.return_value = 'local'
        os_mcp.validate_task_source(source, 'Task List')
        for parent, extension, backend in [('remote-account', True, 'local'),
                                            ('local-stub', True, 'caldav'),
                                            ('local-stub', False, 'local')]:
            source.get_parent.return_value = parent
            source.has_extension.return_value = extension
            source.get_extension.return_value.get_backend_name.return_value = backend
            with self.assertRaises(ValueError): os_mcp.validate_task_source(source, 'Task List')

    def test_unsafe_builtin_alias_is_rejected_before_execution(self):
        source = 'def unique(items):\n dict = eval\n return dict("items")\n'
        with patch.object(bench.subprocess, 'run') as execute:
            self.assertFalse(bench.code_score(source, 'code-dedupe'))
            execute.assert_not_called()

    def test_resume_retains_quality_failures_and_retries_only_incomplete_trials(self):
        meta = {'label': 'fixture', 'model': 'pinned', 'fixtures_sha256': 'same',
                'kernel': 'same', 'governors': ['same'], 'cpu_max_khz': ['same'], 'delay_s': 15}
        previous = meta | {'cases': [{'id': 'extract', 'repeat': 0, 'passed': True},
            {'id': 'arithmetic', 'repeat': 0, 'passed': False},
            {'id': 'code-intervals', 'repeat': 0, 'passed': None, 'error': 'interrupted'}]}
        rows, completed = bench.resume_rows(previous, meta, 3)
        self.assertEqual(len(rows), 2)
        self.assertIn(('arithmetic', 0), completed)
        self.assertNotIn(('code-intervals', 0), completed)
        with self.assertRaises(ValueError): bench.resume_rows(previous, meta | {'model': 'different'}, 3)

    def test_preset_adoption_preserves_policy_and_other_profiles(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root); config = home / '.config/mseries-ai'; config.mkdir(parents=True)
            original = {'policy': {'reserve_gib': 9, 'max_fan_rpm': 3000, 'max_temp_c': 75}, 'profiles': {
                'everyday': {'engine': 'mlx', 'model': 'qwen3.5-9b-mlx-4bit', 'context': 8192, 'port': 8766, 'admission_gib': 10},
                'bespoke': {'model': 'user-choice'}}}
            (config / 'profiles.json').write_text(json.dumps(original))
            with patch.object(setup, 'HOME', home), patch.object(setup, 'CONFIG', config), \
                 patch.object(setup, 'LIB', home / '.local/libexec/mseries-ai'), \
                 patch.object(setup.subprocess, 'run', return_value=MagicMock(stdout='{}')), \
                 patch('sys.argv', ['configure']), patch('sys.stdout', io.StringIO()):
                setup.main()
                retained = json.loads((config / 'profiles.json').read_text())
                self.assertEqual(retained['profiles']['everyday'], original['profiles']['everyday'])
                with patch('sys.argv', ['configure', '--adopt-compact-defaults']): setup.main()
            adopted = json.loads((config / 'profiles.json').read_text())
            self.assertEqual(adopted['policy'], original['policy'])
            self.assertEqual(adopted['profiles']['bespoke'], original['profiles']['bespoke'])
            self.assertEqual(adopted['profiles']['everyday']['model'], 'qwen3.5-4b-mseries-4bit')
            self.assertEqual(adopted['profiles']['coder']['admission_gib'], 6.5)
            launcher = compile((home / '.local/bin/mseries-assistant').read_text(), 'launcher', 'exec')
            live, failed = {'everyday'}, set()
            def control(command, **kwargs):
                action = command[2]
                names = [v.removeprefix('mseries-ai-').removesuffix('.service') for v in command[3:] if v.endswith('.service')]
                if action == 'stop':
                    live.difference_update(names); failed.difference_update(names)
                elif action == 'start':
                    for name in names:
                        (failed if name == 'quality' else live).add(name)
                state = 'active' if names and names[-1] in live else ('failed' if names and names[-1] in failed else 'inactive')
                return MagicMock(returncode=(0 if action != 'is-active' or state == 'active' else 3), stdout=state)
            with patch.object(Path, 'home', return_value=home), patch.object(subprocess, 'run', side_effect=control), \
                 patch('sys.argv', ['assistant', '--quality', 'desktop']):
                with self.assertRaises(SystemExit): exec(launcher, {'__name__': '__main__'})
            self.assertIn('everyday', live)
            self.assertNotIn('quality', live)

    def test_factory_cache_directory_does_not_shadow_system_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root); prefix = home / '.local/share/mlx-omarchy'
            (prefix / 'cache').mkdir(parents=True)
            self.assertEqual(machine.runtime_prefix(home), Path('/usr/lib/omarchy-mlx'))
            (prefix / 'venv/bin').mkdir(parents=True)
            (prefix / 'venv/bin/python').touch()
            self.assertEqual(machine.runtime_prefix(home), Path('/usr/lib/omarchy-mlx'))
            (prefix / 'vulkan').mkdir()
            (prefix / 'vulkan/honeykrisp_icd.aarch64.json').touch()
            self.assertEqual(machine.runtime_prefix(home), prefix)

    def test_scoped_notes_refuse_traversal_links_and_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            os_mcp.ROOT = Path(root) / 'workspace'
            outside = Path(root) / 'private.txt'
            outside.write_text('private')
            os_mcp.ROOT.mkdir()
            (os_mcp.ROOT / 'link').symlink_to(outside)
            for name in ['../private.txt', '/etc/passwd', 'link']:
                with self.assertRaises(ValueError):
                    os_mcp.call('workspace_read_file', {'path': name})
            os_mcp.call('workspace_write_note', {'name': 'Test.md', 'text': 'hello'})
            with self.assertRaises(FileExistsError):
                os_mcp.call('workspace_write_note', {'name': 'Test.md', 'text': 'replaced'})
            self.assertEqual(os_mcp.call('workspace_read_file', {'path': 'Test.md'})['text'], 'hello')

    def test_invalid_tool_arguments_never_execute(self):
        for name, args in [('shell', {'command': 'echo unsafe'}),
                           ('workspace_write_note', {'name': 'Test.md'}),
                           ('system_status', {'command': 'not permitted'})]:
            with self.assertRaises(ValueError):
                os_mcp.call(name, args)

    def test_clock_day_rollover_and_invalid_rpc_do_not_crash(self):
        self.assertEqual(os_mcp.call('add_minutes', {'time': '23:50', 'minutes': '20'}),
                         {'time': '00:10', 'day_offset': 1})
        self.assertIn('error', os_mcp.respond({'id': 1, 'method': 'tools/list', 'params': []}))
        row = os_mcp.respond({'id': 2, 'method': 'tools/call',
                             'params': {'name': 'system_status', 'arguments': []}})
        self.assertTrue(row['result']['isError'])

    def test_branch_discovery_preserves_unselected_personal_heads(self):
        def get(path):
            if '/branches?' in path:
                return [{'name': 'new-experiment', 'commit': {'sha': 'b'}}]
            return {'sha': 'a', 'private': False}
        raw = {}
        rows, errors = branch.collect(get, [{'repo': 'a/b', 'base': 'main', 'discover_branches': True}], raw)
        self.assertFalse(errors)
        self.assertEqual(raw['a/b'][0]['branch'], 'new-experiment')
        self.assertEqual(rows['heads:a/b']['count'], 1)

    def test_mcp_stdio_negotiation_and_tool_errors(self):
        requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                     'params': {'protocolVersion': '2025-03-26'}},
                    {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
                    {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                     'params': {'name': 'shell', 'arguments': {}}}]
        result = subprocess.run([sys.executable, str(HERE / 'os-mcp.py')],
                                input='\n'.join(map(json.dumps, requests)) + '\n',
                                capture_output=True, text=True, timeout=5, check=True)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['result']['protocolVersion'], '2025-03-26')
        self.assertGreaterEqual(len(rows[1]['result']['tools']), 8)
        self.assertTrue(rows[2]['result']['isError'])

    def test_desktop_reserve_and_quiet_limits(self):
        sample = {'available_bytes': 16 * machine.GIB, 'fans_rpm': {'fan': 2500}, 'temperatures_c': {'soc': 55}}
        self.assertFalse(machine.violations(sample, extra_bytes=9 * machine.GIB))
        self.assertTrue(machine.violations(sample, extra_bytes=11 * machine.GIB))
        sample['fans_rpm']['fan'] = 4000
        self.assertTrue(machine.violations(sample))

    def test_cooling_hysteresis_and_missing_sensors(self):
        sample = {'available_bytes': 16 * machine.GIB, 'fans_rpm': {'fan': 2800}, 'temperatures_c': {'soc': 60}}
        self.assertEqual(machine.cooling_action(sample, False), 'pause')
        self.assertIsNone(machine.cooling_action(sample, True))
        self.assertEqual(machine.cooling_action(sample, True, paused_seconds=31), 'burst')
        sample['fans_rpm']['fan'] = 2600
        self.assertEqual(machine.cooling_action(sample, True), 'resume')
        sample['temperatures_c']['soc'] = 71
        self.assertEqual(machine.cooling_action(sample, False), 'pause')
        sample['fans_rpm'] = {}
        self.assertTrue(machine.violations(sample))

    def test_worker_refuses_oversized_model_before_spawn(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / '.config/mseries-ai'
            config.mkdir(parents=True)
            (config / 'profiles.json').write_text(json.dumps({'profiles': {'coder': {'admission_gib': 1000}}}))
            result = subprocess.run([sys.executable, str(HERE / 'model-worker.py'), 'coder'],
                                    env=dict(os.environ, HOME=root), text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 3)
            self.assertIn('ADMISSION REFUSED', result.stdout)

    def test_stopping_a_paused_worker_resumes_cleanup_without_repausing(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root); config = home / '.config/mseries-ai'; config.mkdir(parents=True)
            (config / 'profiles.json').write_text(json.dumps({'profiles': {'coder': {
                'engine': 'llama', 'model': 'fixture', 'context': 8192, 'port': 8768, 'admission_gib': 1}}}))
            base = {'available_bytes': 32 * machine.GIB, 'fans_rpm': {'fan': 2300}, 'temperatures_c': {'soc': 55}}
            handlers, calls = {}, []
            child = MagicMock(pid=123)
            child.poll.return_value = None
            def terminate(): calls.append('terminate')
            def wait(timeout): child.poll.return_value = 0; child.returncode = 0
            child.terminate.side_effect = terminate; child.wait.side_effect = wait
            def register(sig, fn): handlers[sig] = fn
            def tick(_):
                handlers[signal.SIGTERM]()
                handlers[signal.SIGTERM]()  # Quiet stop can race an external systemd stop.
            with patch.object(worker.Path, 'home', return_value=home), \
                 patch('sys.argv', ['worker', 'coder']), \
                 patch.object(worker, 'snapshot', side_effect=[base, base | {'fans_rpm': {'fan': 3000}}]), \
                 patch.object(worker.subprocess, 'Popen', return_value=child), \
                 patch.object(worker.signal, 'signal', side_effect=register), \
                 patch.object(worker.os, 'killpg', side_effect=lambda pid, sig: calls.append(sig)), \
                 patch.object(worker.time, 'sleep', side_effect=tick):
                self.assertEqual(worker.main(), 0)
            self.assertEqual(calls.count(signal.SIGSTOP), 1)
            self.assertLess(calls.index(signal.SIGCONT), calls.index('terminate'))
            child.wait.assert_called_once()
            child.terminate.assert_called_once()

    def test_kernel_events_and_changing_addresses_are_grouped(self):
        event = {'_TRANSPORT': 'kernel', 'MESSAGE': 'asahi gpu fault at 0xabcdef1234 pid 44'}
        first = crash.kernel_event(event)
        second = crash.kernel_event(event | {'MESSAGE': 'asahi gpu fault at 0x1234567890 pid 99'})
        self.assertEqual(first['signature'], second['signature'])
        self.assertIsNone(crash.kernel_event(event | {'MESSAGE': 'wifi firmware loaded successfully'}))
        self.assertEqual(crash.kernel_event(event | {'MESSAGE': 'Out of memory: Killed process 55'})['program'], 'kernel/memory')

    def test_branch_pagination_and_incomplete_discovery(self):
        calls = []
        def get(path):
            calls.append(path)
            return list(range(100)) if path.endswith('&page=1') else [101]
        self.assertEqual(len(branch.pages(get, '/pulls?state=open')), 101)
        self.assertEqual(len(calls), 2)
        with self.assertRaises(ValueError):
            branch.pages(lambda _: [1] * 100, '/pulls', limit=2)

    def test_dashboard_state_roundtrip_and_size_do_not_drop_changes(self):
        current = {f'branch:owner/repo:{i}': {'sha': str(i), 'detail': 'metadata ' * 100} for i in range(200)}
        prior = {k: dict(v, sha='previous') for k, v in current.items()}
        state = dashboard.reconcile({'snapshots': prior}, current, [])
        self.assertEqual(dashboard.decode_state(dashboard.encode_state(state)), state)
        self.assertEqual(dashboard.decode_state(state), state)
        self.assertEqual(len(state['pending']), 200)
        self.assertLess(len(dashboard.render(state)), 65000)

    def test_failed_branch_comparison_is_reported(self):
        def get(path):
            if '/compare/' in path:
                raise OSError('offline')
            return {'sha': 'a', 'private': False}
        observations, errors = branch.collect(get, [{'repo': 'a/b', 'base': 'main', 'branches': ['test']}])
        self.assertFalse(observations)
        self.assertEqual(len(errors), 1)

    def test_code_scoring_catches_input_mutation_and_unsafe_code(self):
        mutating = 'def merge_intervals(items):\n items.sort()\n return items\n'
        self.assertFalse(bench.code_score(mutating, 'code-intervals'))
        self.assertFalse(bench.code_score('import os\ndef unique(items): return items', 'code-dedupe'))
        self.assertFalse(bench.code_score('def unique(items): return open("/etc/passwd").read()', 'code-dedupe'))
        self.assertTrue(bench.code_score('def unique(items):\n return list(dict.fromkeys(items))', 'code-dedupe'))
        self.assertTrue(bench.code_score('def unique(items):\n seen=set()\n out=[]\n for x in items:\n  if x not in seen:\n   seen.add(x)\n   out.append(x)\n return out', 'code-dedupe'))

    def test_cut_stream_is_not_scored_as_a_model_answer(self):
        chunk = b'data: {"choices":[{"delta":{"content":"partial"}}]}\n'
        opener = MagicMock()
        opener.open.return_value = io.BytesIO(chunk)
        with patch.object(bench.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(RuntimeError, 'incomplete response'):
                bench.stream('http://127.0.0.1:8766/v1', {})
        opener.open.return_value = io.BytesIO(chunk + b'data: [DONE]\n')
        with patch.object(bench.urllib.request, 'build_opener', return_value=opener):
            self.assertEqual(bench.stream('http://127.0.0.1:8766/v1', {})['answer'], 'partial')


if __name__ == '__main__':
    unittest.main()
