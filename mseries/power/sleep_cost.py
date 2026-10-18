#!/usr/bin/python3
# SPDX-License-Identifier: MIT
# Adapted from omacom/omarchy-mac-pkgs b5e10d3d; see UPSTREAM.md and LICENSE.omacom.
# The battery energy each suspend costs. systemd-sleep runs `sleep-cost pre|post
# <action>` around every sleep; `last` prints the newest record; `watch` (a user
# unit) shows what a sleep used once the screen is unlocked after it.

import os
import math
import platform
import json
from pathlib import Path
import subprocess
import sys
import time

LOG = Path(os.environ.get('MSERIES_SLEEP_LOG', '/var/lib/mseries/sleep-cost.log'))
PENDING = Path(os.environ.get('MSERIES_SLEEP_PENDING', '/run/mseries/sleep-cost.pending'))
POWER_SUPPLY = Path(os.environ.get('MSERIES_POWER_SUPPLY_PATH', '/sys/class/power_supply'))
PROC = Path(os.environ.get('MSERIES_PROC_ROOT') or '/proc')
KEEP = 200
# A clock step or a boot clock that missed the sleep shows as the two clocks
# disagreeing; such an interval is not counted.
CLOCK_TOLERANCE = (60.0, 0.01)
# Shorter sleeps are recorded but not announced: the battery's energy reading
# is too coarse to say much about them.
NOTICE_MINIMUM = 1800.0
# A resume whose record is older than this wrote none of its own.
RECENT = 600.0
# How long a lock state nobody can read holds the notice back.
UNKNOWN_LIMIT = 120.0
BODY = 'Measured across suspend, including transition overhead; not proof of sleep residency.'
SLEEP_EVENTS = ('dbus-monitor', '--system',
                "type='signal',sender='org.freedesktop.login1',"
                "interface='org.freedesktop.login1.Manager',member='PrepareForSleep'")
