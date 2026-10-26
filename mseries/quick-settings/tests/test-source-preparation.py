#!/usr/bin/env python3
"""Keep desktop, package and factory builds on the shared core preparation path."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
HELPER = 'mseries/quick-settings/prepare-source.sh'


class SourcePreparationTests(unittest.TestCase):
    def test_desktop_calls_shared_helper_once(self):
        text = (ROOT / 'mseries/install-quick-settings-brightness.sh').read_text()
        self.assertEqual(text.count(f'bash "$repo/{HELPER}" "$repo" "$work/source"'), 1)
        self.assertLess(text.index(HELPER), text.index('# Screen-share section'))
        self.assertNotIn('quick-settings-brightness.patch', text)
        self.assertNotIn('quick-settings-audio-output.patch', text)
        self.assertNotIn('quick-settings-bluetooth.patch', text)
        self.assertNotIn('quick-settings-layout.patch', text)

    def test_factory_and_package_keep_shared_helper(self):
        for name in ('mkosi.images/apple-silicon/build-quick-settings', 'mseries/debs/build.sh'):
            with self.subTest(name=name):
                self.assertIn(HELPER, (ROOT / name).read_text())


    def test_desktop_preserves_its_extra_sources(self):
        text = (ROOT / 'mseries/install-quick-settings-brightness.sh').read_text()
        for token in ('ShareState ShareClient SharePanel', 'AirDropPanel.vala',
                      "'Widgets' / 'SharePanel.vala'", "dependency('libsoup-3.0')"):
            with self.subTest(token=token):
                self.assertIn(token, text)


if __name__ == '__main__':
    unittest.main()
