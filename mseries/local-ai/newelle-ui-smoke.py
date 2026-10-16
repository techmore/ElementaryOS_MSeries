#!/usr/bin/python3
"""Run inside Newelle/Xvfb: actual Send, configured MCP clock and persistent memory."""
import argparse
import gettext
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    gettext.install('newelle', '/app/share/locale')
    sys.path.insert(0, '/app/share/newelle')
    from newelle.main import MyApp
    from gi.repository import GLib
    app = MyApp(application_id='io.github.qwersyk.Newelle', version='1.6.0')
    phase, receipt = 0, {'test': 'actual Newelle Send/response and MCP clock through Xvfb'}
    expected = {'system_status', 'list_apps', 'list_tasks', 'list_calendar_events', 'add_minutes',
                'get_energy', 'workspace_list_files', 'workspace_read_file', 'workspace_write_note', 'recent_faults'}
    def probe():
        nonlocal phase
        try:
            for window in app.get_windows():
                tab = window.get_active_chat_tab() if hasattr(window, 'get_active_chat_tab') else None
                if tab is None:
                    continue
                if phase == 0:
                    receipt['enabled_tools'] = [t.name for t in tab.controller.get_enabled_tools()]
                    if set(receipt['enabled_tools']) != expected:
                        raise RuntimeError('Unexpected enabled tools in final Newelle profile')
                    tab.input_panel.set_text('Reply only: Newelle local test passed')
                    tab.on_entry_button_clicked(); phase = 1
                elif phase == 1 and tab.status:
                    receipt['chat_answer'] = tab.chat[-1].get('Message')
                    if 'Newelle local test passed' not in str(receipt['chat_answer']):
                        raise RuntimeError('Unexpected synthetic chat response')
                    tab.input_panel.set_text('Use add_minutes to calculate 09:45 plus 115 minutes. Reply only HH:MM.')
                    tab.on_entry_button_clicked(); phase = 2
                elif phase == 2 and tab.status:
                    receipt['clock_answer'] = tab.chat[-1].get('Message')
                    receipt['usage'] = tab.chat[-1].get('LLMUsage')
                    if str(receipt['clock_answer']).strip() != '11:40':
                        raise RuntimeError('Newelle MCP clock did not return 11:40')
                    phase = 3; app.quit(); return False
        except Exception as error:
            receipt['error'] = str(error)[:300]; app.quit(); return False
        return True
    GLib.timeout_add_seconds(2, probe)
    GLib.timeout_add_seconds(180, lambda: (app.quit(), False)[1])
    app.run(['newelle-ui-smoke'])
    receipt['passed'] = phase == 3
    (args.output_dir / 'newelle-final-ui-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if not receipt['passed']:
        raise SystemExit('Final Newelle UI profile test failed; inspect bounded receipt.')
    here = Path(__file__).resolve().parent
    model = str(Path.home() / '.cache/huggingface/hub/models--mlx-community--Qwen3.5-9B-MLX-4bit/snapshots/938d8919941c6e7efd3c7150eff7fe9d12afa631')
    for step in ['write', 'read']:
        subprocess.run(['python3', str(here / 'newelle-memory-smoke.py'), step,
                        '--state', str(args.output_dir / 'newelle-memory-persistence'), '--model', model,
                        '--output', str(args.output_dir / 'newelle-persistent-memory.json')], check=True)
    subprocess.run(['flatpak-spawn', '--host', '/usr/bin/python3', str(here / 'triage-smoke.py'),
                    '--output', str(args.output_dir / 'triage-smoke-receipt.json')], check=True)
    print('Newelle UI, persistent synthetic memory and troubleshooting checks passed.')


if __name__ == '__main__':
    main()
