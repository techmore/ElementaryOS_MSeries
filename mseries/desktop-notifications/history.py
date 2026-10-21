# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded notification history, separate from phone message read state."""
from collections import OrderedDict
import time

from model import actions_from, text


class History:
    def __init__(self, limit=100, clock=time.time):
        self.entries = OrderedDict()
        self.limit, self.clock = limit, clock

    def add(self, nid, app, summary, body, actions, desktop='', handle=''):
        old = self.entries.get(nid)
        summary, body = text(summary, 160), text(body, 1024)
        read = bool(old and old['read'] and old['summary'] == summary and old['body'] == body)
        self.entries[nid] = dict(id=int(nid), app=text(app, 80), summary=summary,
                                 body=body, actions=dict(actions_from(actions)),
                                 received_at=int(self.clock()), read=read,
                                 desktop=desktop, handle=handle)
        self.entries.move_to_end(nid)
        while len(self.entries) > self.limit:
            self.entries.popitem(last=False)

    def read(self, nid):
        entry = self.entries.get(int(nid))
        if entry:
            entry['read'] = True

    def mark_all_read(self):
        count = self.unread
        for entry in self.entries.values():
            entry['read'] = True
        return count

    @property
    def unread(self):
        return sum(not entry['read'] for entry in self.entries.values())

    def list(self, limit, active):
        rows = []
        for entry in reversed(self.entries.values()):
            can_dispatch = entry['id'] in active
            rows.append({**{key: entry[key] for key in
                            ('id', 'app', 'summary', 'body', 'received_at', 'read')},
                         'open_available': bool(entry['handle'] or entry['desktop'] or
                                                (can_dispatch and 'default' in entry['actions'])),
                         'can_reply': 'reply' in entry['actions'] and
                                      bool(entry['handle'] or can_dispatch)})
            if len(rows) >= max(1, min(int(limit), 100)):
                break
        return rows
