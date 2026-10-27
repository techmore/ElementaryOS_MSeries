import concurrent.futures
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from conversion import ConversionError, convert, local_file
from install import contract


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "holiday $(literal) image.heic"
        self.source.write_bytes(b"original-image")

    @staticmethod
    def encode(source, destination, image_format):
        destination.write_bytes(b"encoded-copy")

    def test_collision_never_changes_source_or_existing_file(self):
        first = self.source.with_suffix(".jpg")
        first.write_bytes(b"existing-copy")
        result = convert(str(self.source), "jpeg", self.encode)
        self.assertTrue(result.name.endswith(" (1).jpg"))
        self.assertEqual(self.source.read_bytes(), b"original-image")
        self.assertEqual(first.read_bytes(), b"existing-copy")
        self.assertEqual(result.read_bytes(), b"encoded-copy")

    def test_concurrent_publication_uses_distinct_names(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: convert(str(self.source), "jpeg", self.encode), range(4)))
        self.assertEqual(len(set(results)), 4)
        self.assertEqual(self.source.read_bytes(), b"original-image")
        self.assertFalse(list(self.source.parent.glob(".mseries-image-*")))

    def test_failed_encoder_cleans_stage_and_publishes_nothing(self):
        def fail(source, stage, fmt):
            stage.write_bytes(b"partial")
            raise ConversionError("Unsupported decoder")
        with self.assertRaisesRegex(ConversionError, "Unsupported decoder"):
            convert(str(self.source), "jpeg", fail)
        self.assertEqual(list(self.source.parent.iterdir()), [self.source])

    def test_cancel_after_encode_does_not_publish(self):
        cancelled = []
        def encode(source, stage, fmt):
            self.encode(source, stage, fmt)
            cancelled.append(True)
        with self.assertRaisesRegex(ConversionError, "cancelled"):
            convert(str(self.source), "jpeg", encode, lambda: bool(cancelled))
        self.assertEqual(list(self.source.parent.iterdir()), [self.source])

    def test_write_failure_keeps_source_and_removes_staging(self):
        with patch("conversion.os.link", side_effect=PermissionError(13, "Permission denied")):
            with self.assertRaisesRegex(ConversionError, "Permission denied"):
                convert(str(self.source), "jpeg", self.encode)
        self.assertEqual(list(self.source.parent.iterdir()), [self.source])

    def test_jpeg2000_is_distinct_and_uri_inputs_are_literal(self):
        result = convert(self.source.as_uri(), "jpeg2000", self.encode)
        self.assertEqual(result.suffix, ".jp2")
        self.assertEqual(local_file(self.source.as_uri()), self.source)
        for value in ("https://example.com/image.heic", "file://remote/image.heic"):
            with self.assertRaises(ConversionError):
                local_file(value)

    def test_contract_has_no_shell_and_handles_special_prefix(self):
        data = contract(Path('/tmp/my "tools" 100%/convert'), "jpeg", ["image/heic"])
        self.assertIn("Name=Convert to JPEG\n", data)
        self.assertIn('100%%', data)
        self.assertIn(" --format jpeg -- %U", data)
        self.assertNotIn("sh -c", data)
        self.assertIn("MimeType=image/heic;", data)


if __name__ == "__main__":
    unittest.main()
