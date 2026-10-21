#!/usr/bin/env python3
"""Drive the nested compositor's probe socket and assert snap placements.

Usage: check-snap.py PROBE_SOCKET OUT_DIR FIXTURE
Every step reads the compositor's own `snap probe` log line, so results are
what the compositor laid out after the GTK client acked and committed.
"""
import json
import os
import re
import socket
import subprocess
import sys
import time

PROBE, OUT, FIXTURE = sys.argv[1], sys.argv[2], sys.argv[3]
LOG = f'{OUT}/compositor.log'
ANSI = re.compile(r'\x1b\[[0-9;]*m')
LINE = re.compile(
    r'snap probe placement=(?P<placement>\S+) x=(?P<x>-?\d+) y=(?P<y>-?\d+) '
    r'w=(?P<w>\d+) h=(?P<h>\d+) pending=(?P<pending>\w+) group=(?P<group>\S+) states=(?P<states>\S+) '
    r'area=(?P<area>[-\d,]+) preview=(?P<preview>\w+)')
sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
receipts = []
failures = []


def send(command):
    sock.sendto(command.encode(), PROBE)


def read_placement(wait=1.0):
    """The focused window's placement, or None while no window is focused."""
    with open(LOG, errors='replace') as log:
        start = len(log.read())
    send('placement')
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        with open(LOG, errors='replace') as log:
            log.seek(start)
            for line in log.read().splitlines():
                match = LINE.search(ANSI.sub('', line))
                if match:
                    found = match.groupdict()
                    for key in 'xywh':
                        found[key] = int(found[key])
                    found['rect'] = (found['x'], found['y'], found['w'], found['h'])
                    found['area'] = tuple(int(v) for v in found['area'].split(','))
                    found['pending'] = found['pending'] == 'true'
                    found['preview'] = found['preview'] == 'true'
                    found['states'] = set() if found['states'] == '-' else set(found['states'].split('+'))
                    found['group'] = None if found['group'] == '-' else found['group']
                    return found
        time.sleep(0.05)
    return None


ASSIST = re.compile(r'snap probe assist (?P<body>open=.*)$')


def read_assist():
    with open(LOG, errors='replace') as log:
        start = len(log.read())
    send('assist-status')
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        with open(LOG, errors='replace') as log:
            log.seek(start)
            for line in log.read().splitlines():
                match = ASSIST.search(ANSI.sub('', line))
                if match:
                    fields = dict(item.split('=', 1) for item in match['body'].split())
                    fields['open'] = fields['open'] == 'true'
                    if fields['open']:
                        fields['candidates'] = int(fields['candidates'])
                        fields['selected'] = int(fields['selected'])
                        fields['cells'] = [tuple(int(v) for v in cell.split(','))
                                           for cell in fields['cells'].split(';')]
                    return fields
        time.sleep(0.05)
    raise SystemExit('no assist status line')


def screenshot(name):
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'x11grab', '-video_size',
                    '1280x800', '-i', os.environ['DISPLAY'], '-frames:v', '1', '-update', '1',
                    '-y', f'{OUT}/{name}.png'], check=False)


def settle(predicate, timeout=3.0):
    """Wait until the client acked and the compositor settled the placement."""
    deadline = time.monotonic() + timeout
    while True:
        state = read_placement()
        if state and not state['pending'] and predicate(state):
            return state
        if time.monotonic() > deadline:
            if state is None:
                raise SystemExit('no focused window: the fixture did not map')
            return state
        time.sleep(0.1)


def check(name, state, condition, detail=''):
    receipts.append({'step': name, 'ok': bool(condition), 'placement': state['placement'],
                     'rect': state['rect'], 'states': sorted(state['states']), 'detail': detail})
    print(('PASS' if condition else 'FAIL'), name, state['placement'], state['rect'], detail)
    if not condition:
        failures.append(name)


