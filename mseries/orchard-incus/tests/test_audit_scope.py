"""The live audit may never turn a changed selection into an owner-guest write."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_scope import AuditScope


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'output'
        self.out.mkdir()
        self.names = {'audit-a', 'audit-b'}
        self.scope = AuditScope(self.names, self.out)

    def test_original_guests_are_rejected_for_every_mutating_family(self):
        operations = [('stop', 'owner'), ('delete', '--force', 'owner'), ('pause', 'owner'),
                      ('copy', 'owner', 'audit-b'), ('rename', 'audit-a', 'owner'),
                      ('config', 'set', 'owner', 'limits.cpu=2'),
                      ('config', 'device', 'remove', 'owner', 'disk'),
                      ('snapshot', 'restore', 'owner', 's1'), ('exec', 'owner', '--', 'true'),
                      ('export', 'owner', str(self.out / 'backup')),
                      ('file', 'push', str(self.out / 'file'), 'owner/root/file')]
        for args in operations:
            with self.subTest(args=args), self.assertRaises(RuntimeError):
                self.scope.check(args)

    def test_owned_workflow_operations_are_allowed(self):
        for args in [('stop', 'audit-a', '--force'), ('delete', '--force', 'audit-a'),
                     ('copy', 'audit-a', 'audit-b'), ('rename', 'audit-a', 'audit-b'),
                     ('config', 'set', 'audit-a', 'limits.cpu=2'),
                     ('config', 'device', 'add', 'audit-a', 'share', 'disk', 'source=' + str(self.out)),
                     ('config', 'device', 'remove', 'audit-a', 'share'),
                     ('snapshot', 'create', 'audit-a', 's1'), ('exec', 'audit-a', '--', 'true'),
                     ('export', 'audit-a', str(self.out / 'backup')),
                     ('file', 'push', '-r', str(self.out / 'file'), 'audit-a/root/file'),
                     ('file', 'pull', 'audit-a/root/file', str(self.out / 'file'))]:
            with self.subTest(args=args):
                self.scope.check(args)

    def test_outside_host_paths_are_rejected_in_both_directions(self):
        outside = str(Path(self.tmp.name) / 'outside')
        for args in [('export', 'audit-a', outside), ('file', 'push', outside, 'audit-a/root/file'),
                     ('file', 'pull', 'audit-a/root/file', outside),
                     ('config', 'device', 'add', 'audit-a', 'share', 'disk', 'source=' + outside)]:
            with self.subTest(args=args), self.assertRaises(RuntimeError):
                self.scope.check(args)

    def test_symlink_destinations_cannot_escape_the_output_directory(self):
        (self.out / 'link').symlink_to(Path(self.tmp.name))
        with self.assertRaises(RuntimeError):
            self.scope.host_path(self.out / 'link' / 'escaped')

    def test_unknown_and_global_mutations_are_rejected(self):
        for args in [('image', 'delete', 'cached'), ('launch', 'cached'), ('query', '-X', 'DELETE', '/1.0/instances/owner')]:
            with self.subTest(args=args), self.assertRaises(RuntimeError):
                self.scope.check(args)

    def test_read_only_inventory_and_metadata_are_allowed(self):
        for args in [('list',), ('monitor', '--type=lifecycle'), ('query', '/1.0/instances/owner'),
                     ('config', 'show', 'owner'), ('image', 'list'), ('storage', 'info', 'default')]:
            self.scope.check(args)

    def test_new_cycle_names_share_the_live_owned_set(self):
        self.names.add('audit-next')
        self.scope.guest('audit-next')
