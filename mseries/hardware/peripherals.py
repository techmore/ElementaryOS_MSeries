#!/usr/bin/python3 -I
"""Apple and Logitech keyboards, trackpads and mice: Bluetooth state, charge, plug-in handling.

  status [--json]      every input accessory with link, trust and the best battery reading
  pair [ADDRESS]       pair, trust and connect; without ADDRESS, the one nearby unpaired match
  watch                user service: plug-in prompts, reconnect on unplug, low-battery notices

Pairing needs a person (a rogue keyboard in range would otherwise be trusted), so the
watcher only offers it. Everything else it does touches devices that are already paired.
"""
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import threading
import time

SYS_POWER = Path('/sys/class/power_supply')
SYS_USB = Path('/sys/bus/usb/devices')
LOW_PERCENT = 15
RECOVERED_PERCENT = 30
SETTLE_SECONDS = 2
HEARTBEAT_SECONDS = 300
SCAN_SECONDS = 12

USB_VENDORS = {'05ac': 'apple', '046d': 'logitech'}
MAC = re.compile(r'([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})')
LEVELS = {'critical': 'critical', 'low': 'low', 'normal': 'normal', 'high': 'high', 'full': 'full'}
ICONS = {'keyboard': 'input-keyboard', 'trackpad': 'input-touchpad', 'mouse': 'input-mouse'}


def run(command, timeout=20):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, 124, '', str(exc))


def kind_of(name, icon=''):
    lowered = name.lower()
    if 'trackpad' in lowered or 'touchpad' in lowered:
        return 'trackpad'
    if 'keyboard' in lowered:
        return 'keyboard'
    if 'mouse' in lowered:
        return 'mouse'
    return {'input-keyboard': 'keyboard', 'input-mouse': 'mouse'}.get(icon, 'other')


def vendor_of(name, modalias=''):
    lowered = name.lower()
    if lowered.startswith('magic ') or re.match(r'(usb|bluetooth):v(004c|05ac)', modalias.lower()):
        return 'apple'
    if re.match(r'usb:v046d', modalias.lower()) or lowered.startswith('mx ') or 'logitech' in lowered:
        return 'logitech'
    return 'other'


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ''


def bluez_devices():
    """Input devices BlueZ knows, from one ObjectManager call."""
    done = run(['busctl', '--system', '--json=short', 'call', 'org.bluez', '/',
                'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects'])
    try:
        objects = json.loads(done.stdout)['data'][0]
    except (ValueError, KeyError, IndexError):
        return []
    found = []
    for path, interfaces in objects.items():
        raw = interfaces.get('org.bluez.Device1')
        if not raw:
            continue
        props = {key: value['data'] for key, value in raw.items()}
        uuids = props.get('UUIDs', [])
        hid = props.get('Icon', '').startswith('input-') or any(
            u.startswith(('00001812', '00001124')) for u in uuids)
        if not hid:
            continue
        battery = interfaces.get('org.bluez.Battery1', {}).get('Percentage', {}).get('data')
        name = props.get('Alias') or props.get('Name') or props['Address']
        found.append(dict(
            address=props['Address'].upper(), name=name, icon=props.get('Icon', ''),
            modalias=props.get('Modalias', ''), paired=bool(props.get('Paired')),
            trusted=bool(props.get('Trusted')), connected=bool(props.get('Connected')),
            rssi=props.get('RSSI'), percent=battery, path=path))
    return found


def kernel_supplies():
    """HID battery supplies: exact percent when the driver has it, a level when not."""
    found = []
    try:
        entries = sorted(SYS_POWER.iterdir())
    except OSError:
        return found
    for entry in entries:
        if read(entry / 'scope') != 'Device':
            continue
        real = os.path.realpath(entry)
        text = entry.name + ' ' + read(entry / 'serial_number')
        mac = MAC.search(text)
        percent = read(entry / 'capacity')
        found.append(dict(
            name=entry.name, real=real, address=mac.group(1).upper() if mac else None,
            transport='usb' if '/0003:' in real else 'bluetooth' if '/0005:' in real else 'unknown',
            model=read(entry / 'model_name'), status=read(entry / 'status'),
            percent=int(percent) if percent.isdigit() else None,
            level=LEVELS.get(read(entry / 'capacity_level').lower())))
    return found


def usb_accessories():
    """Plugged-in Apple/Logitech keyboards, trackpads and mice."""
    found = []
    try:
        entries = sorted(SYS_USB.iterdir())
    except OSError:
        return found
    for entry in entries:
        vendor = USB_VENDORS.get(read(entry / 'idVendor'))
        product = read(entry / 'product')
        if not vendor or not product or 'internal' in product.lower():
            continue
        kind = kind_of(product)
        if kind == 'other':
            continue
        found.append(dict(name=product, kind=kind, vendor=vendor, real=os.path.realpath(entry),
                          key='usb:%s:%s:%s' % (read(entry / 'idVendor'), read(entry / 'idProduct'),
                                                entry.name)))
    return found


