import gzip
import importlib.util
from pathlib import Path
import stat
import unittest

spec = importlib.util.spec_from_file_location('trial_initrd', Path(__file__).with_name('prepare-trial-initrd.py'))
trial = importlib.util.module_from_spec(spec); spec.loader.exec_module(trial)


class TrialInitrdTests(unittest.TestCase):
    def archive(self, name, data=b'data'):
        values = [1, stat.S_IFREG | 0o644, 0, 0, 1, 0, len(data), 0, 0, 0, 0, 0, 0]
        trailer = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        return trial.newc.encode([(name, values, data)], trailer)

    def test_early_cpio_padding_and_main_payload_are_preserved(self):
        early = self.archive('early_cpio', b'1\n') + b'\0' * 4096
        main = gzip.compress(self.archive('init'))
        prefix, compressed = trial.split_image(early + main)
        self.assertEqual(prefix, early)
        self.assertEqual(compressed, main)
        self.assertEqual(trial.newc.parse(gzip.decompress(compressed))[0][0][0], 'init')

    def test_gzip_only_input_is_supported_without_inventing_early_data(self):
        image = gzip.compress(self.archive('init'))
        self.assertEqual(trial.split_image(image), (b'', image))

    def test_unsafe_early_archive_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsafe archive path'):
            trial.split_image(self.archive('../escape') + gzip.compress(self.archive('init')))

    def test_truncated_and_unknown_main_formats_are_rejected(self):
        for data in (b'070701', self.archive('early_cpio') + b'not-a-gzip', b'unknown'):
            with self.assertRaises(ValueError):
                trial.split_image(data)
