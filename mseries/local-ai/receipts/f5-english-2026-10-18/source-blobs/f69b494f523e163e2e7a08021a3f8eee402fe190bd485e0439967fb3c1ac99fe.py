"""Use the shared machine policy for speech admission and active-session guards."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if not (HERE / 'machine.py').exists():
    sys.path.insert(0, str(HERE.parent / 'local-ai'))
from machine import DEFAULT_POLICY, snapshot, violations


def load_policy():
    policy = dict(DEFAULT_POLICY)
    path = Path.home() / '.config/mseries-ai/profiles.json'
    if path.exists(): policy.update(json.loads(path.read_text())['policy'])
    return policy


def reasons(policy, extra_bytes=0, sample=None):
    sample = snapshot() if sample is None else sample
    found = violations(sample, policy, extra_bytes)
    # Speech's quiet boundary is inclusive, even if the shared desktop policy
    # admits its exact upper bound. Do not alter other workloads' policy.
    if max(sample.get('fans_rpm', {}).values(), default=9999) >= min(2700, policy['max_fan_rpm']):
        found.append('speech fan boundary')
    if max(sample.get('temperatures_c', {}).values(), default=999) >= min(63, policy['max_temp_c']):
        found.append('speech temperature boundary')
    return found
