#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit a prepared trial against its baseline and installed candidate bytes; read only."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat

spec = importlib.util.spec_from_file_location('trial', Path(__file__).with_name('prepare-trial-initrd.py'))
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


def entries(image):
    prefix, main = trial.split_image(image)
    rows, _ = trial.newc.parse(gzip.decompress(main))
    return prefix, {trial.newc.canonical(n): (v, d) for n, v, d in rows}


def audit(baseline, candidate, module_tree):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{1,127}', module_tree.name):
        raise ValueError('invalid module release name')
    before_prefix, before = entries(baseline)
    after_prefix, after = entries(candidate)
    if before_prefix != after_prefix:
        raise ValueError('early firmware archive changed')
    excluded = lambda n: n.startswith('usr/lib/modules/') or n == 'modlist.txt'
    if {n: v for n, v in before.items() if not excluded(n)} != {n: v for n, v in after.items() if not excluded(n)}:
        raise ValueError('nonmodule unlock/userspace entries changed')
    for required in ('init', 'init_functions', 'config', 'hooks/encrypt', 'usr/bin/cryptsetup'):
        if required not in after:
            raise ValueError('missing required unlock entry: ' + required)
    prefix = 'usr/lib/modules/' + module_tree.name + '/'
    count = 0
    for name, (values, data) in after.items():
        if name.startswith('usr/lib/modules/') and not (name.startswith(prefix) or name == prefix.rstrip('/')):
            raise ValueError('foreign kernel release in candidate archive')
        if name.startswith(prefix) and stat.S_ISREG(values[1]) and '/kernel/' in name:
            path = module_tree / name[len(prefix):]
            if not path.is_file() or path.read_bytes() != data:
                raise ValueError('candidate module bytes differ: ' + name)
            count += 1
    if not count:
        raise ValueError('no candidate modules')
    dependency_name = prefix + 'modules.dep'
    if dependency_name not in after:
        raise ValueError('missing module dependency index')
    for row in after[dependency_name][1].decode().splitlines():
        module, separator, dependencies = row.partition(':')
        if not separator or any(prefix + p not in after for p in [module, *dependencies.split()]):
            raise ValueError('module dependency missing from archive')
    return {'schema': 1, 'status': 'offline archive audit passed; not a boot qualification',
            'baseline_sha256': hashlib.sha256(baseline).hexdigest(),
            'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
            'candidate_release': module_tree.name, 'verified_module_count': count,
            'early_prefix_unchanged': True, 'nonmodule_entries_unchanged': True,
            'module_bytes_match_candidate_tree': True, 'dependency_files_present': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'module-tree'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.baseline.read_bytes(), args.candidate.read_bytes(), args.module_tree), indent=2))
