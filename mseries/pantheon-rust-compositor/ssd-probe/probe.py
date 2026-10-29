"""Drive the server-side frame of an X11 window on the nested compositor.

Run by run.sh inside a private Xvfb + D-Bus session. HOST_DISPLAY is the Xvfb that
shows the nested compositor; XDISPLAY is the compositor's own XWayland. Pointer input
goes through xdotool on the host display, geometry is read back through xdotool on
XWayland, and screenshots of the host display are kept in OUT.

Prints one RESULT line per check, PASS or FAIL.
"""
import os
import subprocess
import sys
import time

HOST = os.environ['HOST_DISPLAY']
XDISPLAY = os.environ['XDISPLAY']
COMP = os.environ['COMP_PID']
OUT = os.environ['OUT']
HERE = os.path.dirname(os.path.abspath(__file__))
TITLE = 34          # decorations::TITLE_HEIGHT
PAD, BUTTON, GAP = 7, 24, 4  # button layout 'close,minimize,maximize:' set by run.sh
failures = []


def run(display, *args):
    env = dict(os.environ, DISPLAY=display)
    return subprocess.run(args, env=env, capture_output=True, text=True).stdout.strip()


def host(*args):
    return run(HOST, 'xdotool', *args)


def inner(*args):
    return run(XDISPLAY, 'xdotool', *args)


