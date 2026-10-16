"""Read-only machine telemetry and conservative AI admission policy."""
import json
from pathlib import Path
import time

GIB = 1024 ** 3
DEFAULT_POLICY = {'reserve_gib': 6, 'max_fan_rpm': 3500, 'max_temp_c': 80}


def runtime_prefix(home=None):
    user = (Path.home() if home is None else home) / '.local/share/mlx-omarchy'
    # A factory user's catalog/cache creates this directory without installing
    # a runtime. Select the private user runtime only when it is complete.
    if (user / 'venv/bin/python').is_file() and (user / 'vulkan/honeykrisp_icd.aarch64.json').is_file():
        return user
    return Path('/usr/lib/omarchy-mlx')


def number(path):
    try:
        return float(path.read_text().strip())
    except (OSError, ValueError):
        return None


def snapshot(root=Path('/')):
    mem = {}
    for line in (root / 'proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        mem[key] = int(value.split()[0]) * 1024
    fans, temps, power = {}, {}, None
    for hw in (root / 'sys/class/hwmon').glob('hwmon*'):
        for kind, result, scale in [('fan', fans, 1), ('temp', temps, 1000)]:
            for path in hw.glob(kind + '*_input'):
                value = number(path)
                if value is None:
                    continue
                label = path.with_name(path.name.replace('_input', '_label'))
                name = label.read_text().strip() if label.exists() else hw.name + '/' + path.name
                value /= scale
                if kind == 'fan' or 0 < value < 120:
                    result[name] = value
        for label in hw.glob('power*_label'):
            if label.read_text().strip() == 'Total System Power':
                raw = number(label.with_name(label.name.replace('_label', '_input')))
                if raw is not None:
                    power = raw / 1_000_000
    pressure = {}
    for name in ['cpu', 'memory', 'io']:
        path = root / 'proc/pressure' / name
        pressure[name] = path.read_text().strip() if path.exists() else None
    return {'time': time.time(), 'available_bytes': mem['MemAvailable'],
            'total_bytes': mem['MemTotal'], 'swap_used_bytes': mem.get('SwapTotal', 0) - mem.get('SwapFree', 0),
            'fans_rpm': fans, 'temperatures_c': temps, 'power_w': power, 'pressure': pressure}


def violations(sample, policy=None, extra_bytes=0):
    policy = DEFAULT_POLICY if policy is None else policy
    reasons = []
    if not sample['fans_rpm'] or not sample['temperatures_c']:
        reasons.append('fan or temperature telemetry unavailable; quiet limits cannot be checked')
    if sample['available_bytes'] - extra_bytes < policy['reserve_gib'] * GIB:
        reasons.append('desktop memory reserve would be crossed')
    if max(sample['fans_rpm'].values(), default=0) > policy['max_fan_rpm']:
        reasons.append('fan RPM exceeds the quiet profile limit')
    if max(sample['temperatures_c'].values(), default=0) > policy['max_temp_c']:
        reasons.append('temperature exceeds the quiet profile limit')
    return reasons


def cooling_action(sample, paused, policy=None, paused_seconds=0):
    policy = DEFAULT_POLICY if policy is None else policy
    fan = max(sample['fans_rpm'].values(), default=0)
    temp = max(sample['temperatures_c'].values(), default=0)
    if not paused and (fan >= policy.get('cool_fan_rpm', 2800) or temp >= policy.get('cool_temp_c', 70)):
        return 'pause'
    if paused and fan <= policy.get('resume_fan_rpm', 2600) and temp <= policy.get('resume_temp_c', 65):
        return 'resume'
    if (paused and paused_seconds >= policy.get('max_cooling_s', 30)
            and fan <= policy['max_fan_rpm'] - 300 and temp <= policy.get('resume_temp_c', 65)):
        return 'burst'
    return None


if __name__ == '__main__':
    print(json.dumps(snapshot(), indent=2))
