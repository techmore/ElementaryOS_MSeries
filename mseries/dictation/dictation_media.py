"""Quiet other audio while dictation listens, like macOS, then put it back exactly.

On start: pause MPRIS players that are Playing, then mute other apps' running
PipeWire playback streams. On end: unmute only the streams we muted and resume
only the players we paused. What we changed is written to a small state file
first, so if the daemon dies mid-session the next start can undo it.

WirePlumber normally remembers each app's mute ("stream-properties"). If we
muted a stream and the app then closed it, the app's next stream would start
muted. So saving is switched off (runtime only, never written to disk) while we
hold streams muted, and switched back on when we restore.

Never touched: streams that were already muted, idle streams, filter-chain
streams, our own children (the pw-play chimes), and any capture (microphone).
Every helper is bounded by a short timeout and never raises.
"""
import json, os, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MPRIS_PREFIX = 'org.mpris.MediaPlayer2.'
MPRIS_PATH = '/org/mpris/MediaPlayer2'
MPRIS_PLAYER = 'org.mpris.MediaPlayer2.Player'
RESTORE_SETTING = 'node.stream.restore-props'
RESUME_WINDOW = 600  # a crashed session older than this only unmutes; it does not restart music
PAUSE_SETTLE = 0.15  # let paused players drain their stream before we look for running ones


def state_path():
    base = os.environ.get('XDG_RUNTIME_DIR') or str(Path.home() / '.cache/mseries')
    return Path(base) / 'mseries-dictation-media.json'


def run_cmd(cmd, timeout=2):
    """stdout of a short command, or None when it fails, times out or is missing."""
    try:
        done = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def own_child(pid, me=None):
    """True for this process and its direct children (the chime's pw-play)."""
    me = os.getpid() if me is None else me
    if pid == me:
        return True
    try:
        stat = Path(f'/proc/{pid}/stat').read_text()
        return int(stat.rsplit(')', 1)[1].split()[1]) == me
    except (OSError, ValueError, IndexError):
        return False


def stream_key(props):
    """WirePlumber's restore key (state-stream.lua formKey)."""
    for k in ('media.role', 'application.id', 'application.name', 'media.name', 'node.name'):
        if props.get(k):
            return f"{props.get('media.class', '').removeprefix('Stream/')}:{k}:{props[k]}"
    return None


def parse_streams(dump):
    """App playback streams from pw-dump JSON: id, serial, key, pid, muted, running."""
    try:
        objects = json.loads(dump or '[]')
    except ValueError:
        return []
    objects = objects if isinstance(objects, list) else []
    # Pulse clients put the pid on the stream; native ones (pw-play) only on their client object.
    client_pid = {}
    for o in objects:
        if o.get('type') == 'PipeWire:Interface:Client':
            props = (o.get('info') or {}).get('props') or {}
            client_pid[o.get('id')] = props.get('application.process.id') or props.get('pipewire.sec.pid')
    out = []
    for o in objects:
        info = o.get('info') or {}
        props = info.get('props') or {}
        if o.get('type') != 'PipeWire:Interface:Node' or props.get('media.class') != 'Stream/Output/Audio':
            continue
        if str(props.get('node.link-group', '')).startswith('filter-chain') or props.get('node.passive') is True:
            continue  # the speaker DSP chain: muting it silences everything, our chime included
        pid = props.get('application.process.id') or client_pid.get(props.get('client.id'))
        if pid is None:
            continue
        muted = any(p.get('mute') for p in (info.get('params') or {}).get('Props') or [] if isinstance(p, dict))
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            pid = -1
        out.append({'id': o.get('id'), 'serial': props.get('object.serial'), 'key': stream_key(props),
                    'pid': pid, 'muted': bool(muted), 'running': info.get('state') == 'running'})
    return out


def plan_mute(streams, is_own=own_child):
    """Running, audible streams that are not ours."""
    return [s for s in streams if s['running'] and not s['muted'] and not is_own(s['pid'])]