def best_battery(readings):
    """Exact percent beats a level; the cable's own supply beats BlueZ's copy."""
    ordered = sorted(readings, key=lambda r: r['rank'])
    exact = next((r for r in ordered if r['percent'] is not None), None)
    level = next((r for r in ordered if r.get('level')), None)
    status = next((r['status'] for r in ordered if r.get('status')), '')
    charging = {'Charging': True, 'Discharging': False, 'Full': False, 'Not charging': False}.get(status)
    if not exact and not level:
        return dict(percent=None, level=None, charging=charging, source=None)
    return dict(percent=exact['percent'] if exact else None,
                level=level['level'] if level else None,
                charging=charging, source=(exact or level)['source'])


def collect():
    return merge(bluez_devices(), kernel_supplies(), usb_accessories())


def merge(bluez, supplies, usb):
    devices = []
    by_address = {}
    for item in bluez:
        entry = dict(key=item['address'], name=item['name'], address=item['address'],
                     kind=kind_of(item['name'], item['icon']),
                     vendor=vendor_of(item['name'], item['modalias']),
                     paired=item['paired'], trusted=item['trusted'], connected=item['connected'],
                     rssi=item['rssi'], wired=False, ambiguous=False, readings=[])
        if item['percent'] is not None:
            entry['readings'].append(dict(rank=2, percent=item['percent'], level=None,
                                          status='', source='bluetooth'))
        devices.append(entry)
        by_address[item['address']] = entry
    unmatched = []
    for supply in supplies:
        reading = dict(rank=1 if supply['transport'] == 'bluetooth' else 0, percent=supply['percent'],
                       level=supply['level'], status=supply['status'], source='kernel')
        if supply['address'] in by_address:
            by_address[supply['address']]['readings'].append(reading)
        else:
            unmatched.append((supply, reading))
    for accessory in usb:
        paired = [d for d in devices if d['paired'] and d['vendor'] == accessory['vendor']
                  and d['kind'] == accessory['kind']]
        if len(paired) == 1:
            target = paired[0]
        else:
            target = dict(key=accessory['key'], name=accessory['name'], address=None,
                          kind=accessory['kind'], vendor=accessory['vendor'], paired=False,
                          trusted=False, connected=False, rssi=None, wired=True,
                          ambiguous=len(paired) > 1, readings=[])
            devices.append(target)
        target['wired'] = True
        for supply, reading in unmatched:
            if supply['real'].startswith(accessory['real'] + '/'):
                target['readings'].append(reading)
    for entry in devices:
        entry['battery'] = best_battery(entry.pop('readings'))
    return devices


def describe(entry):
    link = 'USB + Bluetooth' if entry['wired'] and entry['paired'] else 'USB' if entry['wired'] \
        else 'Bluetooth'
    if entry['wired']:
        state = 'plugged in'
    elif entry['connected']:
        state = 'connected'
    elif entry['paired']:
        state = 'paired, not connected'
    else:
        state = 'not paired'
    battery = entry['battery']
    if battery['percent'] is not None:
        charge = '%d%%' % battery['percent']
    elif battery['level']:
        charge = battery['level']
    else:
        charge = 'unknown'
    if battery['charging']:
        charge += ' charging'
    return link, state, charge


def status(arguments):
    devices = collect()
    if '--json' in arguments:
        print(json.dumps(devices, indent=2))
        return 0
    if not devices:
        print('No Apple or Logitech input accessories found.')
        return 0
    for entry in devices:
        link, state, charge = describe(entry)
        trust = '' if entry['trusted'] or not entry['paired'] else ', not trusted'
        print('%-26s %-9s %-16s %s%s, %s' % (entry['name'], entry['kind'], link, state, trust, charge))
    return 0


def pair_one(address, replace=False):
    if replace:
        run(['bluetoothctl', 'remove', address])
    done = run(['bluetoothctl', 'pair', address], timeout=45)
    text = done.stdout + done.stderr
    if 'Pairing successful' not in text and 'AlreadyExists' not in text and 'Paired: yes' not in text:
        return False, text.strip().splitlines()[-1] if text.strip() else 'pairing did not finish'
    run(['bluetoothctl', 'trust', address])
    run(['bluetoothctl', 'connect', address], timeout=30)
    return True, ''


def candidates(kind=None, vendor=None):
    run(['bluetoothctl', '--timeout', str(SCAN_SECONDS), 'scan', 'on'], timeout=SCAN_SECONDS + 10)
    found = []
    for item in bluez_devices():
        # An advertisement seen just now carries RSSI; BlueZ's cache of old sightings does not.
        if item['paired'] or item['rssi'] is None:
            continue
        item_kind = kind_of(item['name'], item['icon'])
        item_vendor = vendor_of(item['name'], item['modalias'])
        if item_vendor == 'other' or item_kind == 'other':
            continue
        if (kind and item_kind != kind) or (vendor and item_vendor != vendor):
            continue
        found.append(item)
    return found


