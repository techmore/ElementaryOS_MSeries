#!/usr/bin/python3
"""Install local assistant launchers, model policy, MCP adapters and Newelle settings."""
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
HOME = Path.home()
LIB = HOME / '.local/libexec/mseries-ai'
CONFIG = HOME / '.config/mseries-ai'
MODEL = str(HOME / '.cache/huggingface/hub/models--mlx-community--Qwen3.5-9B-MLX-4bit/snapshots/938d8919941c6e7efd3c7150eff7fe9d12afa631')


def put(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() != value:
        backup = path.with_name(path.name + '.before-mseries')
        if not backup.exists():
            shutil.copy2(path, backup)
    path.write_text(value)
    path.chmod(mode)


def main():
    LIB.mkdir(parents=True, exist_ok=True)
    for name in ['machine.py', 'model-worker.py', 'os-mcp.py', 'brief.py']:
        shutil.copy2(HERE / name, LIB / name)
    config = {'policy': {'reserve_gib': 6, 'max_fan_rpm': 3500, 'max_temp_c': 80,
                         'cool_fan_rpm': 2700, 'resume_fan_rpm': 2600, 'burst_s': 3, 'sample_s': 1}, 'profiles': {
        'everyday': {'engine': 'mlx', 'model': 'qwen3.5-9b-mlx-4bit', 'context': 8192, 'port': 8766, 'admission_gib': 7.5},
        'compact': {'engine': 'mlx', 'model': 'qwen3-4b-instruct-2507-4bit', 'context': 4096, 'port': 8766, 'admission_gib': 4.5},
        'compact35': {'engine': 'mlx', 'model': 'qwen3.5-4b-mseries-4bit', 'context': 16384, 'port': 8768, 'admission_gib': 5.5},
        'personal': {'engine': 'mlx', 'model': 'qwen3.5-9b-mlx-4bit', 'context': 64000, 'port': 8766,
                     'prompt_cache_size': 1, 'admission_gib': 11},
        'coder': {'engine': 'mlx', 'model': 'qwen3.5-9b-mlx-4bit',
                  'context': 16384, 'port': 8768, 'admission_gib': 8},
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
        put(CONFIG / 'profiles.json', json.dumps(existing, indent=2) + '\n')
    for profile in ['everyday', 'compact', 'compact35', 'personal', 'coder', 'coder7', 'liquid', 'bonsai']:
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
p=argparse.ArgumentParser(); p.add_argument('app', choices=['desktop','personal','hermes','coding']); p.add_argument('args', nargs=argparse.REMAINDER); a=p.parse_args()
profile={'coding':'coder','hermes':'personal','personal':'everyday','desktop':'everyday'}[a.app]
if a.app in ('desktop','personal') and subprocess.run(['systemctl','--user','is-active','--quiet','mseries-ai-personal.service']).returncode==0: profile='personal'
# One supervised worker owns the GPU/model budget at a time.
subprocess.run(['systemctl','--user','stop']+['mseries-ai-'+x+'.service' for x in ['everyday','compact','compact35','personal','coder','coder7','liquid','bonsai'] if x!=profile],check=True)
subprocess.run(['systemctl','--user','start','mseries-ai-'+profile+'.service'],check=True)
port=8768 if profile=='coder' else 8766
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for i in range(120):
    state=subprocess.run(['systemctl','--user','is-active','mseries-ai-'+profile+'.service'],capture_output=True,text=True).stdout.strip()
    if state in ('failed','inactive'): raise SystemExit('Model refused, stopped for quiet limits, or failed. See journalctl --user -u mseries-ai-'+profile)
    try:
        with opener.open('http://127.0.0.1:'+str(port)+'/v1/models',timeout=2) as r: catalog=json.load(r)
        ids=[m['id'] for m in catalog['data']]
        expected='50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b' if profile=='compact' else '938d8919941c6e7efd3c7150eff7fe9d12afa631'
        if not any(x==expected or x.endswith('/'+expected) for x in ids): raise SystemExit('Unexpected model on local endpoint; refusing to connect the assistant.')
        break
    except (OSError,ValueError): time.sleep(1)
else: raise SystemExit('Model did not become ready within 120 seconds')
h=Path.home()
if a.app in ('desktop','personal'): os.execvp('flatpak',['flatpak','run','io.github.qwersyk.Newelle']+a.args)
if a.app=='hermes':
    os.environ['HERMES_HOME']=str(h/'.local/share/mseries-assistants/personal')
    os.environ['OPENAI_API_KEY']='local'
    (h/'Documents/Assistant Workspace').mkdir(parents=True,exist_ok=True)
    os.chdir(h/'Documents/Assistant Workspace')
    os.execv(str(h/'.local/share/mseries-assistants/hermes/venv/bin/hermes'),['hermes']+a.args)
(h/'Documents/Coding Assistant').mkdir(parents=True,exist_ok=True)
os.chdir(h/'Documents/Coding Assistant')
os.environ['CRUSH_DISABLE_PROVIDER_AUTO_UPDATE']='1'
os.execv(str(h/'.local/bin/crush'),['crush']+a.args)
'''
    put(HOME / '.local/bin/mseries-assistant', launcher, 0o755)
    mcp = {'command': '/usr/bin/python3', 'args': [str(LIB / 'os-mcp.py')]}
    personal = HOME / '.local/share/mseries-assistants/personal'
    personal.mkdir(parents=True, exist_ok=True, mode=0o700)
    hermes = {'model': {'provider': 'custom', 'base_url': 'http://127.0.0.1:8766/v1',
                        'default': MODEL, 'context_length': 64000},
              'agent': {'reasoning_effort': 'none', 'max_turns': 12},
              'platform_toolsets': {'cli': ['memory', 'session_search']},
              'memory': {'memory_enabled': True, 'user_profile_enabled': True},
              'mcp_servers': {'mseries-os': mcp}, 'fallback_model': [],
              'tools': {'tool_search': {'enabled': 'off'}}}
    if not (personal / 'config.yaml').exists():
        # JSON is valid YAML; no extra host Python dependencies are needed.
        put(personal / 'config.yaml', json.dumps(hermes, indent=2) + '\n')
    for app, title in [('desktop', 'Desktop Assistant'), ('personal', 'Personal Assistant'), ('hermes', 'Hermes Assistant (Experimental)'), ('coding', 'Coding Assistant')]:
        terminal = 'true' if app in ('hermes', 'coding') else 'false'
        put(HOME / f'.local/share/applications/mseries-{app}-assistant.desktop',
            f'[Desktop Entry]\nType=Application\nName={title}\nExec="{HOME}/.local/bin/mseries-assistant" {app}\nIcon=utilities-system-monitor\nTerminal={terminal}\nCategories=Utility;\n', 0o644)
    # Configure inside Flatpak's own settings namespace, without opening a window.
    body = '''import json,sys
from gi.repository import Gio
s=Gio.Settings.new('io.github.qwersyk.Newelle')
backup={k:s.get_value(k).print_(True) for k in s.list_keys()}
print(json.dumps(backup))
disabled=['execute_command','show_image','read_image','take_screenshot','show_video','read_file','write_file','edit','glob','list_directory','grep_search','run_subagent','schedule_task','ask_user','sleep','switch_mode','todo','activate_skill','memory_search','memory_save','rag_search_files','tool_search']
tools=json.loads(s.get_string('tools-settings'))
tools.update({k:{'enabled':False} for k in disabled})
tools.update({k:{'enabled':True,'lazy_load':False} for k in ['system_status','list_apps','list_tasks','list_calendar_events','add_minutes','get_energy','workspace_list_files','workspace_read_file','workspace_write_note','recent_faults']})
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
                             MODEL, str(LIB / 'os-mcp.py')], text=True, capture_output=True, check=True)
    backup = CONFIG / 'newelle-before.json'
    if not backup.exists():
        put(backup, result.stdout)
    subprocess.run(['flatpak', 'override', '--user', '--talk-name=org.freedesktop.Flatpak', 'io.github.qwersyk.Newelle'], check=True)
    # Newelle caches schemas by command/args. Our renamed tools must be fetched
    # before its controller builds the first request; retain other MCP servers.
    cache = HOME / '.var/app/io.github.qwersyk.Newelle/cache/extensions_cache/mcp_tool_cache.json'
    if cache.exists():
        try:
            metadata = json.loads(cache.read_text())
            identifier = 'stdio:/usr/bin/python3:' + str(LIB / 'os-mcp.py')
            if isinstance(metadata, dict) and identifier in metadata:
                del metadata[identifier]
                put(cache, json.dumps(metadata, indent=2) + '\n')
        except (OSError, ValueError):
            pass  # Newelle itself ignores an unreadable cache and fetches schemas.
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    print('Configured local Desktop, Personal and Coding Assistant launchers; no windows opened.')


if __name__ == '__main__':
    main()
