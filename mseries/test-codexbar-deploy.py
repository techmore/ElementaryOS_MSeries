#!/usr/bin/env python3
"""Run the real deploy script against fake tools; process-control commands never reach the live session."""
import os
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name('deploy-codexbar.sh')

class DeployTest(unittest.TestCase):
    def test_reload_is_explicit_and_never_quits_the_daemon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            repo = root / 'repo' / 'mseries'
            repo.mkdir(parents=True)
            (repo / SCRIPT.name).write_bytes(SCRIPT.read_bytes())
            for name in ('codexbar_claude_history.py', 'codexbar_cache.py', 'codexbar_tokens.py', 'codexbar-opencode-local.py',
                         'codexbar-sessions.py', 'codexbar-accounts.py', 'codexbar-claude.py',
                         'codexbar-opencode-login.py', 'codexbar-opencode-wrapper.py'):
                (repo / name).touch()
            icons = repo / 'codexbar-wingpanel/icons'
            icons.mkdir(parents=True)
            for name in ('openai', 'claude', 'opencode'):
                (icons / (name + '.svg')).touch()
            profile = root / 'profile'
            (profile / '.local/bin').mkdir(parents=True)
            tools = root / 'tools'
            tools.mkdir()
            # Stub sudo too: icon installation must stay in the temporary test tree.
            fake = tools / 'tool'
            fake.write_text('''#!/bin/bash
name=${0##*/}
printf '%s %s\\n' "$name" "$*" >> "$TEST_LOG"
case $name in
 meson) if [[ $1 == setup ]]; then mkdir -p "$2"; touch "$2/libcodexbar.so" "$2/codexbar-settings"; fi ;;
 pkg-config) echo "$TEST_ROOT/indicators"; mkdir -p "$TEST_ROOT/indicators" ;;
 sudo) exit 0 ;;
 install) /usr/bin/install "$@" ;;
 pgrep) exit 0 ;;
 *) exit 0 ;;
esac
''')
            fake.chmod(0o755)
            for name in ('meson', 'ninja', 'pkg-config', 'sudo', 'gtk-update-icon-cache', 'pgrep', 'pkill', 'setsid', 'sleep', 'install'):
                (tools / name).symlink_to(fake)
            log = root / 'calls'
            env = os.environ | {'HOME': str(profile), 'PATH': str(tools) + ':/usr/bin:/bin',
                                'TEST_LOG': str(log), 'TEST_ROOT': str(root)}
            for args in ([], ['--no-restart'], ['--restart']):
                log.write_text('')
                result = subprocess.run(['bash', str(repo / SCRIPT.name), *args], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = log.read_text().splitlines()
                self.assertEqual(sum(line.startswith('pkill ') for line in calls), int(args == ['--restart']))
                self.assertFalse(any('--quit' in line for line in calls))
                self.assertFalse(any(line.startswith('setsid ') for line in calls), 'already-running processes are preserved')
            log.write_text('')
            result = subprocess.run(['bash', str(repo / SCRIPT.name), '--bad-option'], env=env, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(log.read_text(), '')

if __name__ == '__main__':
    unittest.main()