def pair(arguments, kind=None, vendor=None):
    replace = '--replace' in arguments
    addresses = [a for a in arguments if MAC.fullmatch(a)]
    if addresses:
        address = addresses[0].upper()
    else:
        found = candidates(kind, vendor)
        if not found:
            print('No unpaired Apple or Logitech accessory in range. Turn it on (Apple: slide the '
                  'switch off and on) and try again.', file=sys.stderr)
            return 1
        if len(found) > 1:
            print('More than one candidate; pick one:', file=sys.stderr)
            for item in found:
                print('  %s  %s  RSSI %s' % (item['address'], item['name'], item['rssi']), file=sys.stderr)
            return 1
        address = found[0]['address']
    ok, problem = pair_one(address, replace)
    print('Paired and connected %s.' % address if ok else 'Could not pair %s: %s' % (address, problem),
          file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def plan(state, devices):
    """New state and the actions a snapshot calls for; no I/O so tests can drive it."""
    wired = set()
    low = set(state.get('low', []))
    actions = []
    for entry in devices:
        key = entry['key']
        battery = entry['battery']
        percent = battery['percent']
        label = '%s %d%%' % (entry['name'], percent) if percent is not None else entry['name']
        if entry['wired']:
            wired.add(key)
            if key not in state.get('wired', []):
                if entry['address'] and not entry['trusted']:
                    actions.append(('trust', entry['address']))
                if entry['address'] or entry['ambiguous']:
                    actions.append(('notify', '%s is plugged in' % entry['name'],
                                    'Charging.' if battery['charging'] else label,
                                    entry['kind'], None))
                else:
                    actions.append(('notify', '%s is plugged in' % entry['name'],
                                    'Pair it to use it wirelessly.', entry['kind'],
                                    (entry['kind'], entry['vendor'])))
        elif key in state.get('wired', []) and entry['paired'] and not entry['connected']:
            actions.append(('connect', entry['address']))
        if percent is not None and not battery['charging'] and percent <= LOW_PERCENT \
                and key not in low and (entry['connected'] or entry['wired']):
            low.add(key)
            actions.append(('notify', '%s battery is low' % entry['name'],
                            '%d%% left. Plug it in to charge.' % percent, 'battery-caution', None))
        elif key in low and (battery['charging'] or (percent is not None and percent >= RECOVERED_PERCENT)):
            low.discard(key)
    return dict(wired=sorted(wired), low=sorted(low)), actions


def state_file():
    base = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
    return base / 'mseries' / 'peripherals.json'


def load_state():
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}


def save_state(state):
    path = state_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state))
    except OSError:
        pass


def notify(title, body, icon, offer=None):
    command = ['notify-send', '-a', 'Peripherals', '-i', ICONS.get(icon, icon), '-t', '20000']
    if offer:
        command += ['--action=pair=Pair']
    command += [title, body]

    def show():
        done = run(command, timeout=60)
        if offer and done.stdout.strip() == 'pair':
            kind, vendor = offer
            outcome = pair([], kind, vendor)
            notify('Pairing finished' if outcome == 0 else 'Pairing failed',
                   'Run mseries-peripherals status to check.' if outcome == 0
                   else 'Run mseries-peripherals pair for details.', 'preferences-system-bluetooth')
    threading.Thread(target=show, daemon=True).start()


def apply(actions):
    for action in actions:
        if action[0] == 'notify':
            notify(action[1], action[2], action[3], action[4])
        elif action[0] == 'trust':
            run(['bluetoothctl', 'trust', action[1]])
        elif action[0] == 'connect':
            run(['bluetoothctl', 'connect', action[1]], timeout=30)


def watch():
    state = load_state()
    # What is already plugged in at login is not news; only changes after it prompt.
    first = collect()
    state, actions = plan(dict(state, wired=[d['key'] for d in first if d['wired']]), first)
    save_state(state)
    apply(actions)
    monitor = subprocess.Popen(['stdbuf', '-oL', 'udevadm', 'monitor', '--udev', '--subsystem-match=usb',
                                '--subsystem-match=hid'], stdout=subprocess.PIPE, text=True, bufsize=1)
    while True:
        ready, _, _ = select.select([monitor.stdout], [], [], HEARTBEAT_SECONDS)
        if ready:
            if not monitor.stdout.readline():
                return 1
            # One plug-in is a burst of events; let it finish, then drain it.
            time.sleep(SETTLE_SECONDS)
            while select.select([monitor.stdout], [], [], 0)[0]:
                if not monitor.stdout.readline():
                    return 1
        state, actions = plan(state, collect())
        save_state(state)
        apply(actions)


def main(argv):
    command = argv[1] if len(argv) > 1 else 'status'
    if command == 'status':
        return status(argv[2:])
    if command == 'pair':
        return pair(argv[2:])
    if command == 'watch':
        return watch()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
