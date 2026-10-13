import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

spec = importlib.util.spec_from_file_location('verify', Path(__file__).with_name('verify.py'))
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        patches = [mock.patch.object(verify, 'STATE', root), mock.patch.object(verify, 'DB', root / 'verify.db'),
                   mock.patch.object(verify, 'STATUS_JSON', root / 'verify-status.json')]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        self.seed = root / 'checks.json'
        self.db = verify.connect()
        self.notes = []
        patch = mock.patch.object(verify, 'notify', lambda title, body: self.notes.append((title, body)))
        patch.start()
        self.addCleanup(patch.stop)

    def load(self, *checks):
        self.seed.write_text(json.dumps({'checks': list(checks)}))
        verify.load_seed(self.db, self.seed)

    def run_once(self):
        verify.cmd_run(self.db, SimpleNamespace(notify=True, quiet=True))

    def state(self, check_id):
        return self.db.execute('SELECT state FROM checks WHERE id=?', (check_id,)).fetchone()['state']

    def test_waiting_until_precondition_then_passes_and_stays_passed(self):
        flag = Path(self.tmp.name) / 'ready'
        self.load({'id': 'a', 'title': 'A', 'precondition': f'test -e {flag}', 'command': 'true'})
        self.run_once()
        self.assertEqual(self.state('a'), 'waiting')
        self.assertEqual(self.notes, [])
        flag.write_text('')
        self.run_once()
        self.assertEqual(self.state('a'), 'passed')
        self.assertEqual(len(self.notes), 1)
        flag.unlink()  # a passed check is not re-evaluated
        self.run_once()
        self.assertEqual(self.state('a'), 'passed')
        self.assertEqual(len(self.notes), 1)

    def test_failure_notifies_once_then_recovers(self):
        flag = Path(self.tmp.name) / 'good'
        self.load({'id': 'f', 'title': 'F', 'command': f'echo detail $RANDOM; test -e {flag}'})
        self.run_once()
        self.run_once()
        self.assertEqual(self.state('f'), 'failed')
        self.assertEqual(len(self.notes), 1, 'changing detail text must not re-notify')
        flag.write_text('')
        self.run_once()
        self.assertEqual(self.state('f'), 'passed')
        self.assertEqual(len(self.notes), 2)

    def test_manual_asks_once_and_answers_stick(self):
        self.load({'id': 'm', 'kind': 'manual', 'title': 'M', 'hint': 'look', 'precondition': 'true'},
                  {'id': 'n', 'kind': 'manual', 'title': 'N', 'hint': 'look', 'precondition': 'true'})
        self.run_once()
        self.run_once()
        self.assertEqual(self.state('m'), 'ask')
        self.assertEqual(len(self.notes), 2, 'one question per manual check')
        verify.cmd_confirm(self.db, SimpleNamespace(id='m', answer='yes', note=[]))
        verify.cmd_confirm(self.db, SimpleNamespace(id='n', answer='no', note=['too dark']))
        self.run_once()
        self.assertEqual(self.state('m'), 'passed')
        self.assertEqual(self.state('n'), 'failed', 'a "no" must not flip back to asking')
        verify.cmd_recheck(self.db, SimpleNamespace(id='n'))
        self.run_once()
        self.assertEqual(self.state('n'), 'ask')

    def test_after_chain_unlocks_in_one_pass(self):
        self.load({'id': 'first', 'title': '1', 'command': 'true'},
                  {'id': 'second', 'kind': 'manual', 'title': '2', 'after': 'first', 'hint': 'x'})
        self.run_once()
        self.assertEqual(self.state('first'), 'passed')
        self.assertEqual(self.state('second'), 'ask')

    def test_after_blocks_until_dependency_passes(self):
        self.load({'id': 'first', 'title': '1', 'command': 'false'},
                  {'id': 'second', 'title': '2', 'after': 'first', 'command': 'true'})
        self.run_once()
        self.assertEqual(self.state('second'), 'waiting')

    def test_history_and_status_json_written(self):
        self.load({'id': 'h', 'title': 'H', 'command': 'echo hi'})
        self.run_once()
        runs = self.db.execute('SELECT outcome, detail FROM runs WHERE check_id=?', ('h',)).fetchall()
        self.assertEqual([(r['outcome'], r['detail']) for r in runs], [('passed', 'hi')])
        payload = json.loads(verify.STATUS_JSON.read_text())
        self.assertEqual(payload['counts'], {'passed': 1})

    def test_reload_keeps_results(self):
        self.load({'id': 'k', 'title': 'old', 'command': 'true'})
        self.run_once()
        self.load({'id': 'k', 'title': 'new', 'command': 'true'})
        row = self.db.execute('SELECT title, state FROM checks WHERE id=?', ('k',)).fetchone()
        self.assertEqual((row['title'], row['state']), ('new', 'passed'))

    def test_timeout_is_a_failure_not_a_hang(self):
        self.load({'id': 't', 'title': 'T', 'command': 'sleep 5'})
        with mock.patch.object(verify, 'TIMEOUT', 1):
            self.run_once()
        self.assertEqual(self.state('t'), 'failed')

    def test_shipped_seed_is_valid(self):
        seed = json.loads(Path(__file__).with_name('verify-checks.json').read_text())
        ids = [c['id'] for c in seed['checks']]
        self.assertEqual(len(ids), len(set(ids)))
        for check in seed['checks']:
            self.assertIn(check.get('kind', 'auto'), ('auto', 'manual'))
            if check.get('kind', 'auto') == 'auto':
                self.assertTrue(check.get('command'), check['id'])
            if check.get('after'):
                self.assertIn(check['after'], ids)

    def test_tags_are_stored_listed_and_filterable(self):
        self.load({'id': 'a', 'title': 'A', 'kind': 'manual', 'tags': ['dock', 'power']},
                  {'id': 'b', 'title': 'B', 'kind': 'manual'})
        payload = verify.write_status(self.db)
        by_id = {item['id']: item for item in payload['items']}
        self.assertEqual(by_id['a']['tags'], ['dock', 'power'])
        self.assertEqual(by_id['b']['tags'], [])
        verify.cmd_status(self.db, SimpleNamespace(json=True, tag='dock'))

    def test_database_without_tags_column_is_upgraded(self):
        self.db.execute('ALTER TABLE checks DROP COLUMN tags')
        self.db.commit()
        db = verify.connect()
        self.assertIn('tags', {row['name'] for row in db.execute('PRAGMA table_info(checks)')})


if __name__ == '__main__':
    unittest.main()
