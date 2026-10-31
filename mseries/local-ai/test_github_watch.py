#!/usr/bin/env python3
"""State migration and bounded dashboard rendering for github-watch.py."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('github_watch', HERE / 'github-watch.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
people_spec = importlib.util.spec_from_file_location('people_watch', HERE / 'people-watch.py')
people = importlib.util.module_from_spec(people_spec)
people_spec.loader.exec_module(people)


def sha1(text):
    return hashlib.sha1(text.encode()).hexdigest()


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

    def test_full_length_digests_shorten_without_reporting_a_change(self):
        key = 'branch:example/project:main'
        full, base = 'a1b2c3d4e5f6' + '0' * 28, 'f' * 40
        previous = {'snapshots': {key: {'sha': full, 'base_sha': base}},
                    'pending': {'heads:example/project': {'from': {'sha256': 'e' * 64}, 'to': {'sha256': 'd' * 64}}}}

        state = watch.reconcile(previous, {key: {'sha': full, 'base_sha': base}}, [])

        self.assertNotIn(key, state['pending'])
        self.assertEqual(state['snapshots'][key], {'sha': 'a1b2c3d4e5f6', 'base_sha': 'ffffffffffff'})
        self.assertEqual(state['pending']['heads:example/project'], {'sha256': 'eeeeeeeeeeee'})

    def test_every_source_pending_fits_with_520_full_length_heads(self):
        # 2026-10-31: 510 tracked sources with 40-character SHAs overflowed the issue body.
        observations, snapshots = {}, {}
        for index in range(520):
            key = f'branch:example/repository-{index % 24:02d}:feature/long-branch-name-{index:04d}'
            snapshots[key] = {'branch': key.rsplit(':', 1)[1], 'sha': sha1(f'old-{index}'),
                              'base_sha': sha1(f'base-{index}'), 'ahead': index, 'behind': index % 9,
                              'status': 'diverged'}
            observations[key] = dict(snapshots[key], sha=sha1(f'new-{index}'))

        state = watch.reconcile({'snapshots': snapshots}, observations, [])

        self.assertEqual(len(state['pending']), 520)
        self.assertLess(len(watch.render(state).encode()), 65000)


class PeopleWatchRetry(unittest.TestCase):
    class Response:
        def __init__(self, data): self.data = data
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, *args): return self.data

    def run_get(self, outcomes):
        import io, urllib.error
        calls, delays = [], []
        queue = list(outcomes)

        def fake_urlopen(request, timeout=0):
            calls.append(request.full_url)
            outcome = queue.pop(0)
            if isinstance(outcome, int):
                raise urllib.error.HTTPError(request.full_url, outcome, 'x', {}, io.BytesIO(b''))
            if isinstance(outcome, Exception):
                raise outcome
            return self.Response(outcome)

        original = people.urllib.request.urlopen
        people.urllib.request.urlopen = fake_urlopen
        try:
            try:
                return people.get('/repos/x/y', sleep=delays.append), calls, delays, None
            except Exception as error:
                return None, calls, delays, error
        finally:
            people.urllib.request.urlopen = original

    def test_transient_500_is_retried_then_succeeds(self):
        value, calls, delays, error = self.run_get([500, 502, b'{"ok": true}'])
        self.assertIsNone(error)
        self.assertEqual(value, {'ok': True})
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, [1, 3])

    def test_persistent_500_still_raises_after_bounded_attempts(self):
        _, calls, delays, error = self.run_get([500, 500, 500, 500])
        self.assertIsNotNone(error)
        self.assertEqual(len(calls), len(people.RETRY_DELAYS) + 1)
        self.assertEqual(delays, list(people.RETRY_DELAYS))

    def test_client_errors_are_not_retried(self):
        for code in (401, 403, 422):
            _, calls, delays, error = self.run_get([code])
            self.assertIsNotNone(error, code)
            self.assertEqual((len(calls), delays), (1, []), code)

    def test_404_returns_none_without_retry(self):
        value, calls, delays, error = self.run_get([404])
        self.assertIsNone(error)
        self.assertIsNone(value)
        self.assertEqual(len(calls), 1)

    def test_network_timeouts_are_retried(self):
        value, calls, _, error = self.run_get([TimeoutError(), b'{"a": 1}'])
        self.assertIsNone(error)
        self.assertEqual(value, {'a': 1})
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
