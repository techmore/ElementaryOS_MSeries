#!/usr/bin/python3
"""Run inside Newelle/Xvfb: actual Send, configured MCP clock and persistent memory."""
import argparse
import gettext
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--isolated', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--discovery-only', action='store_true', help='Verify the configured tool surface without sending inference requests')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    state = args.output_dir / 'newelle-ui-state'
    if not args.isolated:
        from gi.repository import Gio, GLib
        settings = Gio.Settings.new('io.github.qwersyk.Newelle')
        provider = json.loads(settings.get_string('llm-settings')).get('openai', {})
        if settings.get_string('language-model') != 'openai' or provider.get('endpoint') != 'http://127.0.0.1:8766/v1':
            raise SystemExit('This smoke requires the configured local loopback provider.')
        keys = ['language-model', 'llm-settings', 'mcp-servers', 'tools-settings',
                'context-max', 'context-suggested', 'max-tool-calls', 'websearch-on',
                'tts-on', 'secondary-llm-on', 'auto-run', 'auto-generate-name', 'rag-on-documents']
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        profile = state / 'profile.json'
        profile.write_text(json.dumps({k: settings.get_value(k).print_(True) for k in keys}))
        profile.chmod(0o600)
        # Keep installed optional dependencies, but isolate histories, caches,
        # extensions and all settings writes from the real user's instance.
        pip = Path(GLib.get_user_config_dir()) / 'pip'
        if pip.exists():
            shutil.copytree(pip, state / 'config/pip', dirs_exist_ok=True)
        env = dict(os.environ, GSETTINGS_BACKEND='memory', XDG_CONFIG_HOME=str(state / 'config'),
                   XDG_DATA_HOME=str(state / 'data'), XDG_CACHE_HOME=str(state / 'cache'))
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--output-dir',
                        str(args.output_dir), '--isolated'] + (['--discovery-only'] if args.discovery_only else []),
                       env=env, check=True, timeout=600)
        return
    gettext.install('newelle', '/app/share/locale')
    sys.path.insert(0, '/app/share/newelle')
    from newelle.main import MyApp
    from newelle.integrations.mcp import MCPIntegration
    from gi.repository import GLib, Gio
    settings = Gio.Settings.new('io.github.qwersyk.Newelle')
    for key, value in json.loads((state / 'profile.json').read_text()).items():
        settings.set_value(key, GLib.Variant.parse(None, value, None, None))
    settings.set_boolean('memory-on', False)  # Memory is tested separately with synthetic state.
    settings.set_boolean('welcome-screen-shown', True)
    settings.set_string('path', str(state))
    Gio.Settings.sync()
    # Observe the production dispatcher; preserve its execution and results.
    calls = []
    dispatch = MCPIntegration.execute_tool_name
    def observed(self, tool_name, **arguments):
        result = dispatch(self, tool_name, **arguments)
        if tool_name == 'add_minutes':
            calls.append((arguments, result))
        return result
    MCPIntegration.execute_tool_name = observed
    app = MyApp(application_id='io.github.qwersyk.Newelle', version='1.6.0')
    app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
    phase, receipt = 0, {'test': 'actual Newelle Send/response and MCP clock through Xvfb; configured provider/tool settings cloned into isolated test storage'}
    if args.discovery_only:
        receipt['test'] = 'Actual Newelle controller discovery through Xvfb; isolated clone of configured tools; no chat/memory inference requested'
    expected = {'system_status', 'list_apps', 'list_tasks', 'create_assistant_task', 'list_calendar_events', 'add_minutes',
                'get_energy', 'workspace_list_files', 'workspace_read_file', 'workspace_write_note', 'recent_faults',
                'create_assistant_event', 'browser_list_tabs', 'browser_read_page', 'create_mail_draft', 'read_mail_draft'}
    def probe():
        nonlocal phase
        try:
            for window in app.get_windows():
                tab = window.get_active_chat_tab() if hasattr(window, 'get_active_chat_tab') else None
                if tab is None:
                    continue
                if phase == 0:
                    receipt['enabled_tools'] = [t.name for t in tab.controller.get_enabled_tools()]
                    if not expected.issubset(receipt['enabled_tools']):
                        return True  # MCP discovery is asynchronous on a fresh cache.
                    if set(receipt['enabled_tools']) != expected:
                        raise RuntimeError('Unexpected enabled tools in final Newelle profile')
                    if args.discovery_only:
                        phase = 1; app.quit(); return False
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
                    receipt['clock_calls'] = [{'arguments': a, 'output': str(r.output)[:500]} for a, r in calls]
                    if not any(c['arguments'] == {'time': '09:45', 'minutes': '115'} and '11:40' in c['output'] for c in receipt['clock_calls']):
                        raise RuntimeError('Expected production MCP clock execution was not observed')
                    if str(receipt['clock_answer']).strip() != '11:40':
                        raise RuntimeError('Newelle MCP clock did not return 11:40')
                    phase = 3; app.quit(); return False
        except Exception as error:
            receipt['error'] = str(error)[:300]; app.quit(); return False
        return True
    GLib.timeout_add_seconds(2, probe)
    GLib.timeout_add_seconds(180, lambda: (app.quit(), False)[1])
    app.run(['newelle-ui-smoke'])
    receipt['passed'] = phase == (1 if args.discovery_only else 3)
    (args.output_dir / 'newelle-final-ui-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if not receipt['passed']:
        raise SystemExit('Final Newelle UI profile test failed; inspect bounded receipt.')
    if args.discovery_only:
        print('Newelle discovered the exact configured tool set; no inference requested.')
        return
    here = Path(__file__).resolve().parent
    model = json.loads(settings.get_string('llm-settings'))['openai']['model']
    for step in ['write', 'read']:
        subprocess.run(['python3', str(here / 'newelle-memory-smoke.py'), step,
                        '--state', str(args.output_dir / 'newelle-memory-persistence'), '--model', model,
                        '--output', str(args.output_dir / 'newelle-persistent-memory.json')], check=True)
    print('Newelle UI and persistent synthetic memory checks passed.')


if __name__ == '__main__':
    main()
