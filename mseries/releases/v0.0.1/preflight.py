#!/usr/bin/python3
"""Read-only admission for the scoped English F5 v0.0.1 update.

This is an update for an already working M1 Pro desktop, not a first-install or
hardware microphone test. No model/native library is loaded by these checks.
"""
import argparse
import ast
from contextlib import contextmanager
from email.parser import BytesParser
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

# Verifying or inspecting a package must not create unlisted cache files in it.
sys.dont_write_bytecode = True

VERSION = '0.0.1'
GIB = 1024 ** 3
NATIVE_SHA256 = '9f1f839d89a6d3a874c939ecf3108007cc0964a338596a35adb47c7e6c5c921d'
STREAM_UNIT = 'mseries-stream-dictate.service'
INPUT_UNIT = 'mseries-dictation-input.service'
NATIVE = 'native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so'
PACKAGE_LABEL = 'Package files match the complete v0.0.1 manifest'
PYTHON_QUERY = '''import json, sys, gi
gi.require_version('Gtk', '4.0')
gi.require_version('IBus', '1.0')
gi.require_version('Atspi', '2.0')
from gi.repository import Gtk, IBus, Atspi
print(json.dumps({'python': list(sys.version_info[:2]), 'bindings': True}))'''
BRIDGE_QUERY = '''import gi
from gi.repository import Gio
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
reply = bus.call_sync('org.techmore.DictationInput', '/org/techmore/DictationInput',
    'org.techmore.DictationInput', 'Ready', None, None,
    Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
print('ready' if reply.unpack() == (True,) else 'not-ready')'''


def run(args):
    """Only bounded read-only commands are passed by inspect()."""
    return subprocess.run(args, capture_output=True, text=True, timeout=5,
                          stdin=subprocess.DEVNULL, check=False)


def bounded(path, limit=65536):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Bound exceeded')
    return data


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@contextmanager
def package_file(root, name):
    """Open through owned directory descriptors without following any link."""
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = PurePosixPath(name).parts
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Package payload is not a regular file')
            yield stream
    finally:
        os.close(directory)


def result(checks):
    return {'passed': all(checks.values()), 'checks': checks,
            'failures': [label for label, passed in checks.items() if not passed]}