def halves(area):
    x, y, w, h = area
    return (x, y, w // 2, h), (x + w // 2, y, w - w // 2, h)


def start_fixture(*args, script=FIXTURE, env=None):
    process = subprocess.Popen(['python3', script, *map(str, args)], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    settle(lambda state: state['w'] > 0, timeout=8)
    time.sleep(0.5)
    return process


def drag(points, step_delay=0.02):
    send(f'press {points[0][0]} {points[0][1]}')
    for x, y in points[1:]:
        send(f'motion {x} {y}')
        time.sleep(step_delay)


def path(start, end, steps=12):
    return [(round(start[0] + (end[0] - start[0]) * i / steps),
             round(start[1] + (end[1] - start[1]) * i / steps)) for i in range(steps + 1)]


# --- A. Plain window: keyboard snapping, maximize interplay, drag-out. ---
fixture = start_fixture()
floating = settle(lambda state: state['placement'] == 'floating')
F = floating['rect']
area = floating['area']
left, right = halves(area)
check('fixture floats', floating, floating['placement'] == 'floating' and F[2] > 0)

send('snap left')
state = settle(lambda s: s['rect'] == left)
check('Super+Left tiles the left half', state, state['placement'] == 'tiled-left' and state['rect'] == left)
check('S8 tiled states on work-area edges only', state,
      {'TiledLeft', 'TiledTop', 'TiledBottom'} <= state['states'] and 'TiledRight' not in state['states'],
      ' '.join(sorted(state['states'])))

send('snap left')
state = settle(lambda s: s['rect'] == F)
check('Super+Left again restores the pre-snap rect (S1 toggle)', state,
      state['placement'] == 'floating' and state['rect'] == F and not state['states'])

send('snap right')
state = settle(lambda s: s['rect'] == right)
check('Super+Right tiles the right half', state, state['placement'] == 'tiled-right' and state['rect'] == right)

send('snap up')
state = settle(lambda s: s['rect'] == area)
check('Super+Up maximizes and remembers the tile', state,
      state['placement'] == 'maximized(tiled-right)' and state['rect'] == area and 'Maximized' in state['states'])

send('snap down')
state = settle(lambda s: s['rect'] == right)
check('Super+Down returns to the tile (S2)', state, state['placement'] == 'tiled-right' and state['rect'] == right)

send('snap down')
state = settle(lambda s: s['rect'] == F)
check('Super+Down again restores the floating rect', state, state['placement'] == 'floating' and state['rect'] == F)

send('mode maximize')
state = settle(lambda s: s['rect'] == area)
check('client maximize from floating', state, state['placement'] == 'maximized(floating)' and state['rect'] == area)
send('mode unmaximize')
state = settle(lambda s: s['rect'] == F)
check('client unmaximize restores the floating rect', state, state['placement'] == 'floating' and state['rect'] == F)

send('snap left')
state = settle(lambda s: s['rect'] == left)
grab = (left[0] + left[2] // 4, left[1] + 12)
drag([grab, (grab[0] + 4, grab[1] + 3)])
time.sleep(0.2)
state = settle(lambda s: True)
check('a click-sized drag leaves the tile alone', state, state['placement'] == 'tiled-left' and state['rect'] == left)
drop = (grab[0] + 220, grab[1] + 180)
steps = path((grab[0] + 4, grab[1] + 3), drop)[1:]
# The window detaches at the first motion 8 px from the press.
detach = next(p for p in steps if ((p[0] - grab[0]) ** 2 + (p[1] - grab[1]) ** 2) ** 0.5 >= 8)
want_fraction = (detach[0] - left[0]) / left[2]
want_below = detach[1] - left[1]
for point in steps:
    send(f'motion {point[0]} {point[1]}')
    time.sleep(0.02)
state = settle(lambda s: (s['w'], s['h']) == (F[2], F[3]))
fraction = (drop[0] - state['x']) / state['w']
check('drag-out restores the floating size (S1)', state,
      state['placement'] == 'floating' and (state['w'], state['h']) == (F[2], F[3]))
check('drag-out keeps the grab point under the pointer', state,
      abs(fraction - want_fraction) < 0.01 and abs(drop[1] - state['y'] - want_below) <= 1,
      f'fraction={fraction:.3f} want={want_fraction:.3f} below={drop[1] - state["y"]} want={want_below}')
send('release')
time.sleep(0.3)
dropped = settle(lambda s: True)
check('release without a zone stays floating where dropped', dropped,
      dropped['placement'] == 'floating' and dropped['rect'] == state['rect'])

start = (dropped['x'] + 60, dropped['y'] + 12)
edge = (area[0] + area[2] - 3, area[1] + area[3] // 2)
drag(path(start, edge))
time.sleep(0.2)
state = settle(lambda s: True)
check('dragging to the right edge shows a preview', state, state['preview'])
send('release')
state = settle(lambda s: s['rect'] == right)
check('release at the edge snaps right (S6 rect recomputed)', state,
      state['placement'] == 'tiled-right' and state['rect'] == right)
send('snap down')
state = settle(lambda s: s['placement'] == 'floating' and (s['w'], s['h']) == (F[2], F[3]))
check('Super+Down after a drag-snap restores the dropped floating rect', state,
      state['placement'] == 'floating' and state['rect'] == dropped['rect'])
fixture.terminate()
fixture.wait()
time.sleep(0.5)

# --- B. Minimum width larger than a half (S5). ---
min_width = area[2] // 2 + 160
fixture = start_fixture(min_width)
send('snap right')
state = settle(lambda s: s['placement'] == 'tiled-right' and s['x'] + s['w'] == area[0] + area[2])
check('S5 oversized right tile grows inward, not off-screen', state,
      state['placement'] == 'tiled-right' and state['w'] >= min_width
      and state['x'] + state['w'] == area[0] + area[2] and state['x'] >= area[0],
      f'min_width={min_width}')
send('snap left')
state = settle(lambda s: s['placement'] == 'floating')
check('Super+Left on a right tile restores it', state, state['placement'] == 'floating')
send('snap left')
state = settle(lambda s: s['placement'] == 'tiled-left' and s['x'] == area[0])
check('S5 oversized left tile stays anchored left', state,
      state['placement'] == 'tiled-left' and state['x'] == area[0] and state['w'] >= min_width)
fixture.terminate()
fixture.wait()
time.sleep(0.5)

# --- C. X11 window on XWayland: snapping and a client that resizes itself (S7). ---
with open(LOG, errors='replace') as log:
    ready = re.findall(r'XWayland is ready display_number=(\d+)', ANSI.sub('', log.read()))
if ready:
    env = dict(os.environ, GDK_BACKEND='x11', DISPLAY=f':{ready[-1]}')
    env.pop('WAYLAND_DISPLAY', None)
    fixture = start_fixture(script=FIXTURE.replace('fixture.py', 'fixture-x11.py'), env=env)
    x11_floating = settle(lambda s: s['placement'] == 'floating' and s['w'] > 0)
    send('snap right')
    state = settle(lambda s: s['rect'] == right)
    check('X11 Super+Right tiles the right half', state,
          state['placement'] == 'tiled-right' and state['rect'] == right)
    fixture.send_signal(__import__('signal').SIGUSR1)
    time.sleep(0.8)
    state = settle(lambda s: True)
    check('S7 X11 self-resize is answered with the tile rect', state,
          state['placement'] == 'tiled-right' and state['rect'] == right)
    send('snap down')
    state = settle(lambda s: s['placement'] == 'floating' and s['rect'] == x11_floating['rect'])
    check('X11 Super+Down restores the pre-snap rect', state,
          state['placement'] == 'floating' and state['rect'] == x11_floating['rect'])
    fixture.terminate()
    fixture.wait()
else:
    print('SKIP X11 phase: XWayland did not start')

# --- D. Snap Assist and a two-member snap group (phase 1). ---
fixture = start_fixture(0, 3)
time.sleep(1.0)
send('focus 0')
state = settle(lambda s: s['placement'] == 'floating')
send('snap left')
state = settle(lambda s: s['rect'] == left)
assist = read_assist()
check('snapping a half with others open offers Snap Assist', state,
      assist['open'] and assist['candidates'] == 2 and assist['selected'] == 0,
      str({k: assist[k] for k in ('open', 'candidates')} if assist['open'] else assist))
if assist['open']:
    zone = tuple(int(v) for v in assist['zone'].split(','))
    check('Assist fills the empty half', state, zone == right, str(zone))
    check('Assist cells sit inside the empty half', state,
          all(c[0] >= right[0] and c[0] + c[2] <= right[0] + right[2] for c in assist['cells']))
    time.sleep(0.3)
    screenshot('snap-assist')
send('assist next')
after_next = read_assist()
send('assist prev')
after_prev = read_assist()
check('Assist arrows move the selection', state,
      after_next.get('selected') == 1 and after_prev.get('selected') == 0)
send('assist dismiss')
dismissed = read_assist()
state = settle(lambda s: True)
check('Escape closes Assist and leaves the tile alone', state,
      not dismissed['open'] and state['placement'] == 'tiled-left' and state['group'] is None)

send('snap left')
settle(lambda s: s['placement'] == 'floating')
send('snap left')
settle(lambda s: s['rect'] == left)
assist = read_assist()
cell = assist['cells'][1] if assist.get('open') and len(assist['cells']) > 1 else (0, 0, 0, 0)
send(f'assist-click {cell[0] + cell[2] // 2} {cell[1] + cell[3] // 2}')
chosen = settle(lambda s: s['rect'] == right)
check('clicking a thumbnail snaps that window into the empty half', chosen,
      chosen['placement'] == 'tiled-right' and chosen['rect'] == right and chosen['group'] is not None
      and not read_assist()['open'])
group = chosen['group']
partner_index = None
for index in (1, 2):
    send(f'focus {index}')
    probe = settle(lambda s: True)
    if probe['placement'] == 'tiled-right':
        partner_index = index
send('focus 0')
state = settle(lambda s: True)
check('both halves form one snap group', state,
      state['group'] == group and group is not None and group.endswith(':0.500'), f'group={state["group"]}')

edge = (left[0] + left[2] - 2, left[1] + left[3] // 2)
send(f'split-press {edge[0]} {edge[1]}')
for point in path(edge, (edge[0] + 200, edge[1]), steps=10)[1:]:
    send(f'motion {point[0]} {point[1]}')
    time.sleep(0.03)
send('release')
time.sleep(0.4)
resized = settle(lambda s: s['w'] == left[2] + 200)
send(f'focus {partner_index}')
partner = settle(lambda s: s['x'] == resized['x'] + resized['w'])
check('dragging the shared edge resizes both members', resized,
      resized['w'] == left[2] + 200 and partner['x'] == resized['x'] + resized['w']
      and resized['w'] + partner['w'] == area[2] and partner['placement'] == 'tiled-right',
      f'left={resized["rect"]} right={partner["rect"]} group={partner["group"]}')
split_left = resized['rect']

send('focus 0')
send('snap up')
state = settle(lambda s: s['rect'] == area)
send('snap down')
state = settle(lambda s: s['rect'] == split_left)
check('maximize and restore keep the group and its split', state,
      state['placement'] == 'tiled-left' and state['rect'] == split_left and state['group'] == partner['group'])

send('snap down')
settle(lambda s: s['placement'] == 'floating')
send(f'focus {partner_index}')
state = settle(lambda s: s['rect'] == right)
check('un-snapping one member dissolves the group; the other returns to its half', state,
      state['placement'] == 'tiled-right' and state['rect'] == right and state['group'] is None)

send('focus 0')
send('snap left')
state = settle(lambda s: s['rect'] == left)
check('snapping beside an existing tile groups at once, without Assist', state,
      state['group'] is not None and state['group'].endswith(':0.500') and not read_assist()['open'])
fixture.terminate()
fixture.wait()

with open(f'{OUT}/snap-receipts.json', 'w') as out:
    json.dump({'area': area, 'floating': F, 'steps': receipts, 'failures': failures}, out, indent=1)
print(f'{len(receipts) - len(failures)}/{len(receipts)} snap checks passed')
sys.exit(1 if failures else 0)
