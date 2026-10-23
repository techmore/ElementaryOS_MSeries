#!/usr/bin/env python3
"""Keep superseded PR checks from consuming the account's runner capacity."""
from pathlib import Path
import sys

import yaml

GROUP = "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
CANCEL = "${{ github.event_name == 'pull_request' }}"
ROOT = Path(__file__).resolve().parents[2]


def load(path):
    # BaseLoader preserves GitHub's `on` key (YAML 1.1 treats it as a boolean).
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader)


def check(workflows):
    errors = []
    names = set()
    for path, workflow in workflows:
        triggers = workflow.get('on', {})
        if 'pull_request' not in triggers:
            continue
        name = workflow.get('name')
        normalized = name.casefold() if isinstance(name, str) else None
        if not normalized or normalized in names:
            errors.append(f'{path}: PR workflow names must be present and unique')
        names.add(normalized)
        policy = workflow.get('concurrency', {})
        if not isinstance(policy, dict) or policy.get('group') != GROUP:
            errors.append(f'{path}: concurrency must isolate workflow and PR, falling back to ref')
        if not isinstance(policy, dict) or policy.get('cancel-in-progress') != CANCEL:
            errors.append(f'{path}: only superseded pull_request runs may be cancelled')
    return errors


def repository_workflows():
    paths = sorted((ROOT / '.github/workflows').glob('*.y*ml'))
    return [(str(path.relative_to(ROOT)), load(path)) for path in paths]


def main():
    errors = check(repository_workflows())
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print('All PR workflows isolate and cancel superseded PR runs.')
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
