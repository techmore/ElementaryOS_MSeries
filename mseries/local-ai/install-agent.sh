#!/usr/bin/env bash
# ARM64 Crush client for the existing private MLX runtime. Does not start models.
set -euo pipefail
[[ $(uname -m) == aarch64 ]] || { echo 'Requires Linux ARM64.' >&2; exit 1; }
launcher="$HOME/.local/bin/mlx-omarchy-serve"
model="$HOME/.cache/huggingface/hub/models--mlx-community--Qwen3.5-9B-MLX-4bit/snapshots/938d8919941c6e7efd3c7150eff7fe9d12afa631"
[[ -x "$launcher" && -f "$model/config.json" ]] || { echo 'Prepare the MLX runtime and pinned Qwen 9B model first.' >&2; exit 1; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$script_dir/configure-prefill.py" "$HOME/.local/share/mlx-omarchy/mlx_omarchy_serve/__main__.py"
workspace="$HOME/Documents/Local Agent"
[[ ! -e "$workspace/.crushrc" ]] || { echo 'Existing agent configuration retained; inspect before reinstalling.' >&2; exit 1; }
python3 - <<'PY'
import hashlib, io, tarfile, urllib.request
from pathlib import Path
url = 'https://github.com/charmbracelet/crush/releases/download/v0.98.1/crush_0.98.1_Linux_arm64.tar.gz'
expected = '098e875c1d9501822d08ef14ab094f24cfc87396385af5402994bf741a673b99'
with urllib.request.urlopen(url, timeout=60) as response:
    data = response.read()
if hashlib.sha256(data).hexdigest() != expected:
    raise SystemExit('Crush archive checksum mismatch')
with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
    for name, target in [('crush', Path.home()/'.local/bin/crush'),
                         ('LICENSE.md', Path.home()/'.local/share/crush/LICENSE.md')]:
        matches = [m for m in archive.getmembers() if m.isfile() and Path(m.name).name == name]
        if len(matches) != 1:
            raise SystemExit(f'Archive has unexpected {name} entries')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.extractfile(matches[0]).read())
        target.chmod(0o755 if name == 'crush' else 0o644)
PY
mkdir -p "$workspace" "$HOME/.config/systemd/user" "$HOME/.local/share/applications"
python3 - "$workspace" "$model" "$launcher" <<'PY'
from pathlib import Path
import json, shlex, sys
workspace, model, launcher = sys.argv[1:]
home = Path.home()
catalog = json.loads((home/'.local/share/mlx-omarchy/mlx_omarchy_serve/catalog.json').read_text())
entries = catalog['models']
entry = next(e for e in entries if e['id'] == 'qwen3.5-9b-mlx-4bit')
if entry['revision'] != '938d8919941c6e7efd3c7150eff7fe9d12afa631':
    raise SystemExit('Runtime catalog changed; review model revision before installing')
ref = 'mseries/' + model
rc = '''# Managed local agent configuration, Crush v0.98.1.
option default-providers false
option provider-auto-update false
option metrics false
option auto-lsp false
option request-timeout 180
permissions deny lsp_diagnostics lsp_references lsp_definition lsp_symbols lsp_call_hierarchy lsp_rename lsp_replace_symbol lsp_restart sourcegraph crush_info crush_logs
provider add mseries --name 'M1 Pro local GPU' --type openai-compat \\
  --base-url http://127.0.0.1:8080/v1 --api-key local \\
  --extra-body '{"chat_template_kwargs":{"enable_thinking":false}}'
'''
rc += f'model add {shlex.quote(ref)} --name "Qwen 3.5 9B local" --context-window 32768 --default-max-tokens 2048\n'
rc += f'model large {shlex.quote(ref)} --max-tokens 2048\n'
rc += f'model small {shlex.quote(ref)} --max-tokens 1024\n'
Path(workspace, '.crushrc').write_text(rc)
# Escape systemd percent specifiers and quoted argument characters.
def unit_arg(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
unit = f'''[Unit]
Description=MSeries local Qwen agent model
[Service]
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
Environment=HF_HUB_DISABLE_TELEMETRY=1
ExecStart={unit_arg(launcher)} serve qwen3.5-9b-mlx-4bit --context 32768 --prompt-cache-size 1 --host 127.0.0.1 --port 8080 --offline --yes
TimeoutStopSec=30
SuccessExitStatus=143
'''
(home/'.config/systemd/user/mseries-agent-model.service').write_text(unit)
wrapper = '''#!/usr/bin/env bash
set -euo pipefail
systemctl --user start mseries-agent-model.service
python3 - <<'READY'
import json, time, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    try:
        with opener.open('http://127.0.0.1:8080/v1/models', timeout=2) as response:
            models = json.load(response).get('data', [])
        if not any(m.get('id', '').endswith('938d8919941c6e7efd3c7150eff7fe9d12afa631') for m in models):
            raise SystemExit('Port 8080 does not serve the configured Qwen model.')
        break
    except (OSError, ValueError):
        time.sleep(1)
else:
    raise SystemExit('Model not ready. Inspect: journalctl --user -u mseries-agent-model -n 30')
READY
cd -- "$HOME/Documents/Local Agent"
export CRUSH_DISABLE_PROVIDER_AUTO_UPDATE=1
exec "$HOME/.local/bin/crush" "$@"
'''
path = home/'.local/bin/mseries-agent'
path.write_text(wrapper)
path.chmod(0o755)
desktop = f'''[Desktop Entry]
Type=Application
Name=Local Agent
Comment=Use Qwen on the Apple GPU with Crush
Exec=io.elementary.terminal --new-window -- "{home}/.local/bin/mseries-agent"
Icon=utilities-terminal
Terminal=false
Categories=Utility;
'''
(home/'.local/share/applications/mseries-agent.desktop').write_text(desktop)
PY
systemctl --user daemon-reload
echo 'Installed Crush 0.98.1 and Local Agent. Model service is not started by this installer.'
echo 'Open Local Agent in Applications; stop its model with systemctl --user stop mseries-agent-model.'
