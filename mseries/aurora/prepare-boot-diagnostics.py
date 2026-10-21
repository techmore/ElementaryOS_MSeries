#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare a separate mkinitcpio diagnostic image without changing boot files."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

spec = importlib.util.spec_from_file_location('trial', Path(__file__).with_name('prepare-trial-initrd.py'))
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)

TRACE = '''
# Diagnostic markers contain stage names only, never shell command tracing.
mseries_boot_trace() {
    local trace_status="${2:-0}"
    printf '<6>mseries-boot: %s\\n' "$1" >/dev/kmsg 2>/dev/null || :
    printf 'mseries-boot: %s\\n' "$1" >/dev/console 2>/dev/null || :
    return "$trace_status"
}
'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('unsupported or already instrumented mkinitcpio source')
    return text.replace(old, new, 1)


def instrument(init, functions):
    if 'mseries_boot_trace' in init + functions:
        raise ValueError('already instrumented')
    functions = replace_once(functions, '        "$fn"\n',
                             '        mseries_boot_trace "begin $fn $hook"\n'
                             '        "$fn"\n'
                             '        mseries_boot_trace "end $fn $hook status=$?" "$?"\n')
    functions += TRACE
    for old, new in (
        ('mount_setup\n', 'mount_setup\nmseries_boot_trace "initramfs entered"\n'),
        ('    modprobe -qab ${earlymodules//,/ } $MODULES\n',
         '    mseries_boot_trace "begin configured modules"\n'
         '    modprobe -qab ${earlymodules//,/ } $MODULES\n'
         '    mseries_boot_trace "end configured modules status=$?" "$?"\n'),
        ('if rootdev="$(resolve_device "$root")"; then\n',
         'mseries_boot_trace "begin root device resolution"\n'
         'if rootdev="$(resolve_device "$root")"; then\n'),
        ('"$mount_handler" /sysroot\n',
         'mseries_boot_trace "begin root mount"\n'
         '"$mount_handler" /sysroot\n'
         'mseries_boot_trace "end root mount status=$?" "$?"\n'),
        ('rdlogger_stop\n', 'mseries_boot_trace "before switch_root"\nrdlogger_stop\n'),
    ):
        init = replace_once(init, old, new)
    return init, functions


def prepare(source, output, report):
    for path in (output, report):
        if path.exists() or path.is_symlink():
            raise ValueError('output/report must be new paths')
        if any(path.resolve().is_relative_to(Path(root)) for root in ('/boot', '/usr/lib/modules')):
            raise ValueError('use a private work directory, not live boot/module paths')
    if output.resolve() == report.resolve():
        raise ValueError('output and report must differ')
    original = source.read_bytes()
    prefix, compressed = trial.split_image(original)
    rows, trailer = trial.newc.parse(gzip.decompress(compressed))
    entries = {trial.newc.canonical(n): (v, d) for n, v, d in rows}
    for name in ('init', 'init_functions'):
        if name not in entries or not stat.S_ISREG(entries[name][0][1]) or entries[name][0][4] != 1:
            raise ValueError('expected standalone regular init/init_functions')
    init, functions = instrument(entries['init'][1].decode(), entries['init_functions'][1].decode())
    replacements = {'init': init.encode(), 'init_functions': functions.encode()}
    updated = []
    for name, values, data in rows:
        key = trial.newc.canonical(name)
        if key in replacements:
            values = values.copy()
            data = replacements[key]
            values[6] = len(data)
        updated.append((name, values, data))
    encoded = trial.newc.encode(updated, trailer)
    checked = {trial.newc.canonical(n): (v, d) for n, v, d in trial.newc.parse(encoded)[0]}
    unchanged = all(checked[n] == item for n, item in entries.items() if n not in replacements)
    if not unchanged:
        raise ValueError('unrelated archive entry changed')
    result = prefix + gzip.compress(encoded, compresslevel=6, mtime=0)
    receipt = {
        'schema': 1, 'status': 'offline diagnostic image only; not installed or booted',
        'source_sha256': hashlib.sha256(original).hexdigest(),
        'diagnostic_sha256': hashlib.sha256(result).hexdigest(),
        'modified_entries': sorted(replacements), 'all_other_entries_unchanged': unchanged,
        'early_prefix_unchanged': result[:len(prefix)] == prefix,
        'suggested_additional_arguments': ['initcall_debug', 'ignore_loglevel', 'log_buf_len=8M',
                                           'plymouth.enable=0', 'rd.log=kmsg|console|file'],
        'limits': 'No persistent evidence is guaranteed before root mount. Capture visible last messages if a future authorized trial stalls. No driver fix or hardware boot qualification.',
    }
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(result)
    with report.open('x') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output, args.report), indent=2))
