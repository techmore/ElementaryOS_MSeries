#!/usr/bin/env python3
"""Offline regression tests with real .deb assembly and synthetic ARM64 payloads."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load('stage-brave')
validator = load('verify-factory-brave')


class BraveFactoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tree = self.root / 'package'
        control = tree / 'DEBIAN/control'
        control.parent.mkdir(parents=True)
        control.write_text('Package: brave-browser\nVersion: 1.0\nArchitecture: arm64\n'
                           'Maintainer: Test <test@example.invalid>\nDescription: Test fixture\n')
        runtime = tree / 'opt/brave.com/brave'
        for name in ['brave', 'chrome-sandbox', 'icudtl.dat', 'resources.pak',
                     'brave_resources.pak', 'v8_context_snapshot.bin', 'locales/en-US.pak', 'LICENSE']:
            path = runtime / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic fixture')
        (runtime / 'brave').write_bytes(b'\x7fELF\x02\x01' + bytes(12) + (183).to_bytes(2, 'little'))
        (runtime / 'brave').chmod(0o755)
        self.package = self.root / 'brave.deb'
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(tree), str(self.package)],
                       check=True, stdout=subprocess.DEVNULL)
        self.pin = self.root / 'pin.json'
        self.pin.write_text(json.dumps({'version': '1.0', 'architecture': 'arm64',
            'url': 'https://example.invalid/synthetic.deb', 'sha256': builder.digest(self.package)}))
        self.dest = self.root / 'image'

    def stage(self):
        builder.stage(self.dest, self.package, self.pin)

    def test_stage_without_maintainer_scripts_and_verify_usr_payload(self):
        self.stage()
        validator.verify(self.dest)
        self.assertFalse((self.dest / 'opt').exists())
        self.assertTrue((self.dest / 'usr/share/doc/mseries-brave/LICENSE').is_file())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.stage()

    def test_reject_corrupt_download_before_extraction(self):
        with self.package.open('ab') as stream:
            stream.write(b'corruption')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.stage()
        self.assertFalse(self.dest.exists())

    def test_reject_wrong_architecture_metadata(self):
        pin = json.loads(self.pin.read_text())
        pin['architecture'] = 'amd64'
        self.pin.write_text(json.dumps(pin))
        with self.assertRaisesRegex(ValueError, 'Architecture'):
            self.stage()

    def test_missing_locale_fails_final_image_validation(self):
        self.stage()
        (self.dest / 'usr/lib/mseries-brave/locales/en-US.pak').unlink()
        with self.assertRaises(FileNotFoundError):
            validator.verify(self.dest)

    def test_changed_binary_fails_final_image_validation(self):
        self.stage()
        (self.dest / 'usr/lib/mseries-brave/brave').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'payload changed'):
            validator.verify(self.dest)

    def test_non_arm64_executable_fails_validation(self):
        self.stage()
        binary = self.dest / 'usr/lib/mseries-brave/brave'
        binary.write_bytes(b'\x7fELF\x02\x01' + bytes(12) + (62).to_bytes(2, 'little'))
        manifest = self.dest / 'usr/share/doc/mseries-brave/files.json'
        files = json.loads(manifest.read_text())
        files['brave'] = builder.digest(binary)
        manifest.write_text(json.dumps(files))
        with self.assertRaisesRegex(ValueError, 'not ARM64'):
            validator.verify(self.dest)


if __name__ == '__main__':
    unittest.main()
