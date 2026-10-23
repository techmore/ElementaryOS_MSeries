import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('mark', Path(__file__).with_name('mark-newelle-chat.py'))
mark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mark)

ENTRY = '[Desktop Entry]\nName=Newelle\nExec=flatpak run io.github.qwersyk.Newelle\n\n[Desktop Action a]\nName=A\n'


class MarkNewelle(unittest.TestCase):
    def test_marker_goes_into_the_main_group_once(self):
        text = mark.marked(ENTRY)
        self.assertEqual(text.count(mark.MARK), 1)
        self.assertLess(text.index(mark.MARK), text.index('[Desktop Action a]'))
        self.assertEqual(mark.marked(text), text)

    def test_entry_without_other_groups(self):
        text = mark.marked('[Desktop Entry]\nName=N\n')
        self.assertTrue(text.endswith(mark.MARK + '\n'))

    def test_writes_user_copy_and_removes_only_its_own(self):
        with tempfile.TemporaryDirectory() as home:
            exports = Path(home, 'flatpak/exports/share/applications')
            exports.mkdir(parents=True)
            (exports / f'{mark.APP_ID}.desktop').write_text(ENTRY)
            os.environ['XDG_DATA_HOME'] = home
            try:
                mark.sys.argv = ['mark']
                self.assertEqual(mark.main(), 0)
                target = Path(home, 'applications', f'{mark.APP_ID}.desktop')
                self.assertIn(mark.MARK, target.read_text())
                self.assertIn(mark.GENERATED, target.read_text())
                mark.sys.argv = ['mark', '--remove']
                mark.main()
                self.assertFalse(target.exists())
                target.parent.mkdir(exist_ok=True)
                target.write_text('[Desktop Entry]\nName=Hand made\n')
                mark.main()
                self.assertTrue(target.exists())
            finally:
                os.environ.pop('XDG_DATA_HOME')

    def test_not_installed_is_reported(self):
        with tempfile.TemporaryDirectory() as home:
            os.environ['XDG_DATA_HOME'] = home
            try:
                mark.sys.argv = ['mark']
                self.assertEqual(mark.main(), 1)
            finally:
                os.environ.pop('XDG_DATA_HOME')

    def test_repo_desktop_entries_of_the_other_chat_apps_carry_the_marker(self):
        root = Path(__file__).resolve().parents[2]
        for name in ('rust/mseries-messages/data/io.elementary.mseries.MessagesRust.desktop',
                     'rust/claude-pantheon-rs/data/io.github.techmore.ClaudePantheonRs.desktop'):
            lines = (root / name).read_text().split('\n[', 1)[0].splitlines()
            self.assertIn(mark.MARK, [line.strip() for line in lines], name)


if __name__ == '__main__':
    unittest.main()
