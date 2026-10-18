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
    return violations(snapshot() if sample is None else sample, policy, extra_bytes)
