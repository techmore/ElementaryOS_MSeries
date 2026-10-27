#!/usr/bin/env python3
"""State migration and bounded dashboard rendering for github-watch.py."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('github_watch', HERE / 'github-watch.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


class GitHubWatchState(unittest.TestCase):
    def test_legacy_pending_change_migrates_without_losing_latest_revision(self):
        key = 'branch:example/project:main'
        previous = {
            'snapshots': {
                key: {
                    'repo': 'example/project',
                    'branch': 'main',
                    'sha': 'newest-sha',
                    'base_sha': 'base-sha',
                    'ahead': 4,
                    'behind': 2,
                    'status': 'diverged',
                    'url': 'https://github.com/example/project/compare',
                    'qualification': 'long repeated metadata',
                },
            },
            'pending': {
                key: {
                    'from': {'sha': 'first-sha', 'base_sha': 'base-sha'},
                    'to': {'sha': 'newest-sha', 'base_sha': 'base-sha'},
                },
            },
            'errors': [],
        }

        state = watch.reconcile(previous, {}, [], acknowledged=False)

        self.assertEqual(state['snapshots'][key], {
            'sha': 'newest-sha',
            'base_sha': 'base-sha',
            'branch': 'main',
            'ahead': 4,
            'behind': 2,
            'status': 'diverged',
        })
        self.assertEqual(state['pending'][key], {
            'sha': 'first-sha',
            'base_sha': 'base-sha',
        })
        body = watch.render(state)
        self.assertIn('Before: `{"base_sha": "base-sha", "sha": "first-sha"}`', body)
        self.assertIn('Now: `{"ahead": 4, "base_sha": "base-sha", "behind": 2, "branch": "main", "sha": "newest-sha", "status": "diverged"}`', body)
        self.assertNotIn('long repeated metadata', body)

    def test_new_change_keeps_original_before_and_stores_only_latest_snapshot(self):
        key = 'branch:example/project:main'
        previous = {
            'snapshots': {key: {'repo': 'example/project', 'branch': 'main', 'sha': 'middle-sha',
                                'base_sha': 'base-sha', 'url': 'https://example.invalid'}},
            'pending': {key: {'from': {'sha': 'first-sha', 'base_sha': 'base-sha'},
                              'to': {'sha': 'middle-sha', 'base_sha': 'base-sha'}}},
        }
        current = {key: {'repo': 'example/project', 'branch': 'main', 'sha': 'latest-sha',
                         'base_sha': 'new-base-sha', 'ahead': 9, 'behind': 1,
                         'status': 'diverged', 'url': 'https://example.invalid/compare'}}

        state = watch.reconcile(previous, current, [], acknowledged=False)

        self.assertEqual(state['pending'][key], {'sha': 'first-sha', 'base_sha': 'base-sha'})
        self.assertEqual(state['snapshots'][key], {
            'sha': 'latest-sha',
            'base_sha': 'new-base-sha',
            'branch': 'main',
            'ahead': 9,
            'behind': 1,
            'status': 'diverged',
        })
        body = watch.render(state)
        self.assertIn('Before: `{"base_sha": "base-sha", "sha": "first-sha"}`', body)
        self.assertIn('Now: `{"ahead": 9, "base_sha": "new-base-sha", "behind": 1, "branch": "main", "sha": "latest-sha", "status": "diverged"}`', body)

    def test_acknowledgment_clears_pending_changes(self):
        state = watch.reconcile(
            {'snapshots': {'repo': {'sha': 'current'}}, 'pending': {'repo': {'sha': 'older'}}},
            {'repo': {'sha': 'current'}},
            [],
            acknowledged=True,
        )

        self.assertEqual(state['pending'], {})
        self.assertEqual(state['snapshots'], {'repo': {'sha': 'current'}})

    def test_compact_state_round_trips(self):
        state = {
            'snapshots': {'repo': {'sha': 'current', 'base_sha': 'base'}},
            'pending': {'repo': {'sha': 'before', 'base_sha': 'base'}},
            'errors': [],
        }

        self.assertEqual(watch.decode_state(watch.encode_state(state)), state)

    def test_large_legacy_dashboard_fits_the_issue_body_limit_after_migration(self):
        snapshots = {}
        pending = {}
        for index in range(378):
            repo = f'example/repository-{index:03d}'
            branch = f'feature/change-{index:03d}'
            key = f'branch:{repo}:{branch}'
            current = {
                'repo': repo,
                'branch': branch,
                'sha': f'{index:040x}',
                'base_sha': f'{index + 1000:040x}',
                'ahead': index,
                'behind': index % 7,
                'status': 'ahead' if index % 2 else 'diverged',
                'url': f'https://github.com/{repo}/compare/{index:040x}...{index + 1000:040x}',
                'qualification': 'discovered; applicability, patch equivalence and M1 Pro tests required',
            }
            snapshots[key] = current
            if index < 173:
                pending[key] = {
                    'from': {'sha': f'{index + 2000:040x}', 'base_sha': f'{index + 1000:040x}', 'branch': branch},
                    'to': watch.change_marker(current),
                }

        state = watch.reconcile({'snapshots': snapshots, 'pending': pending, 'errors': []}, {}, [])
        body = watch.render(state)

        self.assertEqual(len(state['snapshots']), 378)
        self.assertEqual(len(state['pending']), 173)
        self.assertLess(len(body.encode()), 65000)


if __name__ == '__main__':
    unittest.main()
