import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).parents[1] / 'input_bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class Fake:
    def __init__(self):
        self.events = []
    def motion(self, *args):
        self.events.append(args)
    def click(self, *args):
        self.events.append(args)
    def keys(self, *args):
        self.events.append(args)


class InputTests(unittest.TestCase):
    def test_unicode_and_chords(self):
        backend = Fake()
        bridge.dispatch({'kind': 'text', 'text': 'é🙂\n'}, backend)
        self.assertEqual(backend.events[0][0], [233, 0x0101f642, 0xff0d])
        bridge.dispatch({'kind': 'key', 'key': 'a', 'modifiers': ['ctrl']}, backend)
        self.assertEqual(backend.events[1], ([97], [0xffe3]))

    def test_reject_invalid_input_without_side_effects(self):
        cases = [None, {}, {'kind': 'move', 'dx': float('nan'), 'dy': 0},
                 {'kind': 'move', 'dx': True, 'dy': 1}, {'kind': 'move', 'dx': 1001, 'dy': 0},
                 {'kind': 'click', 'button': 'bad'}, {'kind': 'text', 'text': 'a' * 513},
                 {'kind': 'text', 'text': 'hello\x00'}, {'kind': 'key', 'key': 'F999'},
                 {'kind': 'key', 'key': 'a', 'modifiers': ['ctrl', 'ctrl']}]
        for event in cases:
            with self.subTest(event=event):
                backend = Fake()
                with self.assertRaises(ValueError):
                    bridge.dispatch(event, backend)
                self.assertEqual(backend.events, [])

    def test_keys_release_modifiers_after_failure(self):
        backend = object.__new__(bridge.Mutter)
        events = []
        def remote(method, signature, args):
            events.append(args)
            if args == (97, True):
                raise RuntimeError('failed key')
        backend.remote = remote
        backend.check_unlocked = lambda: None
        with self.assertRaises(RuntimeError):
            backend.keys([97], [0xffe3])
        self.assertEqual(events[-2:], [(97, False), (0xffe3, False)])


if __name__ == '__main__':
    unittest.main()
