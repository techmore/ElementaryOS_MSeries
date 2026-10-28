"""Every user unit wanted by graphical-session.target must also be After= it.

systemd orders a target after each unit it wants unless that unit already says
After=<target>. Such a unit is then ordered *before* the session target, and as
soon as it (or a drop-in) is also ordered after anything that waits for the
target, the transaction has a cycle and systemd silently deletes a start job at
login. That is how F5 dictation stopped starting (PR #614). This check covers
the tracked unit files and the units that installer scripts write from shell
heredocs, so the next unit cannot reintroduce the trap.
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = 'graphical-session.target'
HEREDOC = re.compile(r'<<-?\s*[\'"]?(\w+)[\'"]?')


def tracked(*patterns):
    out = subprocess.run(['git', 'ls-files', '-z', '--', *patterns], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.split('\0') if p]


def directives(text, key):
    return [v for line in text.splitlines() if line.strip().startswith(key + '=')
            for v in line.split('=', 1)[1].split()]


def heredoc_units(path):
    """Yield (line number, body) for each heredoc in a shell script that writes a unit."""
    lines = path.read_text(errors='replace').splitlines()
    i = 0
    while i < len(lines):
        match = HEREDOC.search(lines[i])
        if not match:
            i += 1
            continue
        end, start, body = match.group(1), i + 1, []
        i += 1
        while i < len(lines) and lines[i].strip() != end:
            body.append(lines[i])
            i += 1
        text = '\n'.join(body)
        if '[Install]' in text or '[Unit]' in text:
            yield start, text


def units():
    for path in tracked('*.service'):
        if not path.is_file():  # dangling *.wants symlinks into the image
            continue
        yield str(path.relative_to(ROOT)), path.read_text(errors='replace')
    for path in tracked('*.sh'):
        if path.is_file():
            for line, text in heredoc_units(path):
                yield f'{path.relative_to(ROOT)}:{line}', text


class UserUnitOrderingTests(unittest.TestCase):
    def test_wanted_by_session_target_is_after_it(self):
        seen = 0
        for name, text in units():
            if TARGET not in directives(text, 'WantedBy'):
                continue
            seen += 1
            with self.subTest(unit=name):
                self.assertIn(TARGET, directives(text, 'After'),
                              f'{name} is WantedBy={TARGET} without After={TARGET}')
        self.assertGreater(seen, 3, 'scanner found too few session units; is the walk broken?')

    def test_heredoc_scanner_sees_installer_units(self):
        found = [name for name, text in units()
                 if name.startswith('mseries/install-desktop-notifications.sh:')]
        self.assertTrue(found, 'desktop notifications installer unit not found')


if __name__ == '__main__':
    unittest.main()
