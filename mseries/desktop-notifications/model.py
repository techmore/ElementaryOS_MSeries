# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded, ephemeral notification state; no toolkit, I/O or message APIs."""
from collections import OrderedDict
from dataclasses import dataclass
import unicodedata

MAX_VISIBLE = 3
MAX_ACTIONS = 3


def text(value, limit):
    value = str(value)[:limit]
    return ''.join(c for c in value if c in '\n\t' or not unicodedata.category(c).startswith('C'))


def actions_from(values):
    selected = []
    seen = set()
    # Limit traversal as well as retained strings; identifiers remain exact.
    for index in range(0, min(len(values) - 1, 32), 2):
        key, label = str(values[index]), str(values[index + 1])
        if not key or len(key) > 128 or key in seen:
            continue
        if key != 'default' and sum(k != 'default' for k, _ in selected) >= MAX_ACTIONS:
            continue
        seen.add(key)
        selected.append((key, text(label, 48)))
    return tuple(selected)


@dataclass(frozen=True)
class Notice:
    id: int
    owner: str
    app: str
    summary: str
    body: str
    actions: tuple
    timeout: int


class Store:
    def __init__(self, schedule, cancel, changed, closed, invoked, muted=lambda: False):
        self.schedule, self.cancel = schedule, cancel
        self.changed, self.closed, self.invoked = changed, closed, invoked
        self.muted = muted
        self.items = OrderedDict()
        self.timers = {}
        self.next_id = 1
        self.limit = MAX_VISIBLE

    def notify(self, owner, replaces, app, summary, body, actions, timeout):
        old = self.items.get(int(replaces))
        if old is not None and old.owner == owner:
            nid = old.id
            self._cancel(nid)
        else:
            nid = self.next_id
            self.next_id = self.next_id % 0xffffffff + 1
            while nid in self.items:
                nid = self.next_id
                self.next_id = self.next_id % 0xffffffff + 1
        timeout = int(timeout)
        timeout = 8000 if timeout < 0 else min(timeout, 120000)
        notice = Notice(nid, owner, text(app, 80), text(summary, 160),
                        text(body, 1024), actions_from(actions), timeout)
        self.items[nid] = notice
        self.items.move_to_end(nid)
        while len(self.items) > self.limit:
            self.close(next(iter(self.items)), 4)
        if self.muted():
            # Suppressed notifications retain no content or timer.
            self.close(nid, 4)
        else:
            self.changed()
            if timeout:
                self.timers[nid] = self.schedule(timeout, lambda: self._expire(nid))
        return nid

    def _cancel(self, nid):
        timer = self.timers.pop(nid, None)
        if timer is not None:
            self.cancel(timer)

    def _expire(self, nid):
        self.timers.pop(nid, None)
        self.close(nid, 1)
        return False

    def close(self, nid, reason, owner=None):
        notice = self.items.get(nid)
        if notice is None or (owner is not None and owner != notice.owner):
            return
        self._cancel(nid)
        del self.items[nid]
        self.changed()
        self.closed(nid, reason)

    def activate(self, nid, key):
        notice = self.items.get(nid)
        if notice is None or key not in dict(notice.actions):
            return
        self.invoked(nid, key)
        # Undefined reason avoids presenting an action as a deliberate dismissal
        # to clients which interpret reason=2 as a phone mark-read request.
        self.close(nid, 4)

    def clear(self):
        for nid in tuple(self.items):
            self.close(nid, 4)


def positions(area, count, width=360, height=180, margin=16, gap=12):
    """Logical X11 coordinates, newest at the bottom, no workarea overflow."""
    x, y, w, h = area
    width = max(1, min(width, w - 2 * margin))
    height = max(1, min(height, h - 2 * margin))
    capacity = max(1, min(MAX_VISIBLE, (max(1, h - 2 * margin) + gap) // (height + gap)))
    count = min(count, capacity)
    right = x + max(0, w - margin - width)
    bottom = y + max(0, h - margin - height)
    return [(right, bottom - i * (height + gap), width, height) for i in range(count)]
