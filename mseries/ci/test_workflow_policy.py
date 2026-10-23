import copy
from pathlib import Path
import tempfile
import unittest

import workflow_policy as policy


class WorkflowCancellationTest(unittest.TestCase):
    def setUp(self):
        self.workflows = policy.repository_workflows()
        self.pr_workflows = [(p, w) for p, w in self.workflows if 'pull_request' in w.get('on', {})]

    def test_every_real_pr_workflow_is_covered(self):
        self.assertGreaterEqual(len(self.pr_workflows), 9)
        self.assertEqual([], policy.check(self.workflows))

    def test_removing_cancellation_from_any_workflow_fails(self):
        for path, workflow in self.pr_workflows:
            with self.subTest(path=path):
                changed = copy.deepcopy(workflow)
                changed.pop('concurrency')
                self.assertTrue(policy.check([(path, changed)]))

    def test_ref_only_groups_and_non_cancelling_pr_runs_fail(self):
        for field, value in [('group', '${{ github.ref }}'), ('cancel-in-progress', 'false'),
                             ('cancel-in-progress', 'true'), ('group', '${{ github.event.pull_request.number }}')]:
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(self.pr_workflows[0][1])
                changed['concurrency'][field] = value
                self.assertTrue(policy.check([('bad.yml', changed)]))

    def test_new_pr_workflow_cannot_escape_policy(self):
        new = {'name': 'New expensive checks', 'on': {'pull_request': {}}, 'jobs': {}}
        self.assertTrue(policy.check(self.workflows + [('new.yml', new)]))

    def test_duplicate_names_cannot_cancel_another_workflow(self):
        for name in [self.pr_workflows[0][1]['name'], self.pr_workflows[0][1]['name'].swapcase()]:
            with self.subTest(name=name):
                duplicate = copy.deepcopy(self.pr_workflows[0][1])
                duplicate['name'] = name
                self.assertTrue(policy.check(self.workflows + [('duplicate.yml', duplicate)]))

    def test_same_pr_shares_group_but_other_prs_workflows_and_refs_do_not(self):
        # Substitute the documented GitHub contexts in the actual checked expression.
        def group(workflow, pr, ref):
            return policy.GROUP.replace('${{ github.workflow }}', workflow).replace(
                '${{ github.event.pull_request.number || github.ref }}', str(pr) if pr else ref)
        first = group('Validation', 526, 'refs/pull/526/merge')
        self.assertEqual(first, group('Validation', 526, 'refs/pull/526/merge'))
        self.assertNotEqual(first, group('Validation', 527, 'refs/pull/527/merge'))
        self.assertNotEqual(first, group('Messages', 526, 'refs/pull/526/merge'))
        self.assertNotEqual(first, group('Validation', None, 'refs/heads/dev'))
        self.assertNotEqual(group('Packages', None, 'refs/heads/dev'),
                            group('Packages', None, 'refs/heads/main'))
        self.assertEqual("${{ github.event_name == 'pull_request' }}", policy.CANCEL)

    def test_release_workflows_and_publisher_lock_are_preserved(self):
        workflows = dict(self.workflows)
        publisher = workflows['.github/workflows/mseries-debs.yml']['jobs']['publish']['concurrency']
        self.assertEqual({'group': 'mseries-apt-publish', 'cancel-in-progress': 'false'}, publisher)
        self.assertEqual('false', workflows['.github/workflows/daily-9.0.yml']['concurrency']['cancel-in-progress'])
        self.assertEqual('false', workflows['.github/workflows/upstream-watch.yml']['concurrency']['cancel-in-progress'])

    def test_yaml_loader_preserves_on_and_boolean_scalars(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.yml'
            path.write_text('on:\n  pull_request:\nconcurrency:\n  cancel-in-progress: false\n')
            data = policy.load(path)
            self.assertIn('pull_request', data['on'])
            self.assertEqual('false', data['concurrency']['cancel-in-progress'])


if __name__ == '__main__':
    unittest.main()
