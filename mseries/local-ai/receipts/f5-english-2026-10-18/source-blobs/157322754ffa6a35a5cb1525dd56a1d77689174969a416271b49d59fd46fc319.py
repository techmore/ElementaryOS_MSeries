"""Read-only owner-session preservation check after isolated installed fixtures."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

work = Path(__file__).resolve().parent
out = work / 'f5-postdeploy-v1'
if (out / 'receipt.json').exists():
    raise SystemExit('Preserve the existing receipt; do not overwrite it')
base = Path.home() / '.local/share/mseries/stream'
sys.path.insert(0, str(base))
from dictation_resources import snapshot
from dictation_status import read_status

def command(*args):
    return subprocess.check_output(args, text=True, timeout=10).strip()

baseline = json.loads((work / 'f5-deployment-baseline-private.json').read_text())
values = [command(*args) for args in [
    ['gsettings', 'get', 'org.gnome.desktop.input-sources', 'sources'],
    ['gsettings', 'get', 'org.gnome.desktop.input-sources', 'current'],
    ['gsettings', 'get', 'org.gnome.desktop.interface', 'gtk-im-module'],
    ['ibus', 'engine']]]
checks = {'input_preferences_preserved': hashlib.sha256(json.dumps(values).encode()).hexdigest() == baseline['baseline_input_fingerprint'],
          'kernel_preserved': os.uname().release == baseline['kernel']}
for unit in ['mseries-stream-dictate.service', 'mseries-dictation-input.service', 'mseries-ai-everyday.service']:
    checks[unit + '-active-enabled'] = command('systemctl', '--user', 'is-active', unit) == 'active' and command('systemctl', '--user', 'is-enabled', unit) == 'enabled'
checks['default_4b_pid_preserved'] = int(command('systemctl', '--user', 'show', 'mseries-ai-everyday.service', '-p', 'MainPID', '--value')) == baseline['default_ai_pid']
speech_pid = int(command('systemctl', '--user', 'show', 'mseries-stream-dictate.service', '-p', 'MainPID', '--value'))
status = read_status()
checks['same_listener_ready'] = speech_pid == 277045 and status is not None and status['pid'] == speech_pid and status['phase'] == 'ready' and status['output'] == 'ibus' and status['backend'] == 'cpu'
checks['bridge_ready'] = command('/usr/bin/python3', str(base / 'dictation-input-client.py'), 'ready') == ''
sample = snapshot()
checks['quiet_reserve_at_final_observation'] = sample['available_bytes'] >= 6 * 1024**3 and max(sample['fans_rpm'].values(), default=9999) < 2700 and max(sample['temperatures_c'].values(), default=999) < 63
cases = []
attempts = []
for cohort in ['f5-installed-v1', 'f5-installed-v2']:
    for path in sorted((work / cohort).glob('*/receipt.json')):
        row = json.loads(path.read_text())
        cases.append({'cohort': cohort, 'app': path.parent.name, 'passed': row.get('passed'), 'complete': row.get('complete'), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    attempts.extend(json.loads(path.read_text()) for path in (work / cohort).glob('*-attempt.json'))
checks['seven_distinct_installed_cases_passed'] = len(cases) == 7 and len({row['app'] for row in cases}) == 7 and all(row['complete'] and row['passed'] for row in cases)
checks['no_guard_interruption'] = all(row.get('interruption') is None for row in attempts)
row = {'complete': True, 'passed': all(checks.values()), 'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'checks': checks, 'source_commit': '5c26ff6c2ff38c89c401c0d109a61244146868d8', 'installed_cases': cases,
       'scope': 'One installed GTK4 public-file ASR smoke plus six no-inference app fixtures; initial three argparse failures remain unscored. Post-fixture read-only service/settings check; no microphone/playback/owner window.',
       'resources': {'min_available_bytes': min(row['resources']['min_available_bytes'] for row in attempts),
                     'max_fan_rpm': max(row['resources']['max_fan_rpm'] for row in attempts),
                     'max_temp_c': max(row['resources']['max_temp_c'] for row in attempts)},
       'resource_scope': 'Half-second supervisor samples with active guard; includes preserved setup attempts. No acoustic/power claim.',
       'unstarted_argv_failures_preserved': 3, 'microphone_recorded': False, 'audio_played': False,
       'services_changed_by_verification': False, 'raw_settings_exported': False}
out.mkdir(mode=0o700, exist_ok=True)
(out / 'receipt.json').write_text(json.dumps(row, indent=2) + '\n')
print(json.dumps({'passed': row['passed'], 'checks': checks, 'resources': row['resources']}))
raise SystemExit(0 if row['passed'] else 1)
