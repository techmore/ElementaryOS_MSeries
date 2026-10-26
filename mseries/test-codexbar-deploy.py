#!/usr/bin/env python3
"""Run the real deploy script against fake tools; process-control commands never reach the live session."""
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name('deploy-codexbar.sh')
LIB = pathlib.Path(__file__).with_name('lib-codexbar.sh')


def shared_list(name):
    """An array from lib-codexbar.sh, read by bash itself rather than re-parsed."""
    output = subprocess.run(['bash', '-c', f'source "$1"; printf "%s\\n" "${{{name}[@]}}"', 'bash', str(LIB)],
                            check=True, capture_output=True, text=True).stdout
    return output.split()


class DeployTest(unittest.TestCase):
    def test_reload_is_explicit_and_never_quits_the_daemon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            repo = root / 'repo' / 'mseries'
            repo.mkdir(parents=True)
            (repo / SCRIPT.name).write_bytes(SCRIPT.read_bytes())
            (repo / LIB.name).write_bytes(LIB.read_bytes())
            (repo / "lib-t3-panel.sh").write_bytes(SCRIPT.with_name("lib-t3-panel.sh").read_bytes())
            (repo / "install-t3-wingpanel.sh").write_text('echo stage-unified >> "$TEST_LOG"\n')
            for name in [*shared_list('CODEXBAR_HELPERS'), 'codexbar-opencode-wrapper.py']:
                (repo / name).touch()
            icons = repo / 'codexbar-wingpanel/icons'
            icons.mkdir(parents=True)
            marks = shared_list('CODEXBAR_MARKS')
            for name in marks:
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
 cmp) [[ ${TEST_ICONS_MATCH:-1} == 1 ]] ;;
 install) /usr/bin/install "$@" ;;
 pgrep) exit 0 ;;
 *) exit 0 ;;
esac
''')
            fake.chmod(0o755)
            for name in ('meson', 'ninja', 'pkg-config', 'sudo', 'gtk-update-icon-cache', 'pgrep', 'pkill', 'setsid', 'sleep', 'install', 'cmp'):
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
                self.assertFalse(any('gtk-update-icon-cache' in line for line in calls), 'unchanged icons never invalidate the live theme')
                self.assertFalse(any('--quit' in line for line in calls))
                self.assertFalse(any(line.startswith('setsid ') for line in calls), 'already-running processes are preserved')
            log.write_text('')
            result = subprocess.run(['bash', str(repo / SCRIPT.name)], env=env | {'TEST_ICONS_MATCH':'0'}, capture_output=True, text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            calls=log.read_text().splitlines()
            self.assertEqual(sum('sudo gtk-update-icon-cache' in line for line in calls),1)
            self.assertEqual(sum(line.startswith('sudo install -m 0644') for line in calls), len(marks))
            installed = profile / '.local/lib/codexbar-cli'
            self.assertEqual(sorted(path.name for path in installed.iterdir()), sorted(shared_list('CODEXBAR_HELPERS')))
            self.assertEqual(oct((installed / 'codexbar_tokens.py').stat().st_mode & 0o777), '0o644')
            self.assertEqual(oct((installed / 'codexbar-sessions.py').stat().st_mode & 0o777), '0o755')
            self.assertFalse(any(line.startswith('pkill ') for line in calls))
            (root / 'indicators/libmseries-t3.so').touch()
            log.write_text('')
            result = subprocess.run(['bash', str(repo / SCRIPT.name)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('/../mseries-retired-indicators/libcodexbar.so', log.read_text())
            self.assertIn('stage-unified', log.read_text())
            self.assertNotIn('pkill ', log.read_text())
            log.write_text('')
            result = subprocess.run(['bash', str(repo / SCRIPT.name), '--bad-option'], env=env, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(log.read_text(), '')

class PayloadTest(unittest.TestCase):
    """One helper list for install, deploy and the image; it must cover every local import."""

    def test_helpers_cover_local_imports(self):
        helpers = shared_list('CODEXBAR_HELPERS')
        here = SCRIPT.parent
        modules = {name[:-3] for name in helpers if '-' not in name}
        for name in [*helpers, 'codexbar-opencode-wrapper.py']:
            source = (here / name).read_text(encoding='utf-8')
            for module in re.findall(r'^\s*(?:import|from)\s+(codexbar\w*)', source, re.MULTILINE):
                self.assertIn(module, modules, f'{name} imports {module}, which lib-codexbar.sh does not install')

    def test_installers_and_image_use_the_shared_payload(self):
        here = SCRIPT.parent
        for script in ('install-codexbar.sh', 'install-codexbar-wingpanel.sh', 'deploy-codexbar.sh'):
            self.assertIn('codexbar_install_helpers "$repo"', (here / script).read_text(), script)
        payload = (here / 'enhance.sh').read_text()
        for name in [*shared_list('CODEXBAR_HELPERS'), 'lib-codexbar.sh', 'codexbar-opencode-wrapper.py']:
            self.assertRegex(payload, r'[ \t]' + re.escape(name) + r'[ \t\\]', f'enhance.sh image payload lacks {name}')

    def test_every_mark_is_built_and_present(self):
        meson = (SCRIPT.parent / 'codexbar-wingpanel/meson.build').read_text()
        for mark in shared_list('CODEXBAR_MARKS'):
            self.assertTrue((SCRIPT.parent / f'codexbar-wingpanel/icons/{mark}.svg').is_file(), mark)
            self.assertIn(f"'{mark}'" if mark != 'openai' else "icons/openai.svg", meson, mark)


if __name__ == '__main__':
    unittest.main()