def verify_package(package_root):
    """Reject links, escapes, special files, missing/extra files and bad digests.

    The manifest describes integrity, not a detached authenticity signature.
    Release download authenticity still depends on the published release digest.
    """
    passed = False
    try:
        root = Path(package_root)
        if root.is_symlink() or not root.is_dir():
            raise ValueError('Invalid package')
        manifest_path = root / 'manifest.json'
        if manifest_path.is_symlink() or not stat.S_ISREG(manifest_path.stat().st_mode):
            raise ValueError('Invalid manifest')
        def unique(pairs):
            values = {}
            for key, value in pairs:
                if key in values:
                    raise ValueError('Duplicate manifest key')
                values[key] = value
            return values
        with package_file(root, 'manifest.json') as stream:
            raw = stream.read(2 * 1024 ** 2 + 1)
        if len(raw) > 2 * 1024 ** 2:
            raise ValueError('Manifest bound exceeded')
        manifest = json.loads(raw, object_pairs_hook=unique)
        if (not isinstance(manifest, dict) or manifest.get('version') != VERSION
                or not isinstance(manifest.get('source_commit'), str)
                or not re.fullmatch('[0-9a-f]{40}', manifest['source_commit'])):
            raise ValueError('Invalid release identity')
        files = manifest.get('files')
        if not isinstance(files, dict) or not 1 <= len(files) <= 4096:
            raise ValueError('Invalid file manifest')
        for name, expected in files.items():
            if (not isinstance(name, str) or len(name) > 512 or '\\' in name
                    or '\x00' in name or name == 'manifest.json'
                    or PurePosixPath(name).is_absolute()
                    or any(part in ('', '.', '..') for part in name.split('/'))
                    or not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected)):
                raise ValueError('Invalid manifest entry')
        actual = set()
        directories = 0
        def walk_error(error):
            raise error
        for parent, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
            directories += 1
            if directories > 4096:
                raise ValueError('Package directory bound exceeded')
            for name in dirs:
                if not stat.S_ISDIR((Path(parent) / name).lstat().st_mode):
                    raise ValueError('Linked or special directory')
            for name in names:
                path = Path(parent) / name
                if not stat.S_ISREG(path.lstat().st_mode):
                    raise ValueError('Linked or special file')
                actual.add(path.relative_to(root).as_posix())
                if len(actual) > 4097:
                    raise ValueError('Package file bound exceeded')
        if actual != set(files) | {'manifest.json'}:
            raise ValueError('Missing or unlisted package file')
        for name, expected in files.items():
            with package_file(root, name) as stream:
                before = os.fstat(stream.fileno())
                actual_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                after = os.fstat(stream.fileno())
            if (actual_digest != expected or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise ValueError('Package digest mismatch or concurrent edit')
        passed = True
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    return result({PACKAGE_LABEL: passed})


def inspect(root=Path('/'), home=None, runner=run):
    """Inspect an existing desktop; injectable filesystem/commands for tests.

    No raw paths, command output, journal, environment or settings leave this
    function. Failed checks return only the fixed friendly labels below.
    """
    root = Path(root)
    home = Path.home() if home is None else Path(home)
    base = home / '.local/share/mseries/stream'
    checks = {}
    def check(label, function):
        try:
            checks[label] = bool(function())
        except (OSError, ValueError, TypeError, KeyError, IndexError, SyntaxError,
                RecursionError, OverflowError,
                subprocess.SubprocessError, ImportError, AttributeError):
            checks[label] = False
        return checks[label]
    def query(args):
        completed = runner(args)
        if completed.returncode != 0 or not isinstance(completed.stdout, str) or len(completed.stdout) > 8192:
            raise ValueError('Command unavailable')
        return completed.stdout.strip()
    uid = None
    try:
        uid = int(query(['id', '-u']))
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        pass
    check('Run as a normal desktop user', lambda: uid is not None and 0 < uid < 2 ** 31)
    check('Linux aarch64 desktop', lambda: query(['uname', '-s']) == 'Linux' and query(['uname', '-m']) == 'aarch64')
    def compatible():
        names = bounded(root / 'sys/firmware/devicetree/base/compatible', 4096).split(b'\x00')
        return b'apple,j314s' in names and b'apple,t6000' in names
    check('Apple M1 Pro j314s machine', compatible)
    python = {}
    def python_bindings():
        python.update(json.loads(query(['/usr/bin/python3', '-I', '-c', PYTHON_QUERY])))
        return python.get('python') == [3, 14] and python.get('bindings') is True
    check('Python 3.14 with GTK4 IBus and accessibility bindings', python_bindings)
    def venv():
        config = bounded(base / 'venv/pyvenv.cfg', 8192).decode()
        versions = [line.split('=', 1)[1].strip() for line in config.splitlines()
                    if line.partition('=')[0].strip() == 'version']
        return (base / 'venv/bin/python').is_file() and len(versions) == 1 and versions[0].startswith('3.14.')
    check('Existing Python 3.14 speech virtual environment', venv)
    def metadata(name, version):
        found = []
        for path in (base / 'venv/lib/python3.14/site-packages').glob('*.dist-info/METADATA'):
            if path.is_symlink():
                continue
            message = BytesParser().parsebytes(bounded(path, 128 * 1024), headersonly=True)
            normalized = re.sub('[-_.]+', '-', message.get('Name', '').lower())
            if normalized == name:
                found.append(message.get('Version'))
        return found == [version]
    check('Existing transcribe.cpp 0.4.0 metadata', lambda: metadata('transcribe-cpp', '0.4.0'))
    check('Existing NumPy 2.5.4 metadata', lambda: metadata('numpy', '2.5.4'))
    check('Qualified native speech library digest', lambda: digest(base / NATIVE) == NATIVE_SHA256)
    check('Existing F5 controller and Unicode bridge files', lambda: all((base / name).is_file()
          for name in ('stream-dictate.py', 'dictation-input.py', 'dictation-input-client.py')))
    for unit, label in [(STREAM_UNIT, 'Existing CPU F5 listener'), (INPUT_UNIT, 'Existing IBus output bridge')]:
        check(label + ' is active', lambda unit=unit: query(['systemctl', '--user', 'is-active', unit]) == 'active')
        check(label + ' is enabled', lambda unit=unit: query(['systemctl', '--user', 'is-enabled', unit]) == 'enabled')
    check('Existing Unicode bridge is ready without service activation',
          lambda: query(['/usr/bin/python3', '-I', '-c', BRIDGE_QUERY]) == 'ready')
    def native_input():
        source_text = query(['gsettings', 'get', 'org.gnome.desktop.input-sources', 'sources'])
        # GVariant renders an empty source array with its explicit type.
        if source_text.startswith('@a(ss) '):
            source_text = source_text[7:]
        sources = ast.literal_eval(source_text)
        current = query(['gsettings', 'get', 'org.gnome.desktop.input-sources', 'current'])
        index = int(current.removeprefix('uint32 '))
        if not isinstance(sources, list) or not 0 <= index < len(sources):
            return False
        kind, name = sources[index]
        if not isinstance(name, str) or not 0 < len(name) <= 256:
            return False
        expected = 'xkb:us::eng' if kind == 'xkb' else name if kind == 'ibus' else None
        engine = query(['ibus', 'engine'])
        return expected is not None and engine == expected and engine not in ('dummy', 'mseries-dictation')
    check('Selected native IBus input remains valid', native_input)
    check('Desktop toolkit accessibility is enabled', lambda: query(
        ['gsettings', 'get', 'org.gnome.desktop.interface', 'toolkit-accessibility']) == 'true')
    check('Desktop GTK input module is IBus', lambda: query(
        ['gsettings', 'get', 'org.gnome.desktop.interface', 'gtk-im-module']) == "'ibus'")
    def remap():
        config = bounded(root / 'etc/udev/hwdb.d/91-mseries-dictation.hwdb').decode().splitlines()
        return ('evdev:name:Apple SPI [Kk]eyboard:*' in config
                and 'evdev:name:Apple MTP [Kk]eyboard:*' in config
                and any(line.strip() == 'KEYBOARD_KEY_7003e=f14' for line in config))
    check('Existing F5 remap configuration metadata (not a physical key test)', remap)
    def idle():
        if uid is None:
            return False
        pid = int(query(['systemctl', '--user', 'show', STREAM_UNIT, '-p', 'MainPID', '--value']))
        if pid <= 0:
            return False
        status_path = root / ('run/user/' + str(uid)) / 'mseries-dictation/status.json'
        info = status_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) & 0o077:
            return False
        row = json.loads(bounded(status_path, 4096))
        if (row.get('pid') != pid or row.get('phase') != 'ready'
                or row.get('output') != 'ibus' or row.get('backend') != 'cpu'):
            return False
        process = root / 'proc' / str(pid)
        if bounded(process / 'stat', 8192).decode().rpartition(')')[2].split()[0] in ('Z', 'X'):
            return False
        environment = bounded(process / 'environ', 128 * 1024).split(b'\x00')
        if b'STREAM_BACKEND=cpu' not in environment or b'STREAM_OUTPUT=ibus' not in environment:
            return False
        tasks = list((process / 'task').glob('*/children'))
        if not tasks:
            return False
        for children in tasks:
            for child in bounded(children, 65536).decode().split():
                if not child.isdigit():
                    return False
                state = bounded(root / 'proc' / child / 'stat', 8192).decode().rpartition(')')[2].split()[0]
                if state not in ('Z', 'X'):
                    return False
        return True
    check('F5 is idle in the existing CPU and IBus listener', idle)
    sample = {}
    def telemetry():
        path = Path(__file__).resolve().parents[2] / 'local-ai/machine.py'
        spec = importlib.util.spec_from_file_location('f5_release_machine', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sample.update(module.snapshot(root=root))
        return True
    sampled = check('Read-only memory fan and temperature telemetry is available', telemetry)
    check('Installed memory is between 28 and 36 GiB', lambda: sampled and 28 * GIB <= sample['total_bytes'] <= 36 * GIB)
    check('At least 8 GiB memory is currently available', lambda: sampled and sample['available_bytes'] >= 8 * GIB)
    check('All measured fans are below 2700 RPM', lambda: sampled and bool(sample['fans_rpm'])
          and all(0 <= value < 2700 for value in sample['fans_rpm'].values()))
    check('All measured temperatures are below 60 C', lambda: sampled and bool(sample['temperatures_c'])
          and all(0 < value < 60 for value in sample['temperatures_c'].values()))
    return result(checks)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='verify package, then inspect existing desktop prerequisites')
    parser.add_argument('--verify-package', action='store_true', help='verify the complete package without inspecting the desktop')
    parser.add_argument('--package-root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--json', action='store_true', help='print only fixed labels and boolean check results')
    args = parser.parse_args(argv)
    if not (args.check or args.verify_package):
        parser.error('Choose --check or --verify-package')
    report = verify_package(args.package_root)
    if report['passed'] and args.check:
        report = result({**report['checks'], **inspect()['checks']})
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for label, passed in report['checks'].items():
            print(('PASS: ' if passed else 'FAIL: ') + label)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
