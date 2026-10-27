import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INSTALLER = ROOT.parent / 'install-dictation-input.py'


def directives(text, key):
    return [v for line in text.splitlines() if line.startswith(key + '=') for v in line.split('=', 1)[1].split()]


class UnitOrderingTests(unittest.TestCase):
    """systemd orders a target after every unit it wants unless that unit already
    says After=<target>. A wanted unit that is ordered after another unit which is
    After=<target> but lacks it itself makes a cycle, and systemd drops a start job
    at login (seen as `Job mseries-stream-dictate.service/start deleted`)."""

    def merged_stream_dictate(self):
        text = (ROOT / 'mseries-stream-dictate.service').read_text()
        match = re.search(rb"payload\.install\(DROPIN, b'(.*?)', 0o644\)".decode().encode(), INSTALLER.read_bytes())
        self.assertIsNotNone(match, 'installer drop-in not found')
        return text + '\n' + match.group(1).decode().encode().decode('unicode_escape')

    def test_wanted_units_are_after_the_target(self):
        for unit in sorted(ROOT.glob('*.service')):
            text = unit.read_text()
            if unit.name == 'mseries-stream-dictate.service':
                text = self.merged_stream_dictate()
            if 'graphical-session.target' in directives(text, 'WantedBy'):
                self.assertIn('graphical-session.target', directives(text, 'After'), unit.name)

    def test_stream_dictate_still_waits_for_the_input_method(self):
        merged = self.merged_stream_dictate()
        self.assertIn('mseries-dictation-input.service', directives(merged, 'After'))
        self.assertIn('mseries-dictation-input.service', directives(merged, 'Wants'))


if __name__ == '__main__':
    unittest.main()
