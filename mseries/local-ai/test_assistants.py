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


class AssistantContracts(unittest.TestCase):
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
            def tick(_): handlers[signal.SIGTERM]()
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
