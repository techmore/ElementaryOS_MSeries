"""Deep installed-app focus hierarchies retain active-window/deadline guards."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('dictation_input_depth', Path(__file__).with_name('dictation-input.py'))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
API = SimpleNamespace(Role=SimpleNamespace(APPLICATION=75, FRAME=23, DIALOG=16, WINDOW=69),
                      StateType=SimpleNamespace(ACTIVE=1))


class Node:
    def __init__(self, role=39, parent=None, active=False):
        self.role, self.parent, self.active = role, parent, active
        self.visits = 0

    def clear_cache(self):
        self.visits += 1

    def get_parent(self):
        return self.parent

    def get_role(self):
        return self.role

    def get_state_set(self):
        return SimpleNamespace(contains=lambda state: self.active and state == API.StateType.ACTIVE)


def hierarchy(wrappers=24, active=True):
    window = Node(API.Role.FRAME, Node(API.Role.APPLICATION), active)
    leaf = window
    for _ in range(wrappers):
        leaf = Node(parent=leaf)
    return Node(61, leaf), window


class DepthTests(unittest.TestCase):
    def test_actual_newelle_depth_accepts_only_active_frame(self):
        leaf, frame = hierarchy()
        self.assertTrue(bridge.active_window_ancestor(leaf, API, bridge.MetadataBudget()))
        self.assertEqual(frame.visits, 1)
        frame.active = False
        self.assertFalse(bridge.active_window_ancestor(leaf, API, bridge.MetadataBudget()))

    def test_deep_walk_still_observes_shared_rpc_deadline(self):
        leaf, _ = hierarchy()
        now = [0]
        def clock():
            now[0] += .01
            return now[0]
        with self.assertRaisesRegex(ValueError, 'deadline'):
            bridge.active_window_ancestor(leaf, API, bridge.MetadataBudget(seconds=.1, clock=clock))

    def test_cyclic_or_pathological_hierarchy_is_bounded(self):
        leaf = Node()
        leaf.parent = leaf
        self.assertFalse(bridge.active_window_ancestor(leaf, API, bridge.MetadataBudget()))
        self.assertEqual(leaf.visits, 64)

    def test_qt_active_filler_directly_under_application_is_supported(self):
        filler = Node(parent=Node(API.Role.APPLICATION), active=True)
        self.assertTrue(bridge.active_window_ancestor(Node(61, filler), API, bridge.MetadataBudget()))


if __name__ == '__main__':
    unittest.main()