REASONS = {
    'no-sleep': 'no suspended clock interval was observed (possibly a failed suspend)',
    'missing-reading': 'a battery or clock reading was missing',
    'charging': 'the battery was charging',
    'charger-connected': 'a charger was connected',
    'energy-rose': 'the battery gained energy',
    'clocks-disagree': 'the wall clock and the boot clock disagree',
}


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def number(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def supplies():
    try:
        return sorted(POWER_SUPPLY.iterdir())
    except OSError:
        return []


def battery():
    # The first present battery that reports energy (macsmc-battery on a Mac).
    for supply in supplies():
        if read(supply / 'type') == 'Battery' and read(supply / 'present') != '0' and (supply / 'energy_now').exists():
            return supply
    return None


def charger_online():
    # Mains is the SMC's own adapter input; USB covers each USB-C port's source.
    online = None
    for supply in supplies():
        if read(supply / 'type') in ('Mains', 'USB'):
            state = read(supply / 'online')
            if state == '1':
                return 1
            if state == '0':
                online = 0
    return online


class System:
    def clocks(self):
        return time.clock_gettime(time.CLOCK_REALTIME), time.clock_gettime(time.CLOCK_BOOTTIME)

    def boot_id(self):
        return read(PROC / 'sys/kernel/random/boot_id') or 'unknown'

    def awake_clock(self):
        return time.monotonic()

    def sleep(self, seconds):
        time.sleep(seconds)

    def lock_state(self):
        # User services have no XDG_SESSION_ID: use this user's graphical session.
        try:
            session = os.environ.get('XDG_SESSION_ID')
            if not session:
                result = subprocess.run(['loginctl', 'show-user', str(os.getuid()), '-p', 'Display', '--value'],
                                        capture_output=True, text=True, timeout=5)
                session = result.stdout.strip() if result.returncode == 0 else ''
            if not session:
                return 'unknown'
            result = subprocess.run(['loginctl', 'show-session', session, '-p', 'Active', '-p', 'LockedHint'],
                                    capture_output=True, text=True, timeout=5)
            props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            if result.returncode != 0 or props.get('Active') != 'yes':
                return 'unknown'
            return {'yes': 'locked', 'no': 'unlocked'}.get(props.get('LockedHint'), 'unknown')
        except (OSError, subprocess.SubprocessError):
            return 'unknown'

    def notify(self, headline, body):
        try:
            return subprocess.run(['notify-send', '--app-name=M-series Power', '--icon=battery',
                                   '--urgency=normal', headline, body], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def sleep_events(self):
        # True as logind starts a sleep, False once the machine has resumed.
        with subprocess.Popen(SLEEP_EVENTS, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True) as monitor:
            for line in monitor.stdout:
                if 'boolean true' in line:
                    yield True
                elif 'boolean false' in line:
                    yield False


def snapshot(system, prefix):
    real, boot = system.clocks()
    supply = battery()
    status = read(supply / 'status') if supply else None
    charger = charger_online()
    fields = {
        prefix + '_awake': '%.3f' % system.awake_clock(),
        prefix + '_real': '%.3f' % real,
        prefix + '_boot': '%.3f' % boot,
        prefix + '_energy': read(supply / 'energy_now') if supply else None,
        prefix + '_status': status.replace(' ', '-') if status else None,
        prefix + '_charger': None if charger is None else str(charger),
    }
    if supply and prefix == 'end':
        fields['energy_full'] = read(supply / 'energy_full')
    return {key: value for key, value in fields.items() if value}


def parse(line):
    record = {}
    for field in line.split():
        key, separator, value = field.partition('=')
        if separator:
            record[key] = value
    return record


def judge(record):
    try:
        start_real, end_real = float(record['start_real']), float(record['end_real'])
        start_boot, end_boot = float(record['start_boot']), float(record['end_boot'])
    except (KeyError, ValueError):
        return 'missing-reading'
    if not all(math.isfinite(x) for x in (start_real, end_real, start_boot, end_boot)):
        return 'missing-reading'
    start_energy, end_energy = number(record.get('start_energy')), number(record.get('end_energy'))
    if (start_energy is None or end_energy is None or min(start_energy, end_energy) < 0
            or record.get('start_boot_id') in (None, 'unknown')
            or record.get('start_boot_id') != record.get('boot_id')):
        return 'missing-reading'
    if 'Charging' in (record.get('start_status'), record.get('end_status')):
        return 'charging'
    if '1' in (record.get('start_charger'), record.get('end_charger')):
        return 'charger-connected'
    if record.get('start_charger') != '0' or record.get('end_charger') != '0':
        return 'missing-reading'
    if record.get('start_status') != 'Discharging' or record.get('end_status') != 'Discharging':
        return 'missing-reading'
    if end_energy > start_energy:
        return 'energy-rose'
    if record.get('action') not in ('suspend', 'hybrid-sleep', 'suspend-then-hibernate', 'hibernate'):
        return 'missing-reading'
    asleep, wall = end_boot - start_boot, end_real - start_real
    if asleep <= 0 or wall <= 0 or abs(asleep - wall) > max(CLOCK_TOLERANCE[0], CLOCK_TOLERANCE[1] * wall):
        return 'clocks-disagree'
    try:
        awake = float(record['end_awake']) - float(record['start_awake'])
    except (KeyError, ValueError):
        return 'missing-reading'
    if not math.isfinite(awake) or awake < 0 or asleep - awake < 1:
        return 'no-sleep'
    return 'valid'


def record_pre(system, action):
    fields = dict(start_boot_id=system.boot_id(), action=action, **snapshot(system, 'start'))
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(' '.join('%s=%s' % item for item in fields.items()) + '\n')


def record_post(system, action):
    record = parse(read(PENDING) or '')
    record.update(boot_id=system.boot_id(), action=record.get('action', action), **snapshot(system, 'end'))
    record['verdict'] = judge(record)
    lines = (read(LOG) or '').splitlines()[-(KEEP - 1):]
    lines.append(' '.join('%s=%s' % item for item in record.items()))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    temporary = LOG.with_name(LOG.name + '.new')
    temporary.write_text('\n'.join(lines) + '\n')
    temporary.chmod(0o644)
    temporary.replace(LOG)
    PENDING.unlink(missing_ok=True)


def records():
    return [parse(line) for line in (read(LOG) or '').splitlines()[-KEEP:]]


def last_record():
    found = records()
    return found[-1] if found else None


def used(record):
    # (watt-hours used, hours asleep) of a valid record.
    energy = (int(record['start_energy']) - int(record['end_energy'])) / 1e6
    return energy, (float(record['end_boot']) - float(record['start_boot'])) / 3600


def describe(record):
    if record is None:
        return 'No suspend recorded yet.'
    def stamp(key):
        try:
            return time.strftime('%Y-%m-%d %H:%M', time.localtime(float(record[key])))
        except (KeyError, ValueError, OverflowError, OSError):
            return '?'
    span = '%s to %s' % (stamp('start_real'), stamp('end_real'))
    verdict = judge(record)
    if verdict != 'valid':
        return '%s: not counted, because %s.' % (span, REASONS.get(verdict, verdict))
    energy, hours = used(record)
    text = '%s: used %.1f Wh over %.1f h (%.2f W average)' % (span, energy, hours, energy / hours)
    full = number(record.get('energy_full'))
    if full:
        text += ', %.0f%% of a full battery' % (100 * energy * 1e6 / full)
    return text + '.'


def unannounced(system, since, shown):
    # Counted sleeps of this boot that ended after `since` on the boot clock.
    return [record for record in records()
            if judge(record) == 'valid' and record.get('boot_id') == system.boot_id()
            and float(record['end_boot']) >= since and record['end_real'] not in shown]


def notice(found):
    # Every sleep since the last unlock counts, so a short one before the
    # unlock cannot hide the night before it.
    energy = sum(used(record)[0] for record in found)
    hours = sum(used(record)[1] for record in found)
    if hours * 3600 < NOTICE_MINIMUM:
        return None
    return 'Suspend used %.1f Wh over %.1f h.' % (energy, hours)


def after_resume(system, shown):
    # logind reports the resume once systemd-sleep, and so the record, is done.
    since = system.clocks()[1] - RECENT
    if not unannounced(system, since, shown):
        return
    unknown = 0.0
    while True:
        state = system.lock_state()
        if state == 'unlocked':
            break
        if state == 'unknown' and unknown >= UNKNOWN_LIMIT:
            return  # Never expose a notification when lock state is unknown.
        unknown = unknown + 5 if state == 'unknown' else 0.0
        system.sleep(5)
    found = unannounced(system, since, shown)
    headline = notice(found)
    if headline is not None:
        system.sleep(2)
        for attempt in range(3):
            if system.notify(headline, BODY):
                break
            if attempt == 2:
                # Undelivered: the next resume tries these sleeps again.
                return
            system.sleep(10)
    shown.update(record['end_real'] for record in found)


def watch(system):
    # Runtime state survives a user-service restart, but never another boot.
    state = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'mseries-sleep-shown.json'
    try:
        saved = json.loads(state.read_text())
        shown = set(saved) if isinstance(saved, list) and all(isinstance(x, str) for x in saved) else set()
    except (OSError, ValueError, TypeError):
        shown = set()
    def save():
        temporary = state.with_suffix('.new')
        temporary.write_text(json.dumps(sorted(shown)[-KEEP:]))
        temporary.replace(state)
    after_resume(system, shown)
    save()
    for starting in system.sleep_events():
        if not starting:
            after_resume(system, shown)
            save()


def apple_silicon():
    try:
        return platform.machine() == 'aarch64' and b'apple,' in Path('/proc/device-tree/compatible').read_bytes().lower()
    except OSError:
        return False


def main(arguments, system=None):
    if system is None:
        if not apple_silicon():
            return 0
        system = System()
    command = arguments[0] if arguments else ''
    if command in ('pre', 'post') and len(arguments) == 2:
        # Never hold up or fail a sleep over a reading.
        try:
            (record_pre if command == 'pre' else record_post)(system, arguments[1])
        except Exception as error:
            print('sleep-cost %s: %s' % (command, error), file=sys.stderr)
    elif command == 'last' and len(arguments) == 1:
        print(describe(last_record()))
    elif command == 'watch' and len(arguments) == 1:
        watch(system)
        print('The sleep event monitor stopped', file=sys.stderr)
        return 1
    else:
        print('Usage: sleep-cost pre|post <action> | last | watch', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
