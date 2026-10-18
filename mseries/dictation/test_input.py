import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('dictation_input', Path(__file__).with_name('dictation-input.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FocusTests(unittest.TestCase):
    def ready(self):
        state = module.FocusSession()
        state.focus(object(), 'gtk3-im:synthetic')
        state.content(0, 0)
        return state

    def test_unicode_and_literal_text(self):
        s = self.ready()
        s.accept(s.begin(), 'Café — 日本語\n$(literal) & +')

    def test_sensitive_or_unknown_context(self):
        for purpose, hints in [(None, 0), (8, 0), (9, 0), (0, 2048)]:
            s = self.ready(); s.content(purpose, hints)
            with self.assertRaises(ValueError): s.begin()

    def test_xim_without_sensitive_field_metadata_is_refused(self):
        s = self.ready(); s.focus(object(), 'xim'); s.content(0, 0)
        with self.assertRaises(ValueError): s.begin()

    def test_accessible_metadata_gate(self):
        self.assertTrue(module.safe_accessible(79, True, True, True))
        for args in [(40, True, True, True), (79, False, True, True),
                     (79, True, False, True), (79, True, True, False), (0, True, True, True), (67, True, True, True)]:
            self.assertFalse(module.safe_accessible(*args))

    def test_focus_change_and_cancel(self):
        for action in [lambda s: s.focus(object(), 'gtk3-im:other'), lambda s: s.invalidate(), lambda s: s.content(8, 0)]:
            s = self.ready(); token = s.begin(); action(s)
            with self.assertRaises(ValueError): s.accept(token, 'late text')

    def test_expiry_and_wrong_session(self):
        s = self.ready(); token = s.begin()
        with self.assertRaises(ValueError): s.accept('another', 'text')
        s.clock = lambda: s.deadline + 1
        with self.assertRaises(ValueError): s.accept(token, 'text')

    def test_bounds_and_control_characters(self):
        for text in ['', 'x' * 4001, '\x00', '\x1b', '\x7f']:
            s = self.ready()
            with self.assertRaises(ValueError): s.accept(s.begin(), text)


if __name__ == '__main__': unittest.main()
