#!/usr/bin/python3
"""Install local assistant launchers, model policy, MCP adapters and Newelle settings."""
import json
import argparse
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
HOME = Path.home()
LIB = HOME / '.local/libexec/mseries-ai'
CONFIG = HOME / '.config/mseries-ai'
MODEL = str(HOME / '.cache/huggingface/hub/models--mlx-community--Qwen3.5-4B-MLX-4bit/snapshots/32f3e8ecf65426fc3306969496342d504bfa13f3')
QUALITY_MODEL = str(HOME / '.cache/huggingface/hub/models--mlx-community--Qwen3.5-9B-MLX-4bit/snapshots/938d8919941c6e7efd3c7150eff7fe9d12afa631')
ADDED_TOOLS = ['create_assistant_task', 'create_assistant_event', 'browser_list_tabs', 'browser_read_page', 'create_mail_draft', 'read_mail_draft']


def put(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() != value:
        backup = path.with_name(path.name + '.before-mseries')
        if not backup.exists():
            shutil.copy2(path, backup)
    path.write_text(value)
    path.chmod(mode)


def invalidate_mcp_cache():
    cache = HOME / '.var/app/io.github.qwersyk.Newelle/cache/extensions_cache/mcp_tool_cache.json'
    if cache.exists():
        try:
            metadata = json.loads(cache.read_text())
            identifier = 'stdio:/usr/bin/python3:' + str(LIB / 'os-mcp.py')
            if isinstance(metadata, dict) and identifier in metadata:
                del metadata[identifier]
                put(cache, json.dumps(metadata, indent=2) + '\n')
        except (OSError, ValueError):
            pass  # Newelle itself refetches unreadable schema caches.


def install_acp_helper():
    put(LIB / 'acp-agent.py', (HERE / 'acp-agent.py').read_text(), 0o755)
    put(HOME / '.local/bin/mseries-assistant-acp',
        '#!/usr/bin/python3\nimport os,sys\nscript = os.path.expanduser("~/.local/libexec/mseries-ai/acp-agent.py")\nos.execv("/usr/bin/python3", ["python3", script] + sys.argv[1:])\n',
        0o755)


def app_helpers():
    for name in ['app_adapters.py', 'mail-drafts-ui.py', 'runtime_recovery.py']:
        put(LIB / name, (HERE / name).read_text(), 0o755)
    for name, target, action in [('mseries-assistant-browser', 'app_adapters.py', 'browser'),
                                  ('mseries-review-mail-draft', 'app_adapters.py', 'review-mail'),
                                  ('mseries-mail-drafts', 'mail-drafts-ui.py', None)]:
        argv = [str(LIB / target)] + ([action] if action else [])
        put(HOME / '.local/bin' / name, '#!/usr/bin/python3\nimport os,sys\nos.execv("/usr/bin/python3",["python3"]+' + repr(argv) + '+sys.argv[1:])\n', 0o755)
    for name, title in [('mseries-assistant-browser', 'Assistant Browser'), ('mseries-mail-drafts', 'Assistant Mail Drafts')]:
        put(HOME / '.local/share/applications' / (name + '.desktop'),
            f'[Desktop Entry]\nType=Application\nName={title}\nExec="{HOME}/.local/bin/{name}"\nIcon=applications-internet\nTerminal=false\nCategories=Network;\n', 0o644)
    install_acp_helper()
    old_hermes_launcher = HOME / '.local/share/applications/mseries-hermes-assistant.desktop'
    expected_hermes_launcher = (
        f'[Desktop Entry]\nType=Application\nName=Hermes Assistant (Experimental)\n'
        f'Exec="{HOME}/.local/bin/mseries-assistant" hermes\n'
        'Icon=utilities-system-monitor\nTerminal=true\nCategories=Utility;\n'
    )
    try:
        if old_hermes_launcher.read_text() == expected_hermes_launcher:
            old_hermes_launcher.unlink()
    except FileNotFoundError:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adopt-compact-defaults', action='store_true', help='Adopt the measured 4B everyday/coding presets; retain policy and other profiles')
    parser.add_argument('--refresh-tools', action='store_true', help='Update MCP/app helpers and added tools; retain model, memory, policy and other settings')
    parser.add_argument('--install-acp', action='store_true', help='Install only the T3 ACP bridge; leave Newelle settings and model services untouched')
    args = parser.parse_args()
    if args.install_acp:
        if args.adopt_compact_defaults or args.refresh_tools:
            parser.error('--install-acp cannot be combined with other setup modes')
        if not (LIB / 'os-mcp.py').is_file():
            parser.error('--install-acp requires an existing MSeries assistant setup with os-mcp.py installed')
        install_acp_helper()
        print('Installed the T3 ACP bridge only; Newelle settings and model services were not changed.')
        return
    if args.refresh_tools:
        if args.adopt_compact_defaults or not (LIB / 'os-mcp.py').exists():
            parser.error('--refresh-tools requires an existing installation and cannot adopt presets')
        body = '''import json,sys
from gi.repository import Gio
s=Gio.Settings.new('io.github.qwersyk.Newelle')
servers=json.loads(s.get_string('mcp-servers'))
if not any(x.get('command')=='/usr/bin/python3' and x.get('args')==[sys.argv[1]] for x in servers):
    raise SystemExit('The installed MSeries MCP server is not configured in Newelle')
tools=json.loads(s.get_string('tools-settings'))
for name in json.loads(sys.argv[2]):tools[name]={'enabled':True,'lazy_load':False}
s.set_string('tools-settings',json.dumps(tools)); Gio.Settings.sync()
'''
        subprocess.run(['flatpak', 'run', '--command=python3', 'io.github.qwersyk.Newelle', '-c', body,
                        str(LIB / 'os-mcp.py'), json.dumps(ADDED_TOOLS)], check=True)
        app_helpers()
        put(LIB / 'os-mcp.py', (HERE / 'os-mcp.py').read_text(), 0o755)
        put(LIB / 'model-worker.py', (HERE / 'model-worker.py').read_text(), 0o755)
        invalidate_mcp_cache()
        print('Updated MCP/app helpers; retained model, memory, policy and other settings.')
        return
    LIB.mkdir(parents=True, exist_ok=True)
    for name in ['machine.py', 'model-worker.py', 'os-mcp.py', 'brief.py']:
        shutil.copy2(HERE / name, LIB / name)
    app_helpers()
    config = {'policy': {'reserve_gib': 6, 'max_fan_rpm': 3500, 'max_temp_c': 80,
                         'cool_fan_rpm': 2700, 'resume_fan_rpm': 2600, 'burst_s': 3, 'sample_s': 1}, 'profiles': {
        'everyday': {'engine': 'mlx', 'model': 'qwen3.5-4b-mseries-4bit', 'context': 8192, 'port': 8766, 'admission_gib': 6.5},
        'quality': {'engine': 'mlx', 'model': 'qwen3.5-9b-mlx-4bit', 'context': 8192, 'port': 8766, 'admission_gib': 9},
        'coder9': {'engine': 'mlx', 'model': 'qwen3.5-9b-mlx-4bit', 'context': 16384, 'port': 8768, 'admission_gib': 10},
        'compact': {'engine': 'mlx', 'model': 'qwen3-4b-instruct-2507-4bit', 'context': 4096, 'port': 8766, 'admission_gib': 4.5},
        'compact35': {'engine': 'mlx', 'model': 'qwen3.5-4b-mseries-4bit', 'context': 16384, 'port': 8768, 'admission_gib': 6.5},
        'personal': {'engine': 'mlx', 'model': 'qwen3.5-9b-mlx-4bit', 'context': 64000, 'port': 8766,
                     'prompt_cache_size': 1, 'admission_gib': 13},
        'coder': {'engine': 'mlx', 'model': 'qwen3.5-4b-mseries-4bit',
                  'context': 16384, 'port': 8768, 'admission_gib': 6.5},
        'coder7': {'engine': 'llama', 'model': str(HOME / '.local/share/mseries-ai/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf'),
                  'context': 16384, 'port': 8768, 'admission_gib': 7},
        'liquid': {'engine': 'llama', 'model': str(HOME / '.local/share/mseries-ai/models/LFM2.5-1.2B-Instruct-Q4_K_M.gguf'),
                   'context': 4096, 'port': 8768, 'admission_gib': 2},
        'bonsai': {'engine': 'llama', 'model': str(HOME / '.local/share/mseries-ai/models/Ternary-Bonsai-2-9B-Q2_0.gguf'),
                   'context': 8192, 'port': 8768, 'admission_gib': 5.5},
        'coder-large': {'engine': 'llama', 'model': str(HOME / '.local/share/mseries-ai/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf'),
                  'context': 8192, 'port': 8768, 'admission_gib': 21}}}
    # Policy and selected profiles are user settings; upgrades never reset them.
    if not (CONFIG / 'profiles.json').exists():
        put(CONFIG / 'profiles.json', json.dumps(config, indent=2) + '\n')
    else:
        existing = json.loads((CONFIG / 'profiles.json').read_text())
        for name in config['profiles']:
            if name not in existing['profiles']:
                existing['profiles'][name] = config['profiles'][name]
        if args.adopt_compact_defaults:
            for name in ['everyday', 'coder', 'quality', 'coder9', 'personal']:
                existing['profiles'][name] = config['profiles'][name]
        put(CONFIG / 'profiles.json', json.dumps(existing, indent=2) + '\n')
    installed = json.loads((CONFIG / 'profiles.json').read_text())
    desktop_model = QUALITY_MODEL if installed['profiles']['everyday']['model'] == 'qwen3.5-9b-mlx-4bit' else MODEL
    for profile in ['everyday', 'quality', 'coder9', 'compact', 'compact35', 'personal', 'coder', 'coder7', 'liquid', 'bonsai']:
        unit = f'''[Unit]
Description=MSeries {profile} local model with desktop reserve
[Service]
ExecStart=/usr/bin/python3 "%h/.local/libexec/mseries-ai/model-worker.py" {profile}
Nice=10
KillMode=mixed
TimeoutStopSec=45
[Install]
WantedBy=default.target
'''
        put(HOME / f'.config/systemd/user/mseries-ai-{profile}.service', unit, 0o644)
    launcher = '''#!/usr/bin/python3
import argparse, json, os, subprocess, time, urllib.request
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--quality',action='store_true'); p.add_argument('app', choices=['desktop','personal','coding']); p.add_argument('args', nargs=argparse.REMAINDER); a=p.parse_args()
profile={'coding':'coder','personal':'everyday','desktop':'everyday'}[a.app]
if a.quality: profile='coder9' if a.app=='coding' else 'quality'
if a.app in ('desktop','personal') and subprocess.run(['systemctl','--user','is-active','--quiet','mseries-ai-personal.service']).returncode==0: profile='personal'
# One supervised worker owns the GPU/model budget at a time.
managed=['everyday','quality','coder9','compact','compact35','personal','coder','coder7','liquid','bonsai']
previous=[x for x in managed if subprocess.run(['systemctl','--user','is-active','--quiet','mseries-ai-'+x+'.service']).returncode==0]
def refused(message):
    if profile not in previous:
        subprocess.run(['systemctl','--user','stop','mseries-ai-'+profile+'.service'])
        for prior in previous: subprocess.run(['systemctl','--user','start','mseries-ai-'+prior+'.service'])
    raise SystemExit(message)
subprocess.run(['systemctl','--user','stop']+['mseries-ai-'+x+'.service' for x in managed if x!=profile],check=True)
if subprocess.run(['systemctl','--user','start','mseries-ai-'+profile+'.service']).returncode: refused('Could not start the selected model; attempted to restore the previous profile.')
cfg=json.loads((Path.home()/'.config/mseries-ai/profiles.json').read_text())['profiles'][profile]
port=cfg['port']
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for i in range(120):
    state=subprocess.run(['systemctl','--user','is-active','mseries-ai-'+profile+'.service'],capture_output=True,text=True).stdout.strip()
    if state in ('failed','inactive'): refused('Model refused, stopped for quiet limits, or failed. Previous profile restored when possible. See journalctl --user -u mseries-ai-'+profile)
    try:
        with opener.open('http://127.0.0.1:'+str(port)+'/v1/models',timeout=2) as r: catalog=json.load(r)
        ids=[m['id'] for m in catalog['data']]
        expected={'qwen3-4b-instruct-2507-4bit':'50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b','qwen3.5-4b-mseries-4bit':'32f3e8ecf65426fc3306969496342d504bfa13f3','qwen3.5-9b-mlx-4bit':'938d8919941c6e7efd3c7150eff7fe9d12afa631'}[cfg['model']]
        if not any(x==expected or x.endswith('/'+expected) for x in ids): refused('Unexpected model on local endpoint; refusing to connect the assistant.')
        break
    except (OSError,ValueError): time.sleep(1)
else: refused('Model did not become ready within 120 seconds')
h=Path.home()
if a.app in ('desktop','personal'):
    repo='Qwen3.5-4B-MLX-4bit' if expected.startswith('32f3') else 'Qwen3.5-9B-MLX-4bit'
    selected=str(h/'.cache/huggingface/hub'/('models--mlx-community--'+repo)/'snapshots'/expected)
    setup="import json,sys; from gi.repository import Gio; s=Gio.Settings.new('io.github.qwersyk.Newelle'); d=json.loads(s.get_string('llm-settings')); d['openai'].update(api='local',endpoint='http://127.0.0.1:'+sys.argv[2]+'/v1',model=sys.argv[1],models=json.dumps([[sys.argv[1],sys.argv[1]]])); s.set_string('llm-settings',json.dumps(d)); s.set_string('language-model','openai'); Gio.Settings.sync()"
    subprocess.run(['flatpak','run','--command=python3','io.github.qwersyk.Newelle','-c',setup,selected,str(port)],check=True)
    os.execvp('flatpak',['flatpak','run','io.github.qwersyk.Newelle']+a.args)
workspace=h/('Documents/Coding Assistant Quality' if a.quality else 'Documents/Coding Assistant')
workspace.mkdir(parents=True,exist_ok=True)
if not (workspace/'.crushrc').exists() or expected not in (workspace/'.crushrc').read_text(): refused('Coding profile does not match the selected model; run install-crush.py to configure the local preset.')
os.chdir(workspace)
os.environ['CRUSH_DISABLE_PROVIDER_AUTO_UPDATE']='1'
os.execv(str(h/'.local/bin/crush'),['crush']+a.args)
'''
    put(HOME / '.local/bin/mseries-assistant', launcher, 0o755)
    mcp = {'command': '/usr/bin/python3', 'args': [str(LIB / 'os-mcp.py')]}
    personal = HOME / '.local/share/mseries-assistants/personal'
    personal.mkdir(parents=True, exist_ok=True, mode=0o700)
    for app, title in [('desktop', 'Desktop Assistant'), ('personal', 'Personal Assistant'), ('coding', 'Coding Assistant')]:
        terminal = 'true' if app == 'coding' else 'false'
        put(HOME / f'.local/share/applications/mseries-{app}-assistant.desktop',
            f'[Desktop Entry]\nType=Application\nName={title}\nExec="{HOME}/.local/bin/mseries-assistant" {app}\nIcon=utilities-system-monitor\nTerminal={terminal}\nCategories=Utility;\n', 0o644)
    # Configure inside Flatpak's own settings namespace, without opening a window.
    body = '''import json,sys
from gi.repository import Gio
s=Gio.Settings.new('io.github.qwersyk.Newelle')
backup={k:s.get_value(k).print_(True) for k in s.list_keys()}
print(json.dumps(backup))
disabled=['execute_command','show_image','read_image','take_screenshot','show_video','read_file','write_file','edit','glob','list_directory','grep_search','run_subagent','schedule_task','ask_user','sleep','switch_mode','todo','activate_skill','memory_search','memory_save','memory_recall','website','rag_search_files','tool_search']
tools=json.loads(s.get_string('tools-settings'))
tools.update({k:{'enabled':False} for k in disabled})
tools.update({k:{'enabled':True,'lazy_load':False} for k in ['system_status','list_apps','list_tasks','create_assistant_task','list_calendar_events','create_assistant_event','browser_list_tabs','browser_read_page','create_mail_draft','read_mail_draft','add_minutes','get_energy','workspace_list_files','workspace_read_file','workspace_write_note','recent_faults']})
s.set_string('tools-settings',json.dumps(tools))
s.set_string('memory-model','user-summary')
s.set_int('context-max',8192)
s.set_int('context-suggested',6144)
s.set_int('max-tool-calls',6)
for k,v in {'language-model':'openai','llm-settings':json.dumps({'openai':{'api':'local','endpoint':'http://127.0.0.1:8766/v1','model':sys.argv[1],'models':json.dumps([[sys.argv[1],sys.argv[1]]]),'custom_model':True,'streaming':True,'native_tool_calling':True,'advanced_params':True,'temperature':0.2,'custom_body':json.dumps({'chat_template_kwargs':{'enable_thinking':False}})}}),'mcp-servers':json.dumps([{'type':'stdio','title':'MSeries OS','command':'/usr/bin/python3','args':[sys.argv[2]]}])}.items(): s.set_string(k,v)
for k,v in {'websearch-on':False,'tts-on':False,'memory-on':True,'secondary-llm-on':False,'auto-run':False,'auto-generate-name':False,'rag-on-documents':False,'welcome-screen-shown':True}.items(): s.set_boolean(k,v)
Gio.Settings.sync()
'''
    result = subprocess.run(['flatpak', 'run', '--command=python3', 'io.github.qwersyk.Newelle', '-c', body,
                             desktop_model, str(LIB / 'os-mcp.py')], text=True, capture_output=True, check=True)
    backup = CONFIG / 'newelle-before.json'
    if not backup.exists():
        put(backup, result.stdout)
    subprocess.run(['flatpak', 'override', '--user', '--talk-name=org.freedesktop.Flatpak', 'io.github.qwersyk.Newelle'], check=True)
    # Newelle caches schemas by command/args. Our renamed tools must be fetched
    # before its controller builds the first request; retain other MCP servers.
    invalidate_mcp_cache()
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    print('Configured local Desktop, Personal and Coding Assistant launchers; no windows opened.')


if __name__ == '__main__':
    main()
