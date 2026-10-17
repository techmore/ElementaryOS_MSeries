#!/usr/bin/env python3
"""Verify runtime dependencies survive the pruned Apple Silicon overlay."""
import configparser
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def packages(path):
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.read(ROOT / path)
    return set(config.get('Content', 'Packages', fallback='').split())


def verify_image_output(output):
    roots = [p for p in Path(output).glob('liveiso_*') if p.is_dir()]
    if len(roots) != 1:
        raise ValueError('Expected exactly one built liveiso tree')
    plugin = roots[0] / 'usr/lib/aarch64-linux-gnu/wingpanel-9/libnetwork.so'
    if not plugin.is_file() or b'Show speed in menu bar' not in plugin.read_bytes():
        raise ValueError('Built live ISO is missing the patched network indicator')
    source = ROOT / 'mkosi.images/apple-silicon/mkosi.extra'
    required = [p.relative_to(source) for p in source.rglob('*')
                if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    missing = [str(p) for p in required if not (roots[0] / p).is_file()]
    if missing:
        raise ValueError('Built live ISO is missing hardware payload: ' + ', '.join(missing))


def validate_summary(text):
    sections = {}
    for part in text.split('IMAGE: ')[1:]:
        name = part.splitlines()[0].strip()
        sections[name] = part
    for name in ('liveiso', 'sysupdate'):
        if 'apple-silicon_arm64-' not in sections.get(name, ''):
            raise ValueError(f'{name} effective config does not consume the Apple hardware overlay')


class ImageWiringTests(unittest.TestCase):
    def test_built_live_image_requires_hardware_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'liveiso_test'
            shutil.copytree(ROOT / 'mkosi.images/apple-silicon/mkosi.extra', root)
            plugin = root / 'usr/lib/aarch64-linux-gnu/wingpanel-9/libnetwork.so'
            plugin.parent.mkdir(parents=True, exist_ok=True)
            plugin.write_bytes(b'patched network indicator: Show speed in menu bar')
            verify_image_output(directory)
            (root / 'usr/libexec/mseries-brightness').unlink()
            with self.assertRaises(ValueError):
                verify_image_output(directory)

    def test_effective_summary_requires_overlay_in_both_images(self):
        overlay = 'Extra Trees: /work/mkosi.output/apple-silicon_arm64-123'
        validate_summary('IMAGE: liveiso\n' + overlay + '\nIMAGE: sysupdate\n' + overlay)
        with self.assertRaises(ValueError):
            validate_summary('IMAGE: liveiso\nExtra Trees: none\nIMAGE: sysupdate\n' + overlay)

    def test_finalize_preserves_overlay_helpers_and_prunes_package_payload(self):
        source = ROOT / 'mkosi.images/apple-silicon'
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image'
            shutil.copytree(source / 'mkosi.extra', image,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            # The real build installs this compiled component before finalize.
            unit = image / 'usr/lib/systemd/system/touchegg.service'
            unit.write_text('[Service]\nExecStart=/usr/bin/touchegg --daemon\n[Install]\nWantedBy=multi-user.target\n')
            # Runtime paths must survive package pruning and sysupdate's /usr boundary.
            for path in ['usr/lib/omarchy-mlx/venv/bin/python',
                         'usr/lib/omarchy-mlx/vulkan/honeykrisp_icd.aarch64.json',
                         'usr/lib/mseries-ai/llama/bin/llama-server',
                         'usr/bin/mlx-omarchy-serve',
                         'usr/share/omarchy-mlx/serve-catalog.json',
                         'usr/share/doc/mseries-local-ai/SOURCE']:
                target = image / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('synthetic local AI payload')
            expected = {p.relative_to(image) for p in image.rglob('*') if p.is_file()}
            payload = image / 'usr/bin/package-payload'
            payload.parent.mkdir(parents=True, exist_ok=True)
            payload.write_text('must be pruned')
            tools = Path(directory) / 'tools'
            tools.mkdir()
            compiler = tools / 'chroot'
            compiler.write_text('#!/bin/sh\n# Fixture only: target dconf is absent in this synthetic root.\ntouch "$1$4"\n')
            compiler.chmod(0o755)
            subprocess.run(['bash', str(source / 'mkosi.finalize')],
                           env={**os.environ, 'BUILDROOT': str(image), 'SRCDIR': str(ROOT),
                                'PATH': str(tools) + os.pathsep + os.environ['PATH']}, check=True)
            for path in expected:
                with self.subTest(path=str(path)):
                    self.assertTrue((image / path).is_file())
            self.assertFalse(payload.exists())

    def test_consumers_install_overlay_runtime_dependencies(self):
        overlay = packages('mkosi.images/apple-silicon/mkosi.conf')
        runtime = overlay - {'initramfs-tools'}
        self.assertTrue(runtime)
        for consumer in (
            'mkosi.images/liveiso/mkosi.conf.d/arch.arm64.conf',
            'mkosi.images/sysupdate/mkosi.conf.d/arch.arm64.conf',
        ):
            with self.subTest(consumer=consumer):
                self.assertFalse(runtime - packages(consumer),
                                 f'{consumer} loses runtime dependencies after overlay pruning')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--summary':
        validate_summary(Path(sys.argv[2]).read_text())
        print('Effective liveiso/sysupdate hardware overlay wiring passed')
    elif len(sys.argv) == 3 and sys.argv[1] == '--image-output':
        verify_image_output(sys.argv[2])
        print('Built live ISO hardware payload check passed')
    else:
        unittest.main()
