"""Private, bounded dictation lifecycle status. Never stores audio or text."""
import json
import os
from pathlib import Path
import stat
import tempfile
import time

PHASES = {'loading', 'waiting', 'ready', 'listening', 'finishing', 'error', 'stopped', 'cancelled'}


def status_path():
    return Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / 'mseries-dictation/status.json'


def write_status(phase, output, backend):
    if phase not in PHASES or output not in ('ibus', 'ydotool') or not isinstance(backend, str) or len(backend) > 40:
        raise ValueError('Invalid dictation status')
    target = status_path()
    runtime = target.parent.parent
    if runtime.stat().st_uid != os.getuid(): raise ValueError('Runtime directory is not owned by the desktop user')
    target.parent.mkdir(mode=0o700, exist_ok=True)
    if target.parent.is_symlink() or target.parent.stat().st_uid != os.getuid():
        raise ValueError('Invalid dictation runtime directory')
    target.parent.chmod(0o700)
    fd, name = tempfile.mkstemp(prefix='.status-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({'pid': os.getpid(), 'phase': phase, 'output': output,
                'backend': backend, 'updated_at': time.time()}, stream)
        os.replace(name, target)
    finally:
        if os.path.exists(name): os.unlink(name)


def read_status():
    try:
        fd = os.open(status_path(), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077: return None
            row = json.loads(stream.read(4096))
        if set(row) != {'pid', 'phase', 'output', 'backend', 'updated_at'}: return None
        if row['phase'] not in PHASES or row['output'] not in ('ibus', 'ydotool'): return None
        if type(row['pid']) is not int or not isinstance(row['updated_at'], (int, float)): return None
        return row
    except (OSError, ValueError, TypeError):
        return None
