"""Offline launcher contracts; never contact Teams or use the owner's profile."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import struct
import official_icon
import time
import unittest
from unittest.mock import patch

import teams
import setup


class Links(unittest.TestCase):
    def test_official_deep_links_preserve_meeting_parameters(self):
        url = 'msteams://teams.microsoft.com/l/meetup-join/19%3Ameeting?context=%7B%22Tid%22%3A%22test%22%7D'
        self.assertEqual(teams.teams_url(url), url.replace('msteams:', 'https:', 1))
        for host in teams.HOSTS:
            self.assertEqual(teams.teams_url('https://' + host + '/v2/'), 'https://' + host + '/v2/')
        self.assertEqual(teams.teams_url(None), teams.HOME_URL)

    def test_untrusted_links_cannot_be_browser_flags_or_other_sites(self):
        for url in ('--no-sandbox', 'javascript:alert(1)', 'file:///etc/passwd',
                    'http://teams.microsoft.com/', 'https://teams.microsoft.com.evil.test/',
                    'https://teams.microsoft.com@evil.test/', 'https://evil.test@teams.microsoft.com/',
                    'https://teams.microsoft.com:443/', 'https://teams.microsoft.com\\@evil.test/',
                    'msteams://evil.test/', 'https://teams.microsoft.com/\n--no-sandbox',
                    'msteams:/l/chat/0/0'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                teams.teams_url(url)


class Icon(unittest.TestCase):
    def test_changed_official_asset_is_rejected(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.url = official_icon.URL
        response.read.return_value = b'changed upstream bytes'
        response.__enter__.return_value = response
        with patch('official_icon.urlopen', return_value=response):
            with self.assertRaisesRegex(ValueError, 'upstream icon changed'):
                official_icon.download()

    def test_ico_extracts_original_png_bytes_and_rejects_bad_bounds(self):
        png = official_icon.PNG + b'unchanged-fixture-artwork'
        raw = struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', 0, 0, 0, 0, 1, 32, len(png), 22) + png
        self.assertEqual(official_icon.extract_png(raw), png)
        for invalid in (b'', raw[:10], raw[:-1], b'not an icon'):
            with self.assertRaises(ValueError):
                official_icon.extract_png(invalid)


class Install(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='teams-web-')
        self.addCleanup(self.temp.cleanup)
        self.icon_download = patch('official_icon.download', side_effect=OSError('Offline test'))
        self.asset_download = patch('official_icon.download_asset', side_effect=OSError('Offline test'))
        self.asset_download.start()
        self.addCleanup(self.asset_download.stop)
        self.icon_download.start()
        self.addCleanup(self.icon_download.stop)
        self.home = Path(self.temp.name)
        self.config = self.home / 'config space % " $ ` slash\\'
        self.data = self.home / 'data space % " $ ` slash\\'
        self.env = {**os.environ, 'XDG_CONFIG_HOME': str(self.config),
                    'XDG_DATA_HOME': str(self.data), 'CAPTURE': str(self.home / 'args.json')}
        self.env.pop('DISPLAY', None)
        self.env.pop('WAYLAND_DISPLAY', None)
        self.browser = self.home / 'google-chrome-stable'
        self.browser.write_text('#!/usr/bin/python3\nimport json,os,sys\n'
                                'from pathlib import Path\n'
                                'if "--version" in sys.argv: print("Chrome TEST")\n'
                                'else: Path(os.environ["CAPTURE"]).write_text(json.dumps(sys.argv[1:]))\n')
        self.browser.chmod(0o755)
        self.environ = patch.dict(os.environ, self.env, clear=True)
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def test_outlook_replaces_only_the_mail_pin_and_retains_backup(self):
        spec = importlib.util.spec_from_file_location('outlook', Path(__file__).parent.parent / 'install-outlook-web.py')
        outlook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(outlook)
        class Settings:
            values = ['files.desktop', 'io.elementary.mail.desktop', 'browser.desktop']
            def get_strv(self, key):
                return self.values[:]
            def set_strv(self, key, values):
                self.values = values
                return True
        settings = Settings()
        with patch('shutil.which', return_value=str(self.browser)), patch.object(outlook, 'refresh_desktop'), patch('official_icon.download_asset', return_value=b'<svg xmlns="http://www.w3.org/2000/svg"/>'):
            desktop = outlook.install(settings)
            outlook.install(settings)
        self.assertEqual(settings.values, ['files.desktop', outlook.APP_ID + '.desktop', 'browser.desktop'])
        backup = json.loads((self.config / 'mseries/outlook-web/dock-before.json').read_text())
        self.assertEqual(backup['launchers'][1], 'io.elementary.mail.desktop')
        self.assertIn('--app=https://outlook.office.com/mail/', desktop.read_text())
        self.assertNotIn('MimeType=', desktop.read_text())
        self.assertIn('Icon=' + outlook.APP_ID, desktop.read_text())
        with patch('shutil.which', return_value=str(self.browser)), patch.object(outlook, 'refresh_desktop'):
            outlook.install(settings)  # Offline reinstalls preserve the official SVG.
        self.assertIn('Icon=' + outlook.APP_ID, desktop.read_text())
        subprocess.run(['desktop-file-validate', str(desktop)], check=True)
        from gi.repository import Gio
        app = Gio.DesktopAppInfo.new_from_filename(str(desktop))
        self.assertTrue(app.launch_uris([], None))
        capture = self.home / 'args.json'
        deadline = time.monotonic() + 5
        while not capture.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertIn('--app=https://outlook.office.com/mail/', json.loads(capture.read_text()))
        setup.pin_launcher(settings)
        setup.pin_launcher(settings)
        self.assertEqual(settings.values.count(teams.APP_ID + '.desktop'), 1)
        self.assertEqual(settings.values[0], 'files.desktop')

    def test_official_icon_replaces_fallback_and_survives_offline_upgrade(self):
        raw_png = official_icon.PNG + b'fixture'
        with patch('official_icon.download', return_value=raw_png):
            setup.install(str(self.browser))
        icon = self.data / 'icons/hicolor/256x256/apps' / (teams.APP_ID + '.png')
        generic = self.data / 'icons/hicolor/scalable/apps' / (teams.APP_ID + '.svg')
        self.assertEqual(icon.read_bytes(), raw_png)
        self.assertFalse(generic.exists())
        setup.install(str(self.browser))
        self.assertEqual(icon.read_bytes(), raw_png)
        self.assertFalse(generic.exists())
        setup.uninstall()
        self.assertFalse(icon.exists())

    def test_real_launch_and_upgrade_keep_session_private(self):
        launcher, desktop = setup.install(str(self.browser))
        profile = self.config / 'mseries/teams-web/profile'
        link = 'msteams://teams.microsoft.com/l/meetup-join/test?x=1&y=2'
        subprocess.run([str(launcher), link], env=self.env, check=True)
        arguments = json.loads((self.home / 'args.json').read_text())
        self.assertIn('--app=https://teams.microsoft.com/l/meetup-join/test?x=1&y=2', arguments)
        self.assertIn('--user-data-dir=' + str(profile), arguments)
        self.assertIn('--class=' + teams.APP_ID, arguments)
        self.assertFalse({'--no-sandbox', '--disable-web-security', '--disable-gpu-sandbox'} & set(arguments))
        self.assertEqual(profile.stat().st_mode & 0o777, 0o700)
        self.assertEqual((profile.parent / 'config.json').stat().st_mode & 0o777, 0o600)
        session = profile / 'sentinel-session'
        session.write_text('keep')
        setup.install(str(self.browser))
        self.assertEqual(session.read_text(), 'keep')
        subprocess.run(['desktop-file-validate', str(desktop)], check=True)
        setup.uninstall()
        self.assertFalse(launcher.exists())
        self.assertFalse(desktop.exists())
        self.assertEqual(session.read_text(), 'keep')

    def test_desktop_exec_round_trip_with_special_path_characters(self):
        from gi.repository import Gio
        launcher, desktop = setup.install(str(self.browser))
        app = Gio.DesktopAppInfo.new_from_filename(str(desktop))
        self.assertIsNotNone(app)
        self.assertTrue(app.launch_uris(['msteams://teams.microsoft.com/l/chat/test'], None))
        deadline = time.monotonic() + 5
        capture = self.home / 'args.json'
        while not capture.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(capture.exists(), 'Desktop Exec did not launch the expected executable')
        self.assertIn('--app=https://teams.microsoft.com/l/chat/test', json.loads(capture.read_text()))

    def test_existing_brave_session_uses_profile_without_copying_data(self):
        brave = self.home / 'brave-browser-stable'
        brave.write_text(self.browser.read_text())
        brave.chmod(0o755)
        state = self.config / 'BraveSoftware/Brave-Browser/Local State'
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({'profile': {'last_used': 'Profile 2'}}))
        # Test-only PATH selects a recording browser, never the owner's browser.
        with patch.dict(os.environ, {'PATH': str(self.home) + os.pathsep + os.environ['PATH']}):
            launcher, desktop = setup.install(use_brave_session=True)
        subprocess.run([str(launcher)], env=self.env, check=True)
        arguments = json.loads((self.home / 'args.json').read_text())
        self.assertIn('--profile-directory=Profile 2', arguments)
        self.assertFalse(any(a.startswith('--user-data-dir=') for a in arguments))
        self.assertFalse(any(a.startswith('--class=') for a in arguments))
        self.assertFalse((self.config / 'mseries/teams-web/profile').exists())
        self.assertIn('StartupWMClass=brave-teams.microsoft.com__v2_-Profile 2', desktop.read_text())
        self.assertEqual(json.loads(state.read_text())['profile']['last_used'], 'Profile 2')
        state.write_text(json.dumps({'profile': {'last_used': 'Default'}}))
        with patch.dict(os.environ, {'PATH': str(self.home) + os.pathsep + os.environ['PATH']}):
            setup.install()  # Upgrade preserves the originally selected profile.
        config = json.loads((self.config / 'mseries/teams-web/config.json').read_text())
        self.assertEqual(config['mode'], 'brave-session')
        self.assertEqual(config['profile_directory'], 'Profile 2')

    def test_brave_profile_cannot_escape_profile_directory(self):
        for name in ('..', '../Default', '/tmp/session', 'x\\y', 'name\n', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                teams.validate_profile(name)

    def test_diagnostics_do_not_open_browser_or_create_profile(self):
        launcher, _ = setup.install(str(self.browser))
        result = subprocess.run([str(launcher), '--check'], env=self.env,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['version'], 'Chrome TEST')
        self.assertFalse((self.home / 'args.json').exists())
        self.assertFalse((self.config / 'mseries/teams-web/profile').exists())

    def test_missing_browser_fails_before_installing_shortcut(self):
        with self.assertRaises(ValueError):
            setup.install(str(self.home / 'missing-browser'))
        self.assertFalse((self.data / 'applications').exists())

    def test_corrupt_config_has_actionable_error_without_secrets(self):
        launcher, _ = setup.install(str(self.browser))
        root = self.config / 'mseries/teams-web'
        (root / 'config.json').write_text('SECRET_INVALID_JSON')
        result = subprocess.run([str(launcher), '--check'], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Re-run the installer', result.stderr)
        self.assertNotIn('SECRET', result.stderr)

    def test_invalid_link_cannot_launch_browser(self):
        launcher, _ = setup.install(str(self.browser))
        result = subprocess.run([str(launcher), 'https://evil.test'], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.home / 'args.json').exists())


if __name__ == '__main__':
    unittest.main()
