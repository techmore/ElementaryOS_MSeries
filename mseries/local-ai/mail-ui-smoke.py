#!/usr/bin/python3
"""Hidden synthetic Assistant Mail Drafts → native Mail composer test; never sends."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--isolated', action='store_true', help=argparse.SUPPRESS)
    a = p.parse_args(); a.output = a.output.resolve()
    if not a.isolated:
        with tempfile.TemporaryDirectory(prefix='mseries-mail-ui-') as directory:
            state = Path(directory)
            env = dict(os.environ, XDG_CONFIG_HOME=str(state / 'config'), XDG_DATA_HOME=str(state / 'data'),
                       XDG_CACHE_HOME=str(state / 'cache'), MSERIES_ASSISTANT_WORKSPACE=str(state / 'workspace'),
                       GSETTINGS_BACKEND='memory', NO_AT_BRIDGE='0', GDK_BACKEND='x11')
            subprocess.run(['xvfb-run', '-a', 'dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()),
                            '--output', str(a.output), '--isolated'], env=env, check=True, timeout=90)
        return
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    from app_adapters import create_draft
    root = Path(os.environ['MSERIES_ASSISTANT_WORKSPACE'])
    payload = {'to': 'review+tag@example.invalid', 'subject': 'R&D + café',
               'body': 'A=B & C\nSecond line + 10%', 'request_id': 'mail-ui-test-1'}
    create_draft(root, payload)
    child = subprocess.Popen([sys.executable, str(HERE / 'mail-drafts-ui.py')], start_new_session=True)
    report = {'method': 'Hidden Xvfb and isolated D-Bus/XDG homes. Actual Assistant Mail Drafts review button to installed native Mail composer. Synthetic recipient/subject/body only; Send never activated.', 'passed': False}
    opened = False
    def walk(node, depth=0):
        if depth > 16: return []
        rows = []
        try:
            text = node.get_text_iface()
            row = {'node': node, 'role': node.get_role_name(), 'name': node.get_name(),
                   'text': Atspi.Text.get_text(text, 0, min(text.get_character_count(), 1000)) if text else ''}
            rows.append(row)
            for i in range(min(node.get_child_count(), 80)): rows += walk(node.get_child_at_index(i), depth + 1)
        except Exception: pass
        return rows
    try:
        for _ in range(40):
            time.sleep(.5); desktop = Atspi.get_desktop(0)
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i); rows = walk(app)
                if app.get_process_id() == child.pid and not opened:
                    previews = [r['text'] for r in rows]
                    if any(payload['body'] in text for text in previews):
                        button = next((r['node'] for r in rows if r['role'] == 'push button' and r['name'] == 'Open in Mail'), None)
                        if button is None: button = next((r['node'] for r in rows if r['name'] == 'Open in Mail'), None)
                        if button:
                            action = button.get_action_iface()
                            if not Atspi.Action.do_action(action, 0): raise RuntimeError('Review action failed')
                            opened = True; report['review_preview_match'] = True
                elif opened and app.get_process_id() != child.pid:
                    texts = [r['text'] for r in rows]
                    if payload['body'] in texts:
                        report.update(recipient_match=payload['to'] in texts, subject_match=payload['subject'] in texts,
                                      body_match=True, send_activated=False)
                        report['passed'] = report.get('review_preview_match', False) and report['recipient_match'] and report['subject_match']
            if report['passed']: break
    finally:
        try: os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: child.wait(timeout=8)
        except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, indent=2) + '\n')
    if not report['passed']: raise SystemExit('Mail UI handoff not verified; receipt retained')


if __name__ == '__main__': main()
