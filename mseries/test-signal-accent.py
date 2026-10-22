#!/usr/bin/env python3
"""Palette completeness and fixed-width Signal asset recoloring regressions."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('signal_accent', Path(__file__).with_name('signal-accent.py'))
accent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accent)


class PaletteTests(unittest.TestCase):
    def test_default_blue_uses_the_pantheon_r_theme_ramp(self):
        mapping = accent.build_map(accent.ACCENTS["blue"])
        self.assertEqual(accent.ACCENTS["blue"], "#9dbfe3")
        self.assertEqual(mapping["#2c6bed"], "#9dbfe3")
        self.assertEqual(mapping["#3b45fd"], "#9dbfe3")
        self.assertEqual(mapping["#1851b4"], "#7ba2cc")
        self.assertEqual(mapping["#6191f3"], "#a9c8e8")

    def test_every_system_accent_covers_the_complete_signal_family(self):
        for name, value in accent.ACCENTS.items():
            with self.subTest(accent=name):
                mapping = accent.build_map(value)
                self.assertEqual(set(mapping), set(accent.FAMILY))
                self.assertEqual(mapping['#3b45fd'], value)
                self.assertTrue(all(len(c) == 7 for c in mapping.values()))

    def test_logo_and_ui_recolor_without_changing_asset_length(self):
        original = b'logo:#3b45fd;LOGO:#3B45FD;button:#2c6bed;pressed:#1851b4'
        for value in accent.ACCENTS.values():
            changed, count = accent.recolour(original, accent.build_map(value), '1,2,3')
            self.assertEqual(len(changed), len(original))
            self.assertEqual(count, 4)
            self.assertIn(b'logo:' + value.encode(), changed)

    def test_custom_accent_keeps_complete_fallback(self):
        mapping = accent.build_map('#123456')
        self.assertEqual(set(mapping), set(accent.FAMILY))
        self.assertEqual(mapping['#3b45fd'], '#123456')


if __name__ == '__main__':
    unittest.main()
