#!/usr/bin/python3
"""Restart the audio stack when it stops answering (Apple Silicon, asahi-audio DSP).

WirePlumber tears down asahi-audio's DSP filter chains when the sound cards go away, as they do
at every logout and some resumes. That teardown can crash WirePlumber or wedge its main thread,
which systemd never notices: every pactl call and every app then hangs until audio is restarted
by hand. This user service probes the PulseAudio socket and restarts PipeWire, its Pulse server
and WirePlumber when it stops answering.

Safe by construction, after omarchy-mac's omarchy-audio-watchdog (omarchy-mac-pkgs 222f7a8),
simplified for Pantheon, which has no Quickshell to protect:
  * only while this login session is active and unlocked, and only if the three units are up
    (a stopped service is the user's choice);
  * two failed probes in a row are needed, never one;
  * at most STACK_LIMIT restarts per window, then it tells the user once and stops trying until
    audio answers again;
  * never twice within SETTLE seconds, and never right after a resume (stale state).
"""
import os
import subprocess
import sys
import time
from pathlib import Path

SERVICES = ('pipewire.service', 'pipewire-pulse.service', 'wireplumber.service')
TICK = 10.0
PROBE_INTERVAL = 30.0
PROBE_TIMEOUT = 5
SETTLE = 30.0
RESUME_JUMP = 5.0
STACK_GAP = 120.0
STACK_LIMIT = (3, 1800.0)   # restarts, per seconds
HEALTHY_PROBES = 2


def allowed(restarts, now):
    """Pure budget check. restarts: boot-relative times of earlier restarts, oldest first.
    Returns (True, '') or (False, reason)."""
    count, window = STACK_LIMIT
    recent = [at for at in restarts if 0 <= now - at < window]
    if len(recent) >= count:
        return False, f'audio was already restarted {len(recent)} times recently'
    if any(0 <= now - at < SETTLE for at in restarts):
        return False, 'audio was restarted moments ago'
    if recent and now - recent[-1] < STACK_GAP:
        return False, f'audio was restarted less than {int(STACK_GAP)} seconds ago'
    return True, ''


def run(*args, timeout=10, env=None):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              env=dict(os.environ, LC_ALL='C', **(env or {})))
    except (OSError, subprocess.SubprocessError):
        return None


def apple_silicon():
    try:
        return b'apple,' in Path('/proc/device-tree/compatible').read_bytes().lower()
    except OSError:
        return False


def session_ok():
    """This login's own session is active and not locked. No session id: not a login session."""
    session = os.environ.get('XDG_SESSION_ID')
    if not session:
        # A systemd user service is not inside a login session: ask logind for the
        # user's graphical (Display) session.
        shown = run('loginctl', 'show-user', str(os.getuid()), '-p', 'Display', '--value')
        session = shown.stdout.strip() if shown is not None and shown.returncode == 0 else ''
    if not session:
        return False
    result = run('loginctl', 'show-session', session, '-p', 'Active', '-p', 'LockedHint', '--value')
    if result is None or result.returncode != 0:
        return False
    return result.stdout.split() == ['yes', 'no']   # Active=yes, LockedHint=no


def units_state():
    result = run('systemctl', '--user', 'is-active', *SERVICES)
    states = result.stdout.split() if result is not None else []
    if states == ['active'] * len(SERVICES):
        return 'active'
    if 'failed' in states and all(s in ('active', 'failed') for s in states):
        return 'failed'
    return 'other'


def probe():
    runtime = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    result = run('pactl', 'info', timeout=PROBE_TIMEOUT, env={'PULSE_SERVER': f'unix:{runtime}/pulse/native'})
    return result is not None and result.returncode == 0


def restart_stack():
    # A wedged WirePlumber ignores SIGTERM until systemd's stop timeout, so kill first.
    run('systemctl', '--user', 'kill', '--signal=SIGKILL', *SERVICES)
    run('systemctl', '--user', 'reset-failed', *SERVICES)
    result = run('systemctl', '--user', 'restart', *SERVICES, timeout=30)
    return result is not None and result.returncode == 0


def notify(headline, body):
    try:
        subprocess.Popen(['notify-send', '-a', 'Audio', '-i', 'audio-volume-muted-symbolic', headline, body],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def main():
    if not apple_silicon():
        return 0
    restarts = []
    failures = healthy = 0
    stuck = False
    next_probe = 0.0
    settle_until = time.monotonic() + SETTLE
    last_offset = time.clock_gettime(time.CLOCK_BOOTTIME) - time.monotonic()
    while True:
        offset = time.clock_gettime(time.CLOCK_BOOTTIME) - time.monotonic()
        resumed = offset - last_offset > RESUME_JUMP     # CLOCK_MONOTONIC stops in suspend
        last_offset = offset
        now = time.monotonic()
        if resumed or not session_ok() or units_state() == 'other':
            failures = 0
            settle_until = now + SETTLE
        elif now >= settle_until and now >= next_probe:
            if probe():
                failures = 0
                healthy += 1
                if healthy >= HEALTHY_PROBES:
                    stuck = False
                next_probe = now + PROBE_INTERVAL
            else:
                healthy = 0
                failures += 1
                next_probe = now + TICK
                if failures >= 2 and not stuck:
                    ok, why = allowed(restarts, time.clock_gettime(time.CLOCK_BOOTTIME))
                    if ok:
                        print('Restarting the audio stack: the audio server stopped responding', file=sys.stderr, flush=True)
                        restarts.append(time.clock_gettime(time.CLOCK_BOOTTIME))
                        done = restart_stack()
                        failures = 0
                        settle_until = time.monotonic() + SETTLE
                        if done:
                            notify('Audio restarted', 'Sound stopped responding and was restarted')
                    elif 'already restarted' in why:
                        stuck = True
                        notify('Audio is not responding', 'Restart it with: systemctl --user restart pipewire pipewire-pulse wireplumber')
        time.sleep(TICK)


if __name__ == '__main__':
    raise SystemExit(main())
