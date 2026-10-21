#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Poll a human-labelled dock plug cycle without changing hardware state.

Timing starts at the first observed new Type-C partner (or fallback discovery),
not physical cable insertion. Compositor activation is not visible pixels.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'aurora'))
import qualification as q


def snapshot():
    from gi.repository import Gio
    dock = [p.name for p in Path('/sys/bus/thunderbolt/devices').glob('*')
            if 'WD22TB4' in (q.read(p / 'device_name') or '')]
    connected = sorted(p.name for p in Path('/sys/class/drm').glob('card*-*')
                       if not p.name.split('-', 1)[-1].startswith(('eDP', 'DSI', 'LVDS'))
                       and q.read(p / 'status') == 'connected')
    modes, error = [], None
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        state = bus.call_sync('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
                             'org.gnome.Mutter.DisplayConfig', 'GetCurrentState', None, None,
                             Gio.DBusCallFlags.NONE, 700, None).unpack()
        modes = [{'connector': spec[0], 'width': w, 'height': h, 'refresh_hz': hz}
                 for spec, options, props in state[1]
                 for name, w, h, hz, preferred, scales, flags in options
                 if flags.get('is-current') and not spec[0].startswith(('eDP', 'DSI', 'LVDS'))]
    except Exception as exc:
        error = type(exc).__name__
    return {'partners': sorted(p.name for p in Path('/sys/class/typec').glob('port*-partner')),
            'dock': sorted(dock), 'connected': connected, 'active_modes': modes,
            'display_query_error': error}


class Tracker:
    def __init__(self, detached_s=2, stable_s=3):
        self.detached_s, self.stable_s = detached_s, stable_s
        self.detached_since = self.active_since = None
        self.baseline = self.start = None
        self.detached_partners = None
        self.origin = None
        self.first = {}
        self.complete = False

    def observe(self, now, state):
        clear = not state['dock'] and not state['connected'] and not state['active_modes']
        if self.baseline is None:
            if not clear:
                self.detached_since = None
                return 'wait-detach'
            if self.detached_since is None:
                self.detached_since = now
                self.detached_partners = set(state['partners'])
            if now - self.detached_since < self.detached_s:
                return 'wait-detach'
            # Preserve the detached partner set. A new partner can arrive on
            # the same poll that completes the clean-detach window.
            self.baseline = self.detached_partners
        new_partner = bool(set(state['partners']) - self.baseline)
        stages = {'partner_detected': new_partner, 'dock_enumerated': bool(state['dock']),
                  'monitor_connected': bool(state['connected']), 'compositor_active': bool(state['active_modes'])}
        if self.start is None:
            if not any(stages.values()):
                return 'ready-for-plug'
            self.start = now
            self.origin = next(k for k, v in stages.items() if v)
        for label, present in stages.items():
            if present and label not in self.first:
                self.first[label] = round(now - self.start, 3)
        if state['active_modes'] and state['dock']:
            if self.active_since is None:
                self.active_since = now
            self.complete = now - self.active_since >= self.stable_s
        else:
            self.active_since = None
        return 'complete' if self.complete else 'waiting-for-active-mode'


def run(args):
    os.umask(0o077)
    if args.output.exists():
        raise ValueError('preserve prior evidence: choose a fresh output directory')
    if not 0.2 <= args.interval <= 2 or not 10 <= args.timeout <= 600:
        raise ValueError('interval 0.2..2 seconds and timeout 10..600 required')
    record = json.loads(args.receipt.read_text())
    identity = q.validate_receipt(record)
    boot_id = q.read('/proc/sys/kernel/random/boot_id')
    if boot_id != record['boot_id'] or q.read('/proc/sys/kernel/osrelease') != identity['kernel_release']:
        raise ValueError('running boot differs from supplied qualified-identity receipt')
    args.output.mkdir(parents=True, mode=0o700)
    tracker = Tracker()
    started = time.monotonic()
    last = phase = None
    events = []
    last_state = {}
    print('WAITING: unplug dock, hold detached at least 5 seconds, then plug into ' + args.port, flush=True)
    with (args.output / 'events.jsonl').open('x') as stream:
        while time.monotonic() - started < args.timeout:
            before = time.monotonic()
            if q.read('/proc/sys/kernel/random/boot_id') != boot_id:
                raise ValueError('boot changed')
            state = snapshot()
            observed = time.monotonic()
            step = tracker.observe(observed, state)
            if state != last or step != phase:
                event = {'elapsed_s': round(observed - started, 3), 'query_duration_s': round(observed - before, 3),
                         'phase': step, 'state': state}
                events.append(event)
                stream.write(json.dumps(event) + '\n'); stream.flush()
            if step != phase:
                print(step, tracker.first, flush=True)
            last, phase, last_state = state, step, state
            if tracker.complete:
                break
            time.sleep(max(0, args.interval - (time.monotonic() - before)))
    result = {'schema': 1, 'kind': 'dock-port-discovery-timing', 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'physical_port_owner_label': args.port, 'boot_id': boot_id, 'identity_sha256': record['identity_sha256'],
              'kernel_release': identity['kernel_release'], 'source_receipt_sha256': q.digest(args.receipt),
              'runner_sha256': q.digest(__file__), 'requested_poll_interval_s': args.interval,
              'state_changes': len(events), 'timing_origin': tracker.origin,
              'first_observed_stage_seconds': tracker.first,
              'active_mode_stable_at_finish': tracker.complete, 'final_state': last_state,
              'result': 'active-mode-observed' if tracker.complete else 'timeout',
              'physical_picture': 'requires owner confirmation; not measured by polling',
              'limits': 'One plug cycle; detection-to-state timing, not physical insertion-to-visible-image. Poll/query latency applies; no driver/parameter/mode changes, no USB functional/suspend/recovery or repeated stability qualification.'}
    q.write_new(args.output / 'result.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, choices=['front-left', 'rear-left', 'right'])
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--interval', type=float, default=.5)
    parser.add_argument('--timeout', type=float, default=240)
    run(parser.parse_args())