class MediaQuiet:
    def __init__(self, run=run_cmd, path=None, sleep=time.sleep, clock=time.time, is_own=own_child):
        self.run, self.sleep, self.clock, self.is_own = run, sleep, clock, is_own
        self.path = Path(path) if path else state_path()
        self.lock = threading.Lock()
        self.pool = None

    # --- probes -------------------------------------------------------------
    def players(self):
        out = self.run(['busctl', '--user', 'list', '--acquired', '--no-legend']) or ''
        names = [l.split()[0] for l in out.splitlines() if l.split() and l.split()[0].startswith(MPRIS_PREFIX)]
        status = {}
        for name in names:
            reply = self.run(['busctl', '--user', '--timeout=1', 'get-property', name, MPRIS_PATH, MPRIS_PLAYER, 'PlaybackStatus'])
            if reply:
                status[name] = reply.strip().split(' ', 1)[-1].strip('"')
        return status

    def player_call(self, name, method):
        return self.run(['busctl', '--user', '--timeout=1', 'call', name, MPRIS_PATH, MPRIS_PLAYER, method]) is not None

    def streams(self):
        return parse_streams(self.run(['pw-dump'], timeout=3))

    def set_mute(self, node_id, mute):
        return self.run(['wpctl', 'set-mute', str(node_id), '1' if mute else '0']) is not None

    def restore_setting(self):
        out = self.run(['wpctl', 'settings', RESTORE_SETTING]) or ''
        return out.strip().rsplit(' ', 1)[-1] if out.strip() else None

    def set_restore_setting(self, value):
        self.run(['wpctl', 'settings', RESTORE_SETTING, value])  # runtime only: no --save

    # --- state file -------------------------------------------------------------
    def save(self, state):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(state))
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def load(self):
        try:
            state = json.loads(self.path.read_text())
            return state if isinstance(state, dict) else None
        except (OSError, ValueError):
            return None

    def clear(self):
        try: self.path.unlink()
        except OSError: pass

    # --- the two operations ----------------------------------------------------
    def quiet(self):
        """Pause playing players, then mute the other running streams. Records before it acts."""
        with self.lock:
            state = self.load() or {'time': self.clock(), 'paused': [], 'muted': [], 'setting': None}
            playing = [n for n, s in self.players().items() if s == 'Playing']
            state['paused'] = sorted(set(state['paused']) | set(playing))
            self.save(state)
            paused = [n for n in playing if self.player_call(n, 'Pause')]
            state['paused'] = sorted(set(state['paused']) - (set(playing) - set(paused)))
            if paused:
                self.sleep(PAUSE_SETTLE)
            mute = plan_mute(self.streams(), self.is_own)
            if mute and state.get('setting') is None:
                state['setting'] = self.restore_setting()
                self.save(state)
                if state['setting'] == 'true':
                    self.set_restore_setting('false')
            known = {s['serial'] for s in state['muted']}
            state['muted'] += [{'id': s['id'], 'serial': s['serial'], 'key': s['key']} for s in mute if s['serial'] not in known]
            self.save(state)
            for s in mute:
                self.set_mute(s['id'], True)
            return {'paused': paused, 'muted': [s['id'] for s in mute]}

    def restore(self, resume=True):
        """Undo whatever the state file says we did. Safe to call any number of times."""
        with self.lock:
            state = self.load()
            if not state:
                return {'unmuted': [], 'resumed': []}
            unmuted = []
            if state.get('muted'):
                serials = {s['serial'] for s in state['muted']}
                for s in self.streams():
                    if s['serial'] in serials and s['muted'] and self.set_mute(s['id'], False):
                        unmuted.append(s['id'])
            if state.get('setting') == 'true':
                self.set_restore_setting('true')
            resumed = []
            if resume and self.clock() - state.get('time', 0) < RESUME_WINDOW and state.get('paused'):
                status = self.players()
                for name in state['paused']:
                    if status.get(name) == 'Paused' and self.player_call(name, 'Play'):
                        resumed.append(name)
            self.clear()
            return {'unmuted': unmuted, 'resumed': resumed}

    # --- off the dictation threads, strictly in order ---------------------------
    def _submit(self, fn):
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='dictation-media')
        def safe():
            try: return fn()
            except Exception:
                return None  # quieting is a courtesy; it must never break dictation
        return self.pool.submit(safe)

    def begin(self):
        return self._submit(self.quiet)

    def end(self, wait=False):
        future = self._submit(self.restore)
        if wait:
            try: future.result(timeout=10)
            except Exception: pass
        return future
