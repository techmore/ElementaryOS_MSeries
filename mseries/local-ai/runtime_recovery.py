"""Recover abandoned pinned-runtime CLI reservations; never clear live/pair leases."""
import json
import os
from pathlib import Path
import re
import subprocess


def dead_process_group(pid):
    if pid <= 1: return False
    for probe in [os.kill, os.killpg]:
        try: probe(pid, 0)
        except ProcessLookupError: continue
        except PermissionError: return False
        else: return False
    return True


def stale_cli_entries(rows, dead=dead_process_group):
    found = []
    for name, entry in rows.items():
        owner = entry.get('owner') if isinstance(entry, dict) else None
        match = re.fullmatch(r'pid([0-9]+)-[0-9a-f]{12}', owner or '')
        if not match or name != 'mlx-lm-launch-' + owner or any(entry.get(k) is not None for k in ['parent', 'claimed', 'pair_id']): continue
        if dead(int(match[1])): found.append((name, owner))
    return found


def recover(prefix):
    data_home = Path(os.environ.get('MLX_OMARCHY_HOME', Path.home() / '.local/share/mlx-omarchy'))
    path = data_home / 'reservations.json'
    if not path.exists(): return 0
    # Run the pinned upstream owner-checked transaction in its own Python environment.
    script = '''import json,sys
from pathlib import Path
from mlx_omarchy_serve import budget
from runtime_recovery import stale_cli_entries
home=Path(sys.argv[1]); removed=0
for name,owner in stale_cli_entries(budget.load_reservations(home)):
    # Recheck process/group state immediately before the owner-checked clear.
    if (name,owner) in stale_cli_entries({name:budget.load_reservations(home).get(name)}):
        removed+=bool(budget.clear_reservation(name,home=home,owner=owner))
print(json.dumps({'recovered':removed}))
'''
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(Path(__file__).parent), str(prefix), os.environ.get('PYTHONPATH', '')]))
    result = subprocess.run([str(prefix / 'venv/bin/python'), '-c', script, str(data_home)], env=env,
                            capture_output=True, text=True, timeout=15)
    if result.returncode: raise RuntimeError('Pinned runtime reservation recovery failed; no memory policy was relaxed')
    return json.loads(result.stdout)['recovered']
