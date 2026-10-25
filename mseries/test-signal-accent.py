#!/usr/bin/env python3
"""Palette, contrast, and fixed-width Signal archive recoloring regressions."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('signal_accent', Path(__file__).with_name('signal-accent.py'))
accent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accent)


def contrast_ratio(foreground, background):
    def luminance(value):
        channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def asar_fixture(path):
    assets = {
        'stylesheets/manifest.css': (
            b'.link{color:#2c6bed}.button{background:#2c6bed;color:#fff}'
            b'.dark-theme .link{color:#2c6bed}'
            b'.logo{background-color:#3b45fd}'
            b'.module-message__container--outgoing-ultramarine{'
            b'background-image:linear-gradient(180deg,#0552f0,#2c6bed)}'
        ),
        'stylesheets/tailwind.css': (
            b'@layer theme{:root{--axo-color-brand-primary:#3b45fd;'
            b'--axo-color-label-accent:light-dark(#030ffc,#99a1ff);'
            b'--axo-color-fill-accent:light-dark(#4655ff,#5563ff);'
            b'--axo-color-fill-accent-pressed:light-dark(#3b4af4,#616eff);'
            b'--axo-color-border-selected:light-dark(#4655ff,#c9ceff);'
            b'--axo-color-surface-message-outgoing:light-dark(#2267f5,#2267f5);'
            b'--axo-color-label-accent:light-dark(#000cf3,#b6bcff);'
            b'--axo-color-fill-accent:light-dark(#1f31ff,#2536f9);'
            b'--axo-color-fill-accent-pressed:light-dark(#0519ff,#2e3ffa);'
            b'--axo-color-border-selected:light-dark(#3243ff,#c9ceff);'
            b'--axo-color-surface-message-outgoing:light-dark(#0842b9,#0842b9);'
            b'--axo-color-fill-accent-tint:light-dark('
            b'oklab(45.3524% -.0303155 -.305089/.06),'
            b'oklab(74.1051% .0208054 -.133796/.12))}}'
        ),
        'bundles/main.js': b'function jv(e){return e?.signalColors?`#3b45fd`:`#fafafa`}const chat=`#2c6bed`;',
        'bundles/preload/main.js': b'<svg fill="#3B45FD"/><svg fill="#3B45FD"/>const chat="#2c6bed";',
        'images/avatars/avatar_cat.svg': b'<svg fill="#3b45fd"/>',
    }
    files = {}
    cursor = 0
    packed = bytearray()
    for full_path, data in assets.items():
        node = files
        parts = full_path.split('/')
        for part in parts[:-1]:
            node = node.setdefault(part, {'files': {}})['files']
        node[parts[-1]] = {
            'offset': str(cursor), 'size': len(data),
            'integrity': {
                'algorithm': 'SHA256', 'hash': '0' * 64,
                'blockSize': 4 * 1024 * 1024, 'blocks': ['0' * 64],
            },
        }
        cursor += len(data)
        packed.extend(data)
    header = {'files': files}
    raw = json.dumps(header, separators=(',', ':')).encode()
    header_size = 8 + len(raw)
    path.write_bytes(struct.pack('<4I', 4, header_size, 0, len(raw)) + raw + packed)
    return assets


class PaletteTests(unittest.TestCase):
    def test_larger_reading_type_and_distinct_surface_preserve_archive_width(self):
        source = (b'.message{font-size:14px}.caption{font-size:12px}'
                  b'--axo-text-body-large:.875rem;--axo-text-body-medium:.8125rem;'
                  b'--axo-text-body-small:.75rem;--axo-leading-body-large:1.25rem;'
                  b'--axo-leading-body-medium:1.125rem;'
                  b'--axo-color-surface-primary:light-dark(#fafafa,#191919)')
        patched, count = accent.patch_stylesheet(source, accent.palette_for('#3689e6'))
        self.assertEqual(len(source), len(patched))
        self.assertIn(b'font-size:16px', patched)
        self.assertIn(b'font-size:14px', patched)
        self.assertIn(b'--axo-text-body-large:.975rem', patched)
        self.assertIn(b'--axo-leading-body-large:1.40rem', patched)
        self.assertIn(b'light-dark(#eef3fa,#202936)', patched)
        self.assertEqual(count, 8)

    def test_cli_upgrades_legacy_stamp_skips_unchanged_and_restores(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            resources = Path(tmp) / 'resources'
            resources.mkdir()
            archive = resources / 'app.asar'
            asar_fixture(archive)
            original = archive.read_bytes()
            stamp = resources / '.mseries-accent'
            stamp.write_text('#3689e6\n')
            command = [sys.executable, str(Path(accent.__file__)), '--appdir', tmp]
            run = lambda *args: subprocess.run(command + list(args), check=True,
                capture_output=True, text=True)
            run('--sync', '--accent', '#3689e6')
            self.assertNotEqual(archive.read_bytes(), original)
            self.assertIn('helper', json.loads(stamp.read_text()))
            before = archive.stat().st_mtime_ns
            self.assertIn('already uses', run('--sync', '--accent', '#3689e6').stderr)
            self.assertEqual(archive.stat().st_mtime_ns, before)
            run('--restore')
            self.assertEqual(archive.read_bytes(), original)
            self.assertFalse(stamp.exists())
            self.assertFalse((resources / 'app.asar.orig').exists())

    def test_check_does_not_create_backup_or_stamp(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            resources = Path(tmp) / 'resources'
            resources.mkdir()
            archive = resources / 'app.asar'
            asar_fixture(archive)
            original = archive.read_bytes()
            subprocess.run([sys.executable, str(Path(accent.__file__)), '--appdir', tmp,
                '--check', '--accent', '#3689e6'], check=True, capture_output=True)
            self.assertEqual(archive.read_bytes(), original)
            self.assertEqual(sorted(p.name for p in resources.iterdir()), ['app.asar'])

    def test_sync_cache_tracks_archives_and_helper_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / 'original.asar'
            target = Path(tmp) / 'app.asar'
            original.write_bytes(b'original')
            target.write_bytes(b'patched')
            first = accent.sync_stamp('#3689e6', target, original)
            self.assertEqual(first, accent.sync_stamp('#3689e6', target, original))
            self.assertNotEqual(first, accent.sync_stamp('#68b723', target, original))
            self.assertNotEqual(first, '#3689e6')  # upgrade old accent-only stamps
            target.write_bytes(b'updated application')
            self.assertNotEqual(first, accent.sync_stamp('#3689e6', target, original))
            second = accent.sync_stamp('#3689e6', target, original)
            original.write_bytes(b'new upstream original')
            self.assertNotEqual(second, accent.sync_stamp('#3689e6', target, original))
            helper = Path(tmp) / 'helper.py'
            helper.write_bytes(b'new implementation')
            from unittest.mock import patch
            with patch.object(accent, '__file__', str(helper)):
                changed = accent.sync_stamp('#3689e6', target, original)
            self.assertNotEqual(changed, accent.sync_stamp('#3689e6', target, original))

    def test_default_blue_uses_the_published_elementary_palette(self):
        palette = accent.palette_for(accent.ACCENTS['blue'])
        mapping = accent.build_map(accent.ACCENTS['blue'])
        self.assertEqual(accent.ACCENTS['blue'], '#3689e6')
        self.assertEqual(palette, {
            'light': '#8cd5ff', 'dark': '#64baff', 'accent': '#3689e6',
            'pressed': '#0d52bf', 'deep': '#002e99',
        })
        self.assertEqual(mapping['#3b45fd'], '#3689e6')
        self.assertEqual(mapping['#1851b4'], '#0d52bf')
        self.assertEqual(mapping['#6191f3'], '#64baff')
        self.assertEqual(set(mapping), set(accent.FAMILY))

    def test_all_named_action_fills_have_readable_white_labels(self):
        for name, stops in accent.PALETTES.items():
            with self.subTest(accent=name):
                self.assertGreaterEqual(contrast_ratio('#ffffff', stops[4]), 4.5)
                light_text, dark_text = accent.text_stops(dict(zip(
                    ('light', 'dark', 'accent', 'pressed', 'deep'), stops
                )))
                self.assertGreaterEqual(contrast_ratio(light_text, '#ffffff'), 4.5)
                self.assertGreaterEqual(contrast_ratio(dark_text, '#1a1a1a'), 4.5)

    def test_stylesheet_maps_semantic_roles_and_preserves_width(self):
        source = (
            b'.link{color:#2c6bed}.button{background:#2c6bed;color:#fff}'
            b'.dark-theme .link{color:#2c6bed}'
            b'.logo{background-color:#3b45fd}'
            b'.module-message__container--outgoing-ultramarine{'
            b'background-image:linear-gradient(180deg,#0552f0,#2c6bed)}'
            b'@layer theme{:root{--axo-color-brand-primary:#3b45fd;'
            b'--axo-color-label-accent:light-dark(#030ffc,#99a1ff);'
            b'--axo-color-fill-accent:light-dark(#4655ff,#5563ff);'
            b'--axo-color-fill-accent-pressed:light-dark(#3b4af4,#616eff);'
            b'--axo-color-border-selected:light-dark(#4655ff,#c9ceff);'
            b'--axo-color-surface-message-outgoing:light-dark(#2267f5,#2267f5);'
            b'--axo-color-label-accent:light-dark(#000cf3,#b6bcff);'
            b'--axo-color-fill-accent:light-dark(#1f31ff,#2536f9);'
            b'--axo-color-fill-accent-pressed:light-dark(#0519ff,#2e3ffa);'
            b'--axo-color-border-selected:light-dark(#3243ff,#c9ceff);'
            b'--axo-color-surface-message-outgoing:light-dark(#0842b9,#0842b9);'
            b'--axo-color-fill-accent-tint:light-dark('
            b'oklab(45.3524% -.0303155 -.305089/.06),'
            b'oklab(74.1051% .0208054 -.133796/.12))}}'
        )
        changed, count = accent.patch_stylesheet(source, accent.palette_for('#3689e6'))
        self.assertEqual(len(changed), len(source))
        self.assertGreater(count, 10)
        self.assertIn(b'.link{color:#002e99}', changed)
        self.assertIn(b'.button{background:#002e99;color:#fff}', changed)
        self.assertIn(b'.dark-theme .link{color:#64baff}', changed)
        self.assertIn(b'.logo{background-color:#3689e6}', changed)
        self.assertIn(b'linear-gradient(180deg,#002e99,#002e99)', changed)
        self.assertIn(b'--axo-color-label-accent:light-dark(#002e99,#64baff)', changed)
        self.assertIn(b'--axo-color-fill-accent:light-dark(#002e99,#002e99)', changed)
        self.assertIn(b'--axo-color-border-selected:light-dark(#0d52bf,#8cd5ff)', changed)
        self.assertNotIn(b'#3b45fd', changed)

    def test_every_named_palette_preserves_stylesheet_width(self):
        source = (
            b'.link{color:#2c6bed}.dark-theme .link{color:#2c6bed}'
            b'.brand{color:#3b45fd}'
            b'--axo-color-label-accent:light-dark(#030ffc,#99a1ff);'
            b'oklab(45.3524% -.0303155 -.305089/.06)'
        )
        for name, value in accent.ACCENTS.items():
            with self.subTest(accent=name):
                changed, _ = accent.patch_stylesheet(source, accent.palette_for(value))
                self.assertEqual(len(changed), len(source))
                self.assertNotIn(b'#3b45fd', changed)
                self.assertIn(value.encode(), changed)

    def test_custom_accent_keeps_a_complete_generated_ramp(self):
        mapping = accent.build_map('#123456')
        self.assertEqual(set(mapping), set(accent.FAMILY))
        self.assertEqual(mapping['#3b45fd'], '#123456')
        self.assertTrue(all(len(value) == 7 for value in mapping.values()))

    def test_archive_patches_only_theme_assets_and_refreshes_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / 'app.asar'
            target = Path(tmp) / 'patched.asar'
            source_assets = asar_fixture(original)
            _, changed = accent.patch(str(original), str(target), '#3689e6')
            self.assertEqual(set(changed), {
                'stylesheets/manifest.css', 'stylesheets/tailwind.css',
                'bundles/main.js', 'bundles/preload/main.js',
            })
            with target.open('rb') as handle:
                header, _, base = accent.read_header(handle)
                handle.seek(0)
                blob = handle.read()
            entries = dict(accent.walk(header))
            for path, source in source_assets.items():
                entry = entries[path]
                data = blob[base + int(entry['offset']):base + int(entry['offset']) + entry['size']]
                self.assertEqual(len(data), len(source), path)
                if path == 'images/avatars/avatar_cat.svg':
                    self.assertEqual(data, source)
                if path == 'stylesheets/tailwind.css':
                    self.assertIn(b'--axo-color-brand-primary:#3689e6', data)
                    self.assertIn(b'--axo-color-label-accent:light-dark(#002e99,#64baff)', data)
                    self.assertIn(b'--axo-color-surface-message-outgoing:light-dark(#002e99,#002e99)', data)
                if path == 'bundles/main.js':
                    self.assertIn(b'`#3689e6`', data)
                    self.assertIn(b'const chat=`#2c6bed`', data)
                if path == 'bundles/preload/main.js':
                    self.assertEqual(data.count(b'#3689E6'), 2)
                    self.assertIn(b'const chat="#2c6bed"', data)
                if path in changed:
                    self.assertNotEqual(entry['integrity']['hash'], '0' * 64, path)


if __name__ == '__main__':
    unittest.main()
