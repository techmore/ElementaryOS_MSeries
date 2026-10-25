"""Create a new image beside its source; never overwrite or delete user files."""
from pathlib import Path
import os
import tempfile
from urllib.parse import unquote, urlsplit


class ConversionError(Exception):
    pass


def local_file(value):
    if value.startswith("file:"):
        uri = urlsplit(value)
        if uri.netloc not in ("", "localhost") or uri.query or uri.fragment:
            raise ConversionError("Choose a local image file.")
        return Path(unquote(uri.path)).absolute()
    if "://" in value:
        raise ConversionError("Download the image before converting it.")
    return Path(value).absolute()


def convert(value, image_format, encode, cancelled=lambda: False):
    source = local_file(value)
    extension = {"jpeg": ".jpg", "jpeg2000": ".jp2"}.get(image_format)
    if not extension:
        raise ConversionError("Unsupported output format.")
    if not source.is_file():
        raise ConversionError("The selected image is missing or is not a regular file.")
    if cancelled():
        raise ConversionError("Conversion cancelled.")
    stage = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".mseries-image-", suffix=".tmp", dir=source.parent)
        os.close(descriptor)
        stage = Path(name)
        encode(source, stage, image_format)
        if stage.stat().st_size == 0:
            raise ConversionError("The encoder did not produce an image.")
        with stage.open("rb") as stream:
            os.fsync(stream.fileno())
        if cancelled():
            raise ConversionError("Conversion cancelled.")
        for number in range(10000):
            suffix = f" ({number})" if number else ""
            destination = source.with_name(source.stem + suffix + extension)
            try:
                # Same-directory hard-link publication is atomic and cannot replace
                # a pre-existing file, including a symlink or a concurrent output.
                os.link(stage, destination)
                return destination
            except FileExistsError:
                continue
        raise ConversionError("Too many copies with this name. Rename the source and retry.")
    except OSError as error:
        raise ConversionError(f"Could not save a new copy beside the image: {error.strerror or error}") from error
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)


class PixbufEncoder:
    MAX_PIXELS = 100_000_000

    def __init__(self):
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        self.pixbuf = GdkPixbuf
        self.writers = {f.get_name(): f for f in GdkPixbuf.Pixbuf.get_formats() if f.is_writable()}

    def output_formats(self):
        formats = {}
        if "jpeg" in self.writers:
            formats["jpeg"] = "jpeg"
        for name, writer in self.writers.items():
            if "image/jp2" in writer.get_mime_types():
                formats["jpeg2000"] = name
                break
        return formats

    def __call__(self, source, destination, image_format):
        codec = self.output_formats().get(image_format)
        if codec is None:
            raise ConversionError("This computer has no encoder for the selected format.")
        try:
            info, width, height = self.pixbuf.Pixbuf.get_file_info(str(source))
            if info is None:
                raise ConversionError("This image format cannot be decoded. HEIC/HEIF requires an installed GdkPixbuf loader.")
            if width <= 0 or height <= 0 or width * height > self.MAX_PIXELS:
                raise ConversionError("This image exceeds the 100-megapixel conversion limit.")
            image = self.pixbuf.Pixbuf.new_from_file(str(source))
            oriented = image.apply_embedded_orientation()
            if oriented is not None:
                image = oriented
            if image.get_width() * image.get_height() > self.MAX_PIXELS:
                raise ConversionError("This image exceeds the conversion limit.")
            if image.get_has_alpha():
                opaque = self.pixbuf.Pixbuf.new(self.pixbuf.Colorspace.RGB, False, 8, image.get_width(), image.get_height())
                opaque.fill(0xFFFFFFFF)
                image.composite(opaque, 0, 0, image.get_width(), image.get_height(), 0, 0, 1, 1,
                                self.pixbuf.InterpType.NEAREST, 255)
                image = opaque
            keys, values = (["quality"], ["95"]) if image_format == "jpeg" else ([], [])
            if not image.savev(str(destination), codec, keys, values):
                raise ConversionError("The image encoder did not save a copy.")
        except ConversionError:
            raise
        except Exception as error:
            raise ConversionError(f"Could not decode or encode the image: {error}") from error
