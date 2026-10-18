#!/usr/bin/python3
"""Run inside the Newelle Flatpak twice to verify synthetic memory across processes."""
import argparse
import gettext
import json
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=['write', 'read'])
    p.add_argument('--state', type=Path, required=True, help='Dedicated test directory; no live Newelle settings are changed')
    p.add_argument('--model', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    gettext.install('newelle', '/app/share/locale')
    sys.path.insert(0, '/app/share/newelle')
    from gi.repository import Gio
    from newelle.handlers.llm.openai_handler import OpenAIHandler
    from newelle.handlers.memory.user_summary_handler import UserSummaryHandler
    args.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = args.state / 'synthetic-settings.ini'
    if not path.exists():
        path.touch(mode=0o600)
    backend = Gio.keyfile_settings_backend_new(str(path), '/', 'settings')
    settings = Gio.Settings.new_with_backend('io.github.qwersyk.Newelle', backend)
    settings.set_string('llm-settings', json.dumps({'openai': {'api': 'local',
        'endpoint': 'http://127.0.0.1:8766/v1', 'model': args.model, 'custom_model': True,
        'advanced_params': True, 'temperature': 0,
        'custom_body': json.dumps({'chat_template_kwargs': {'enable_thinking': False}})}}))
    llm = OpenAIHandler(settings, str(args.state))
    memory = UserSummaryHandler(settings, str(args.state))
    memory.set_handlers(llm, None); memory.set_memory_size(10)
    if args.phase == 'write':
        memory.set_setting('update_freq', 2)
        history = [{'User': 'User', 'Message': 'Synthetic test: my favorite umbrella color is cobalt blue.'},
                   {'User': 'Assistant', 'Message': 'I will remember your favorite umbrella color.'}]
        memory.get_context(history[0]['Message'], [])
        memory.register_response(history[1]['Message'], history)
        Gio.Settings.sync()
        if 'cobalt' not in memory.get_setting('user_summary').lower():
            raise SystemExit('Synthetic memory generation failed')
    else:
        summary = memory.get_setting('user_summary')
        if 'cobalt' not in summary.lower():
            raise SystemExit('Synthetic summary did not survive process restart')
        answer = llm.generate_text('What color is my favorite umbrella? Reply only the color.', [],
                                  memory.get_context('What color is my favorite umbrella?', []))
        receipt = {'storage': 'isolated Gio keyfile backend', 'cross_process_storage': True,
                   'summary': summary, 'recall': answer, 'passed': 'cobalt' in answer.lower(),
                   'live_user_settings_changed': False}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + '\n')
        if not receipt['passed']:
            raise SystemExit('Synthetic memory recall failed')
    print('Synthetic Newelle memory phase passed: ' + args.phase)


if __name__ == '__main__':
    main()
