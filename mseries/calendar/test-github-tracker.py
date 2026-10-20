#!/usr/bin/env python3
"""Outcome/CI behavior tests without GitHub access or user state."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('tracker', Path(__file__).with_name('github-tracker.py'))
tracker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracker)


def commit(*states, truncated=False):
    return {'oid': 'abc', 'statusCheckRollup': {'contexts': {
        'nodes': [{'__typename': 'CheckRun', 'status': 'COMPLETED', 'conclusion': state} for state in states],
        'pageInfo': {'hasNextPage': truncated}}}}


def payload():
    return {'data': {'repository': {
        'issue': {'title': 'Outcome', 'state': 'OPEN', 'stateReason': None, 'url': 'https://github.com/a/b/issues/1',
                  'milestone': None, 'subIssues': {'pageInfo': {'hasNextPage': False}, 'nodes': [
                      {'title': 'Recovery', 'state': 'OPEN', 'stateReason': None, 'number': 2, 'url': 'https://github.com/a/b/issues/2'},
                      {'title': 'Acceptance', 'state': 'CLOSED', 'stateReason': 'NOT_PLANNED', 'number': 3, 'url': 'https://github.com/a/b/issues/3'}]}},
        'defaultBranchRef': {'name': 'main', 'target': commit('SUCCESS')},
        'pullRequests': {'pageInfo': {'hasNextPage': False}, 'nodes': []}}}}


class TrackerTests(unittest.TestCase):
    def test_ci_never_promotes_missing_skipped_cancelled_or_partial_checks(self):
        self.assertEqual(tracker.ci(commit('SUCCESS')), 'passing')
        for state in ('SKIPPED', 'NEUTRAL', 'CANCELLED', None):
            self.assertEqual(tracker.ci(commit('SUCCESS', state)), 'incomplete')
        self.assertEqual(tracker.ci(None), 'unknown')
        self.assertEqual(tracker.ci(commit()), 'unknown')
        self.assertEqual(tracker.ci(commit('SUCCESS', truncated=True)), 'unknown')
        self.assertEqual(tracker.ci(commit('FAILURE')), 'failing')
        pending = commit('SUCCESS')
        pending['statusCheckRollup']['contexts']['nodes'][0]['status'] = 'IN_PROGRESS'
        self.assertEqual(tracker.ci(pending), 'pending')

    def test_closed_not_planned_is_not_completed_and_ci_does_not_finish_outcome(self):
        data = payload()
        row = tracker.collect({'repo': 'a/b', 'issue': 1, 'title': 'Outcome'}, lambda _: data)
        self.assertEqual(row['completed'], 0)
        self.assertFalse(row['done'])
        data['data']['repository']['issue']['state'] = 'CLOSED'
        data['data']['repository']['issue']['stateReason'] = 'COMPLETED'
        self.assertFalse(tracker.collect({'repo': 'a/b', 'issue': 1}, lambda _: data)['done'])

    def test_only_explicitly_linked_prs_and_exact_head_ci(self):
        data = payload()
        linked = {'title': 'Fix recovery', 'number': 4, 'url': 'https://github.com/a/b/pull/4',
                  'headRefOid': 'new', 'headRefName': 'fix/recovery',
                  'closingIssuesReferences': {'nodes': [{'number': 2, 'repository': {'nameWithOwner': 'a/b'}}], 'pageInfo': {'hasNextPage': False}},
                  'commits': {'nodes': [{'commit': commit('SUCCESS')}]}}
        unrelated = copy.deepcopy(linked)
        unrelated['closingIssuesReferences']['nodes'] = [{'number': 2, 'repository': {'nameWithOwner': 'other/repo'}}]
        data['data']['repository']['pullRequests']['nodes'] = [linked, unrelated]
        row = tracker.collect({'repo': 'a/b', 'issue': 1}, lambda _: data)
        self.assertEqual(len(row['prs']), 1)
        self.assertEqual(row['prs'][0]['ci'], 'unknown')
        self.assertEqual(row['other_prs'], 1)

    def test_failure_keeps_dated_evidence_and_priority(self):
        targets = [{'repo': 'a/b', 'issue': 1}, {'repo': 'c/d', 'issue': 2}]
        previous = {'outcomes': [{**targets[0], 'observed_at': 'old', 'ci': 'passing'}]}
        def fail(_):
            raise OSError('private credential error must never be displayed')
        result = tracker.refresh(targets, previous, fail)
        self.assertEqual([r['repo'] for r in result['outcomes']], ['a/b', 'c/d'])
        self.assertEqual(result['outcomes'][0]['observed_at'], 'old')
        self.assertEqual(result['outcomes'][0]['ci'], 'passing')
        self.assertNotIn('private credential', result['outcomes'][0]['error'])
        self.assertNotIn('ci', result['outcomes'][1])
        self.assertEqual(len(tracker.refresh(targets, [], fail)['outcomes']), 2)

    def test_invalid_config_does_not_silently_fall_back(self):
        original = tracker.CONFIG
        with tempfile.TemporaryDirectory() as folder:
            tracker.CONFIG = Path(folder) / 'config.json'
            tracker.CONFIG.write_text('{"version":1,"targets":[]}')
            with self.assertRaises(ValueError):
                tracker.targets()
        tracker.CONFIG = original


if __name__ == '__main__':
    unittest.main()