def check(name, ok, detail):
    print('RESULT %s %s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)
    if not ok:
        failures.append(name)


def geometry(window):
    values = {}
    for line in inner('getwindowgeometry', '--shell', window).splitlines():
        key, _, value = line.partition('=')
        values[key] = int(value) if value.lstrip('-').isdigit() else value
    return values.get('X'), values.get('Y'), values.get('WIDTH'), values.get('HEIGHT')


def find(title, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        ids = inner('search', '--onlyvisible', '--name', '^%s$' % title).split()
        if ids:
            return ids[-1]
        time.sleep(0.2)
    return None


def settle(window, timeout=2.0):
    """Geometry once it stops changing."""
    last, end = None, time.monotonic() + timeout
    while time.monotonic() < end:
        now = geometry(window)
        if now == last:
            return now
        last = now
        time.sleep(0.25)
    return last


def screenshot(name):
    path = os.path.join(OUT, name)
    run(HOST, 'import', '-window', 'root', path)
    return path


def pixel(path, x, y):
    out = subprocess.run(['convert', path, '-crop', '1x1+%d+%d' % (x, y), '-depth', '8', 'txt:-'],
                         capture_output=True, text=True).stdout
    # "0,0: (250,250,250)  #FAFAFA  srgb(...)"
    rgb = out.split('(')[1].split(')')[0].split(',')[:3] if '(' in out else ['0', '0', '0']
    return tuple(int(float(value)) for value in rgb)


nested = host('search', '--pid', COMP).split()
origin = (0, 0)
for candidate in nested:
    shell = dict(line.split('=', 1) for line in host('getwindowgeometry', '--shell', candidate).splitlines() if '=' in line)
    if int(shell.get('WIDTH', 0)) > 200:
        origin = (int(shell['X']), int(shell['Y']))
        break


def to_host(x, y):
    return int(origin[0] + x), int(origin[1] + y)


def drag(start, delta, steps=12, button=1):
    x, y = to_host(*start)
    host('mousemove', str(x), str(y))
    time.sleep(0.15)
    host('mousedown', str(button))
    for step in range(1, steps + 1):
        host('mousemove', str(int(x + delta[0] * step / steps)), str(int(y + delta[1] * step / steps)))
        time.sleep(0.03)
    host('mouseup', str(button))
    time.sleep(0.4)


def click(point, repeat=1):
    x, y = to_host(*point)
    host('mousemove', str(x), str(y))
    time.sleep(0.15)
    host('click', '--repeat', str(repeat), '--delay', '120', '1')
    time.sleep(0.5)


def button_centre(spec, index):
    x, y, _, _ = spec
    return x + PAD + index * (BUTTON + GAP) + BUTTON // 2, y - TITLE // 2


# 1. A window that asks the window manager for decorations gets a title bar.
env = dict(os.environ, DISPLAY=XDISPLAY, GDK_BACKEND='x11')
ssd = subprocess.Popen([sys.executable, '-W', 'ignore', os.path.join(HERE, 'x11-window.py'),
                        'ssd', 'ssd-probe', '640', '560'], env=env)
window = find('ssd-probe')
if window is None:
    check('map', False, 'ssd-probe never mapped')
    sys.exit(1)
start = settle(window)
props = run(XDISPLAY, 'xprop', '-id', window, '_MOTIF_WM_HINTS', 'WM_NORMAL_HINTS')
check('wifiman-hints', '0x2, 0x0, 0x1, 0x0, 0x0' in props and '420 by 460' in props,
      ' '.join(line.strip() for line in props.splitlines() if 'MOTIF' in line or 'minimum' in line))
shot = screenshot('1-framed.png')
x, y, w, h = start
bar = pixel(shot, *to_host(x + w // 5, y - TITLE // 2))
above = pixel(shot, *to_host(x + w // 5, y - TITLE - 12))
check('title-bar', min(bar) > 200 and bar != above and y >= TITLE,
      'window=%s bar_pixel=%s above_pixel=%s' % (start, bar, above))

# 2. Dragging the title bar moves the X11 window.
drag((x + w // 5, y - TITLE // 2), (120, 80))
moved = settle(window)
check('drag-move', moved[:2] == (x + 120, y + 80) and moved[2:] == start[2:],
      'from=%s to=%s' % (start[:2], moved[:2]))

# 3. The bottom-right resize band shrinks it, but not below its 420x460 minimum.
x, y, w, h = moved
drag((x + w + 3, y + h + 3), (-400, -400))
small = settle(window)
check('resize-min', small[2:] == (420, 460), 'size=%s (min 420x460)' % (small[2:],))
x, y, w, h = small
drag((x + w + 3, y + h + 3), (100, 50))
grown = settle(window)
check('resize-grow', grown[2:] == (520, 510), 'size=%s' % (grown[2:],))

# 4. The left edge resizes from the left and keeps the right edge put.
x, y, w, h = grown
drag((x - 3, y + h // 2), (-60, 0))
left = settle(window)
check('resize-left', left[0] == x - 60 and left[0] + left[2] == x + w, 'rect=%s' % (left,))

# 5. Maximize button, then double-click on the title bar restores it.
click(button_centre(left, 2))
maximized = settle(window)
screenshot('2-maximized.png')
check('maximize', maximized[1] == TITLE and maximized[2] > left[2],
      'rect=%s (client below the title bar)' % (maximized,))
x, y, w, h = maximized
click((x + w // 2 + 80, y - TITLE // 2), repeat=2)
restored = settle(window)
check('double-click-restore', restored == left, 'rect=%s want %s' % (restored, left))

# 6. A client-side decorated window gets no frame, and its own header bar drag
#    (_NET_WM_MOVERESIZE) moves it.
csd = subprocess.Popen([sys.executable, '-W', 'ignore', os.path.join(HERE, 'x11-window.py'),
                        'csd', 'csd-probe', '400', '300'], env=env)
csd_window = find('csd-probe')
if csd_window is None:
    check('csd-map', False, 'csd-probe never mapped')
else:
    begin = settle(csd_window)
    x, y, w, h = begin
    # Where a server title bar would be: nothing to grab, nothing moves.
    if y > 30:
        drag((x + w // 2, y - 15), (50, 50))
    unchanged = settle(csd_window)
    check('csd-no-frame', unchanged == begin, 'rect=%s' % (unchanged,))
    drag((x + w // 3, y + 15), (90, 40))
    after = settle(csd_window)
    check('moveresize-move', after[:2] == (x + 90, y + 40), 'from=%s to=%s' % (begin[:2], after[:2]))
    screenshot('3-csd.png')
    csd.terminate()

# 7. The close button asks the client to close (WM_DELETE_WINDOW).
spec = settle(window)
run(XDISPLAY, 'xdotool', 'windowactivate', window)
time.sleep(0.3)
click(button_centre(spec, 0))
try:
    ssd.wait(timeout=5)
    check('close', True, 'client exited with %s' % ssd.returncode)
except subprocess.TimeoutExpired:
    check('close', False, 'client still running')
    ssd.kill()

print('RESULT %s' % ('ALL PASS' if not failures else 'FAILED ' + ' '.join(failures)), flush=True)
sys.exit(1 if failures else 0)
