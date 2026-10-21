import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest


LANE = Path(__file__).with_name("unified72")


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), LANE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = load("check-legacy-dtb")
trial = load("prepare-j314s-trial")


class Unified72BootTests(unittest.TestCase):
    def test_trial_preparation_rejects_live_system_outputs_before_reading_inputs(self):
        for path in ("/boot/never-stage-trial", "/usr/lib/never-stage-trial", "/etc/never-stage-trial", "/Volumes/never-stage-trial"):
            with self.assertRaisesRegex(ValueError, "private work directory"):
                trial.prepare(SimpleNamespace(output=Path(path)))

    def test_trial_preparation_preserves_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "fresh private"):
                trial.prepare(SimpleNamespace(output=Path(directory)))

    def test_crypto_transition_policy_requires_explicit_matching_root_cipher(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new"
            with self.assertRaisesRegex(ValueError, "observed AES-XTS"):
                trial.prepare(SimpleNamespace(output=output, root_cipher="serpent-xts-plain64"))
            self.assertFalse(output.exists())

    def test_trial_preparation_refuses_a_different_package_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "wrong.deb"
            package.write_bytes(b"not the audited package")
            with self.assertRaisesRegex(ValueError, "package identity differs"):
                trial.prepare(SimpleNamespace(output=root / "new", root_cipher="aes-xts-plain64", package=package))
            self.assertFalse((root / "new").exists())

    def test_fdt_parser_reads_the_big_endian_root_property(self):
        value = b"apple,j314s\0"
        tokens = struct.pack(">I", 1) + b"\0" * 4
        tokens += struct.pack(">III", 3, len(value), 0) + value
        tokens += b"\0" * (-len(tokens) % 4)
        tokens += struct.pack(">II", 2, 9)
        names = b"compatible\0"
        strings = 56 + len(tokens)
        header = struct.pack(">10I", 0xd00dfeed, strings + len(names), 56, strings, 40, 17, 16, 0, len(names), len(tokens))
        data = header + b"\0" * 16 + tokens + names
        self.assertEqual(legacy.fdt(data), {"/": {"compatible": value}})
        self.assertEqual(legacy.strings(value), ["apple,j314s"])

    def test_fdt_parser_refuses_truncated_or_wrong_format_inputs(self):
        for data in (b"", b"\0" * 40, b"\xd0\x0d\xfe\xed"):
            with self.assertRaises(ValueError):
                legacy.fdt(data)

    def test_iommu_cells_cannot_silently_truncate(self):
        self.assertEqual(legacy.cells(b"\0\0\0\x01"), (1,))
        with self.assertRaisesRegex(ValueError, "unaligned"):
            legacy.cells(b"\0\0\x01")

    def test_old_module_exceptions_are_explicit_and_narrow(self):
        self.assertEqual(set(trial.TRANSITIONS), {
            "kernel/crypto/fcrypt.ko", "kernel/crypto/pcbc.ko", "kernel/lib/raid6/raid6_pq.ko"})
        self.assertEqual(len(trial.BASE_SHA), hashlib.sha256().digest_size * 2)


if __name__ == "__main__":
    unittest.main()
