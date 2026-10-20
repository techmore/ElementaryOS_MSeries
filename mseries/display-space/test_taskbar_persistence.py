"""Isolated tests for update paths that must retain the Windows taskbar."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class TaskbarPersistence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.schemas = self.home / '.local/lib/mseries/dock/share/glib-2.0/schemas'
        self.schemas.mkdir(parents=True)
        # Exercise the private-schema lookup even when the distro schema lacks taskbar-mode.
        schema = '''<schemalist><schema id="io.elementary.dock" path="/io/elementary/dock/">
<key name="taskbar-mode" type="b"><default>false</default></key>
<key name="icon-size" type="i"><default>48</default></key>
<key name="autohide-mode" type="s"><default>'never'</default></key>
<key name="launchers" type="as"><default>['teams.desktop','outlook.desktop']</default></key>
</schema></schemalist>'''
        (self.schemas / 'dock.gschema.xml').write_text(schema)
        subprocess.run(['glib-compile-schemas', str(self.schemas)], check=True)
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / 'config'),
                        XDG_STATE_HOME=str(self.home / 'state'), GSETTINGS_BACKEND='keyfile',
                        GSETTINGS_SCHEMA_DIR=str(self.schemas))

    def setting(self, op, key, value=None):
        command = ['gsettings', op, 'io.elementary.dock', key]
        if value is not None:
            command.append(value)
        return subprocess.check_output(command, env=self.env, text=True).strip()

    def profile(self, *args):
        return subprocess.check_output(['/usr/bin/python3', str(ROOT / 'mseries/display-space/dock_profile.py'), *args],
                                       env=self.env, text=True)

    def test_taskbar_update_keeps_visibility_size_and_pins(self):
        self.setting('set', 'taskbar-mode', 'true')
        self.setting('set', 'icon-size', '52')
        before = {key: self.setting('get', key) for key in ('taskbar-mode', 'icon-size', 'autohide-mode', 'launchers')}
        self.assertIn('preserved', self.profile())
        self.assertEqual(before, {key: self.setting('get', key) for key in before})

    def test_floating_profile_still_applies_and_reverts(self):
        self.profile()
        self.assertEqual(self.setting('get', 'icon-size'), '40')
        self.assertEqual(self.setting('get', 'autohide-mode'), "'overlapping-window'")
        self.profile('--revert')
        self.assertEqual(self.setting('get', 'icon-size'), '48')
        self.assertEqual(self.setting('get', 'autohide-mode'), "'never'")

    def test_factory_payload_contains_complete_customizations(self):
        image = self.home / 'image'
        image.mkdir()
        subprocess.run(['bash', str(ROOT / 'mseries/enhance.sh'), '--root', str(image), '--only', 'payload'],
                       check=True, stdout=subprocess.DEVNULL)
        payload = image / 'usr/share/elementary-mac/mseries'
        for name in ('dock-taskbar/prepare-source.sh', 'dock-taskbar/TaskbarCodexBar.vala',
                     'dock-taskbar/test-hover.sh', 'dock-taskbar/test-hover.vala',
                     'dock-tests/test-markers.sh', 'codexbar-wingpanel/Indicator.vala',
                     'codexbar-wingpanel/meson.build', 'teams-web/official_icon.py',
                     'install-teams.sh', 'install-outlook-web.py', 'install-codexbar-wingpanel.sh',
                     'patches/dock-taskbar-codexbar.patch', 'patches/dock-running-apps.patch'):
            self.assertEqual((payload / name).read_bytes(), (ROOT / 'mseries' / name).read_bytes(), name)


if __name__ == '__main__':
    unittest.main()
