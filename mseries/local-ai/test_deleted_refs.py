import importlib.util
import io
from pathlib import Path
import unittest
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('deleted_ref_watch', Path(__file__).with_name('branch-watch.py'))
branch_watch = importlib.util.module_from_spec(spec); spec.loader.exec_module(branch_watch)


class DeletedRefContracts(unittest.TestCase):
    def test_deleted_named_ref_keeps_personal_branch_and_pr_discovery(self):
        def get(path):
            if path.endswith('/commits/gone'):
                raise HTTPError(path, 422, 'Unprocessable', {}, io.BytesIO(b'{"message":"No commit found for SHA: gone"}'))
            if '/branches?' in path: return [{'name': 'experiment', 'commit': {'sha': 'tip'}}]
            if '/pulls?' in path: return [{'number': 1, 'head': {'repo': {'full_name': 'fork/repo'}, 'ref': 'new', 'sha': 'tip'}, 'html_url': 'https://example.invalid/pr'}]
            if '/compare/' in path: return {'ahead_by': 1, 'behind_by': 0, 'status': 'ahead', 'html_url': 'https://example.invalid/compare'}
            return {'private': False, 'sha': 'base'}
        raw = {}
        rows, errors = branch_watch.collect(get, [{'repo': 'a/b', 'base': 'main', 'branches': ['gone'], 'discover_branches': True, 'open_prs': True}], raw)
        self.assertFalse(errors)
        self.assertEqual(rows['branch:a/b:gone']['status'], 'named ref absent')
        self.assertEqual(rows['branch:fork/repo:new']['ahead'], 1)
        self.assertEqual(raw['a/b'][0]['branch'], 'experiment')

    def test_other_http_422_is_still_an_error(self):
        def get(path):
            raise HTTPError(path, 422, 'Unprocessable', {}, io.BytesIO(b'{"message":"Validation Failed"}'))
        with self.assertRaises(HTTPError): branch_watch.tracked_tip(get, 'a/b', 'gone')
