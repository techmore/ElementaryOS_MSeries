#!/usr/bin/env python3
"""Verify runtime dependencies survive the pruned Apple Silicon overlay."""
import configparser
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def packages(path):
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.read(ROOT / path)
    return set(config.get('Content', 'Packages', fallback='').split())


class ImageWiringTests(unittest.TestCase):
    def test_finalize_preserves_overlay_helpers_and_prunes_package_payload(self):
        source = ROOT / 'mkosi.images/apple-silicon'
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image'
            shutil.copytree(source / 'mkosi.extra', image,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            expected = {p.relative_to(image) for p in image.rglob('*') if p.is_file()}
            payload = image / 'usr/bin/package-payload'
            payload.parent.mkdir(parents=True)
            payload.write_text('must be pruned')
            subprocess.run(['bash', str(source / 'mkosi.finalize')],
                           env={**os.environ, 'BUILDROOT': str(image)}, check=True)
            for path in expected:
                with self.subTest(path=str(path)):
                    self.assertTrue((image / path).is_file())
            self.assertFalse(payload.exists())

    def test_consumers_install_overlay_runtime_dependencies(self):
        overlay = packages('mkosi.images/apple-silicon/mkosi.conf')
        runtime = overlay - {'initramfs-tools'}
        self.assertTrue(runtime)
        for consumer in (
            'mkosi.images/liveiso/mkosi.profiles/aarch64/mkosi.conf',
            'mkosi.images/sysupdate/mkosi.conf.d/arch.arm64.conf',
        ):
            with self.subTest(consumer=consumer):
                self.assertFalse(runtime - packages(consumer),
                                 f'{consumer} loses runtime dependencies after overlay pruning')


if __name__ == '__main__':
    unittest.main()
