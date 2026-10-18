#!/usr/bin/python3
"""Embed the reviewed source in sudo python3 -I -c; do not run a mutable loader file."""
import hashlib
import os
from pathlib import Path
import stat
import sys

if not sys.flags.isolated or os.geteuid() != 0 or len(sys.argv) != 5:
    raise SystemExit('Usage: sudo /usr/bin/python3 -I -c REVIEWED_LOADER HELPER_SHA HELPER_PATH STAGE REQUEST_SHA')
expected, helper, stage, request = sys.argv[1:]
owner = os.environ.get('SUDO_UID', '')
if not owner.isdecimal() or int(owner) == 0 or any(len(d) != 64 or any(c not in '0123456789abcdef' for c in d) for d in (expected, request)):
    raise SystemExit('Invalid review identities')
if not Path(helper).is_absolute() or not Path(stage).is_absolute():
    raise SystemExit('Absolute paths required')
fd = os.open(helper, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
with os.fdopen(fd, 'rb') as source:
    before = os.fstat(source.fileno())
    if not stat.S_ISREG(before.st_mode) or before.st_uid != int(owner) or before.st_nlink != 1 or before.st_mode & 0o022 or before.st_size > 1024 * 1024:
        raise SystemExit('Unsafe helper')
    data = source.read(1024 * 1024 + 1)
    after = os.fstat(source.fileno())
    fields = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if len(data) > 1024 * 1024 or any(getattr(before, k) != getattr(after, k) for k in fields) or hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit('Helper changed since review')
sys.argv = [helper, 'apply', '--stage', stage, '--request-sha256', request]
exec(compile(data, helper, 'exec'), {'__name__': '__main__', '__file__': helper})
