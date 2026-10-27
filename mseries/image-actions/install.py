#!/usr/bin/python3
"""User-local installation of Files contracts; no panel/service restarts."""
import argparse
import os
from pathlib import Path
import shutil
from conversion import PixbufEncoder


def quoted_exec(path):
    value = str(path).replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        value = value.replace(char, "\\" + char)
    # Desktop key-file escaping precedes Exec argument parsing.
    return ('"' + value + '"').replace("\\", "\\\\")


def contract(launcher, image_format, mimetypes):
    title = "JPEG" if image_format == "jpeg" else "JPEG 2000"
    return ("[Contractor Entry]\n" + f"Name=Convert to {title}\n"
            + "Description=Save a new image copy beside the original\nIcon=image-x-generic\n"
            + "MimeType=" + ";".join(sorted(set(mimetypes))) + ";\n"
            + "TryExec=/usr/bin/python3\n"
            + f"Exec=/usr/bin/python3 {quoted_exec(launcher)} --format {image_format} -- %U\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    prefix = args.prefix.expanduser().absolute()
    data = Path(os.environ.get("XDG_DATA_HOME") or prefix / "share")
    if not data.is_absolute():
        parser.error("XDG_DATA_HOME must be absolute")
    if any(c in str(prefix) + str(data) for c in "\n\r\x00"):
        parser.error("Installation paths must not contain line breaks or NUL")
    resources = data / "mseries/image-actions"
    contracts = data / "contractor"
    launcher = prefix / "bin/mseries-image-convert"
    desktop = data / "applications/org.techmore.mseries.ImageActions.desktop"
    owned = [contracts / f"org.techmore.mseries.image-{name}.contract" for name in ("jpeg", "jpeg2000")]
    if args.uninstall:
        for path in owned + [launcher, desktop]:
            path.unlink(missing_ok=True)
        for name in ("app.py", "conversion.py"):
            (resources / name).unlink(missing_ok=True)
        print("Image conversion actions removed. Source images are unchanged.")
        return
    encoder = PixbufEncoder()
    formats = encoder.output_formats()
    if "jpeg" not in formats:
        parser.error("A writable GdkPixbuf JPEG encoder is required.")
    mimetypes = [mime for f in encoder.pixbuf.Pixbuf.get_formats() for mime in f.get_mime_types()]
    mimetypes += ["image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"]
    for directory in (resources, contracts, launcher.parent, desktop.parent):
        directory.mkdir(parents=True, exist_ok=True)
    for name in ("app.py", "conversion.py"):
        shutil.copyfile(Path(__file__).parent / name, resources / name)
    launcher.write_text("#!/usr/bin/python3\nimport runpy, sys\nsys.path.insert(0, " + repr(str(resources))
                        + ")\nrunpy.run_path(" + repr(str(resources / "app.py")) + ", run_name='__main__')\n")
    launcher.chmod(0o755)
    for image_format, path in zip(("jpeg", "jpeg2000"), owned):
        if image_format in formats:
            path.write_text(contract(launcher, image_format, mimetypes))
        else:
            path.unlink(missing_ok=True)
    desktop.write_text("[Desktop Entry]\nType=Application\nName=Image Conversion\nNoDisplay=true\n"
                       + "Icon=image-x-generic\nExec=/usr/bin/python3 " + quoted_exec(launcher) + " -- %U\n")
    print("Installed Convert to JPEG in Files. " +
          ("JPEG 2000 is also available." if "jpeg2000" in formats else "No JPEG 2000 encoder is installed; that action is hidden."))


if __name__ == "__main__":
    main()
