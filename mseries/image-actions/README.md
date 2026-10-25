# Files image conversion actions

Issue [#531](https://github.com/techmore/ElementaryOS_MSeries/issues/531).
Native GTK4/Granite action dialogs, using elementary Contractor for Files'
right-click menu. This is a small file action, not a separate image library or
replacement for the Preview viewer tracked in #530. Python GI follows the
existing Apple Passwords and Battery utility surfaces; no new toolkit or app
framework is introduced.

## User journey

Select images in Files, including AirDrop photos in Downloads. Choose Convert
to JPEG. A progress window reports the batch and each saved copy or failure;
a native notification reports completion. Originals are never overwritten or
deleted. Copies are saved beside the selected paths with `.jpg` extensions;
existing names receive numbered suffixes. JPEG 2000 is a separately named
action, installed only if GdkPixbuf reports a writable `image/jp2` encoder.

Transparent areas are composited on white and embedded orientation is applied.
The new image does not promise preservation of EXIF/GPS or color-profile
metadata. HEIC/HEIF works through the installed GdkPixbuf loader; an absent or
failed decoder produces a useful error, never an empty success. Multi-image
HEIF sequences are decoded according to the loader's still-image behavior;
this action does not claim to preserve sequences, Live Photos or animation.

## Install on elementary

Runtime dependencies: Python3 GI, GTK4, Granite7, GdkPixbuf and Contractor.
HEIC support uses `heif-gdk-pixbuf` and the appropriate libheif decoder plugin
on Ubuntu. This installer does not install system packages or restart Files,
Contractor, Wingpanel or another service.

```sh
python3 mseries/image-actions/install.py
```

Installs under `~/.local` (or `--prefix`) and honors absolute `XDG_DATA_HOME`.
Contracts live in its `contractor/` directory and the hidden desktop entry in
`applications/`. If a menu was already open, close and reopen it. Uninstall:

```sh
python3 mseries/image-actions/install.py --uninstall
```

Only this action's files are removed. Source/converted images are retained.
For scripts, `~/.local/bin/mseries-image-convert --headless -- FILE...` emits
per-file JSON results with a failing exit status if any conversion fails.

## File and concurrency behavior

Each encoder writes a private temporary file in the source directory. After
encoding and fsync, a same-directory hard link publishes a complete copy without
replacing any existing path. Concurrent jobs retry collisions. Temporary output
is removed on handled errors/cancellation. Destination filesystems must support
hard links; unsupported filesystems fail without modifying the original. A
forced process termination can leave a hidden `.mseries-image-*.tmp` file, but
never replaces the original or publishes a partial destination. This is per-file
publication, not an atomic batch. Output permissions start private (0600).

Cancel stops remaining files and prevents publication after the current encoder
returns. Closing a busy dialog requests cancellation and keeps the window open
until that operation finishes. Limits: 64 selected images and 100 megapixels per
image. The header inspection bounds normal decoding, but codec behavior and
resource use remain loader-dependent.

## Verification and source boundary

Seven pure transaction/contract tests run on macOS. Linux ARM64 CI exercises
real GdkPixbuf JPEG decoding/encoding, readable output dimensions, original
hash preservation, unavailable decoders/encoders, special-character installation
paths, desktop contract parsing, launch and uninstall. Isolated GTK probes
exercise actual progress/completion and notification delivery against a private
D-Bus notification service; light/dark renders at requested widths420/560 are
retained for review. These do not establish a physical Files right-click test
or owner acceptance on the target boot volume. #531 stays open for that gate.

Contract format was inspected from first-party
[elementary Contractor documentation](https://github.com/elementary/contractor#writing-contract-files)
and its `ContractKeyFile.vala`/`ContractMatcher.vala` source on October 25, 2026.
Only the documented format is used; no Contractor code or external media is
vendored. Images in tests are generated fixture pixels. No user images or
accounts are used by CI. New UI follows native theme preferences; the project
currently has no gettext setup for this utility, so localization remains open.
