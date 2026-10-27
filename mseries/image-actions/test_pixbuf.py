"""Real codec/desktop boundary checks. Linux CI supplies GdkPixbuf/GIO."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from conversion import ConversionError, PixbufEncoder, convert

try:
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GdkPixbuf, Gio, GioUnix, GLib
except ImportError:
    GdkPixbuf = None


@unittest.skipIf(GdkPixbuf is None, "Linux GI runtime required")
class CodecTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "photo with spaces.png"
        image = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 24, 16)
        image.fill(0x11223388)
        image.savev(str(self.source), "png", [], [])
        self.before = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def test_real_jpeg_copy_is_viewable_and_original_unchanged(self):
        result = convert(self.source.as_uri(), "jpeg", PixbufEncoder())
        image = GdkPixbuf.Pixbuf.new_from_file(str(result))
        self.assertEqual((image.get_width(), image.get_height()), (24, 16))
        self.assertFalse(image.get_has_alpha())
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.before)
        self.assertEqual(GdkPixbuf.Pixbuf.get_file_info(str(result))[0].get_name(), "jpeg")

    def test_unsupported_codec_is_explicit_and_creates_no_output(self):
        bad = self.root / "unsupported.heic"
        bad.write_bytes(b"not an image")
        with self.assertRaisesRegex(ConversionError, "cannot be decoded|decode or encode"):
            convert(str(bad), "jpeg", PixbufEncoder())
        self.assertFalse(bad.with_suffix(".jpg").exists())
        self.assertFalse(list(self.root.glob(".mseries-image-*")))

    def test_real_heic_to_jpeg(self):
        image = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 128, 96)
        image.fill(0x4488CCFF)
        png = self.root / "heic-source.png"
        image.savev(str(png), "png", [], [])
        heic = self.root / "received.heic"
        encoded = subprocess.run(["heif-enc", "-q", "50", "-o", str(heic), str(png)],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(encoded.returncode, 0, encoded.stderr[-2000:])
        original = heic.read_bytes()
        result = convert(str(heic), "jpeg", PixbufEncoder())
        decoded = GdkPixbuf.Pixbuf.new_from_file(str(result))
        self.assertEqual((decoded.get_width(), decoded.get_height()), (128, 96))
        self.assertEqual(heic.read_bytes(), original)

    def test_jpeg2000_encoder_capability_is_respected(self):
        encoder = PixbufEncoder()
        if "jpeg2000" in encoder.output_formats():
            result = convert(str(self.source), "jpeg2000", encoder)
            image = GdkPixbuf.Pixbuf.new_from_file(str(result))
            self.assertEqual(image.get_width(), 24)
        else:
            with self.assertRaisesRegex(ConversionError, "no encoder"):
                convert(str(self.source), "jpeg2000", encoder)

    def test_installer_registers_only_writable_formats_and_uninstalls(self):
        prefix = self.root / 'tools with "quotes" 100%'
        env = dict(os.environ, XDG_DATA_HOME=str(prefix / "share"))
        script = Path(__file__).with_name("install.py")
        subprocess.run([sys.executable, str(script), "--prefix", str(prefix)], env=env, check=True)
        contracts = prefix / "share/contractor"
        self.assertTrue((contracts / "org.techmore.mseries.image-jpeg.contract").is_file())
        self.assertEqual((contracts / "org.techmore.mseries.image-jpeg2000.contract").exists(),
                         "jpeg2000" in PixbufEncoder().output_formats())
        # Validate the actual quoted Exec with GLib's desktop parser, not a shell.
        raw = (contracts / "org.techmore.mseries.image-jpeg.contract").read_text()
        key = GLib.KeyFile()
        data = raw.replace("[Contractor Entry]", "[Desktop Entry]").replace(" --format ", " --headless --format ") + "Type=Application\n"
        key.load_from_data(data, len(data.encode()), GLib.KeyFileFlags.NONE)
        info = GioUnix.DesktopAppInfo.new_from_keyfile(key)
        self.assertIsNotNone(info)
        self.assertTrue(info.supports_uris())
        self.assertTrue(info.launch([Gio.File.new_for_path(str(self.source))], None))
        output = self.source.with_suffix(".jpg")
        for _ in range(100):
            if output.exists():
                break
            time.sleep(0.05)
        self.assertTrue(output.is_file(), "GIO launched the installed contract with literal URI arguments")
        self.assertEqual(GdkPixbuf.Pixbuf.new_from_file(str(output)).get_width(), 24)
        subprocess.run([sys.executable, str(script), "--prefix", str(prefix), "--uninstall"], env=env, check=True)
        self.assertFalse(list(contracts.glob("*.contract")))
        self.assertTrue(self.source.exists())


if __name__ == "__main__":
    unittest.main()
