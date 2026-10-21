# SPDX-License-Identifier: GPL-3.0-or-later
"""Shell bar exclusion with bounded asynchronous known-application metadata."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

MAX_INSET = 256
REFRESH_SECONDS = 15


def inset_value(value):
    try:
        return max(0, min(MAX_INSET, int(value)))
    except (TypeError, ValueError):
        return 0


def shell_workarea(workarea, monitor, top_height=0, bottom_height=0):
    """Reserve only missing shell-bar space; metadata y coordinates are ignored."""
    x, y, width, available = workarea
    mx, my, mw, mh = monitor
    left, top = max(x, mx), max(y, my)
    right = max(left + 1, min(x + width, mx + mw))
    bottom = max(top + 1, min(y + available, my + mh))
    top_height = min(inset_value(top_height), max(0, mh // 2))
    bottom_height = min(inset_value(bottom_height), max(0, mh // 2))
    top = min(bottom - 1, max(top, my + top_height))
    bottom = max(top + 1, min(bottom, my + mh - bottom_height))
    return left, top, right - left, bottom - top


def dock_workarea(workarea, monitor, height):
    """Compatibility helper for bottom-reservation fixtures."""
    return shell_workarea(workarea, monitor, 0, height)


def matching_height(frame, monitor_width):
    """Accept only a showing frame from the explicitly named shell application."""
    if frame.get('app') not in ('io.elementary.dock', 'io.elementary.wingpanel') or not frame.get('showing'):
        return 0
    width, height = frame.get('width', 0), frame.get('height', 0)
    if abs(width - monitor_width) > max(16, monitor_width * 0.05):
        return 0
    return inset_value(height) if 0 < height <= MAX_INSET else 0


def probe_atspi(width):
    """Child-only app-name enumeration; first frame of Dock/Wingpanel only.

    Returns top/bottom heights, None per unavailable edge; no private app trees.
    Known shell app identity defines the edge, never its unreliable y position.
    """
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    Atspi.set_timeout(150, 150)
    deadline = time.monotonic() + 0.4
    desktop = Atspi.get_desktop(0)
    if desktop is None:
        return None
    count = desktop.get_child_count()
    if count > 64:
        return None
    heights = [0, 0]
    known = {'io.elementary.wingpanel': 0, 'io.elementary.dock': 1}
    for index in range(count):
        if time.monotonic() >= deadline:
            return None  # Incomplete enumeration cannot establish absence.
        app = desktop.get_child_at_index(index)
        name = app.get_name() if app is not None else ''
        if name not in known:
            continue
        edge = known[name]
        try:
            if app.get_child_count() < 1:
                heights[edge] = None
                continue
            frame = app.get_child_at_index(0)
            if frame is None or frame.get_role() != Atspi.Role.FRAME:
                heights[edge] = None
                continue
            if not frame.get_state_set().contains(Atspi.StateType.SHOWING):
                heights[edge] = 0
                continue
            rect = frame.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
            heights[edge] = matching_height({'app': name, 'showing': True,
                                            'width': rect.width, 'height': rect.height}, width)
        except Exception:
            heights[edge] = None
    return heights


def probe_child(width):
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), '--probe', str(width)],
            capture_output=True, text=True, timeout=0.8, check=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
        )
        value = json.loads(result.stdout[:64])
        return tuple(value) if (isinstance(value, list) and len(value) == 2
                                and all(v is None or type(v) is int and 0 <= v <= MAX_INSET
                                        for v in value)) else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


class ShellCache:
    """One worker/child maximum; one completion idle; no periodic polling timer.

    Worker results are applied on the main loop. Geometry changes invalidate
    cached measurements immediately. An unavailable probe uses the declared
    fallback; confirmed absence uses zero. Refreshes are demand-driven, at most
    once per 15 seconds, with no render/completion refresh loop.
    """
    def __init__(self, post, changed, fallback=None, probe=probe_child,
                 clock=time.monotonic, start=None):
        self.post, self.changed, self.probe, self.clock = post, changed, probe, clock
        self.start = start or (lambda job: threading.Thread(target=job, daemon=True).start())
        self.fallback = (inset_value(os.environ.get('MSERIES_NOTIFICATION_TOP_INSET', '0')),
                         inset_value(os.environ.get('MSERIES_NOTIFICATION_DOCK_INSET', '0'))) if fallback is None else tuple(inset_value(v) for v in fallback)
        self.insets = self.fallback
        self.key = None
        self.checked = float('-inf')
        self.busy = False
        self.generation = 0

    def invalidate(self):
        self.generation += 1
        self.key = None
        self.insets = self.fallback
        self.checked = float('-inf')

    def current(self, monitor):
        key = tuple(monitor)
        if key != self.key:
            self.generation += 1
            self.key, self.insets, self.checked = key, self.fallback, float('-inf')
        if not self.busy and self.clock() - self.checked >= REFRESH_SECONDS:
            self.busy = True
            self.checked = self.clock()
            generation = self.generation
            def worker():
                try:
                    measured = self.probe(key[2])
                except Exception:
                    measured = None
                self.post(lambda: self._complete(key, generation, measured))
            self.start(worker)
        return self.insets

    def _complete(self, key, generation, measured):
        self.busy = False
        if key != self.key or generation != self.generation:
            self.checked = float('-inf')
            self.changed()  # Schedule a fresh measurement for the new monitor.
            return False
        selected = self.fallback if measured is None else tuple(
            fallback if value is None else inset_value(value)
            for fallback, value in zip(self.fallback, measured))
        if selected != self.insets:
            self.insets = selected
            self.changed()
        return False


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--probe':
        raise SystemExit('Internal shell metadata probe: --probe MONITOR_WIDTH')
    try:
        print(json.dumps(probe_atspi(int(sys.argv[2]))))
    except Exception:
        print('null')  # No content or accessible names are logged.
