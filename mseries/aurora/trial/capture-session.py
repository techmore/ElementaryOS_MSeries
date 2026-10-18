#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Once-per-boot, non-disruptive evidence capture for an explicitly staged trial."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import qualification as q


def cpu():
    return [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]


def inventory():
    return {
        'input_names': sorted({q.read(p) for p in Path('/sys/class/input').glob('event*/device/name') if q.read(p)}),
        'network': {p.name: {'state': q.read(p / 'operstate'), 'carrier': q.read(p / 'carrier')}
                    for p in Path('/sys/class/net').glob('*')},
        'bluetooth_controllers': [p.name for p in Path('/sys/class/bluetooth').glob('hci*')],
        'temperatures': {p.name: {'name': q.read(p / 'name'), 'inputs_millicelsius': {t.name: q.number(t) for t in p.glob('temp*_input')}}
                         for p in Path('/sys/class/hwmon').glob('hwmon*')},
        'load_average': Path('/proc/loadavg').read_text().split()[:3],
        'scope': 'Read-only presence/state inventory; not input/network/radio/thermal acceptance',
    }


def capture(config_path):
    os.umask(0o077)
    config = json.loads(config_path.read_text())
    release = q.read('/proc/sys/kernel/osrelease')
    profile = config['profiles'].get(release)
    if profile is None:
        print('Kernel is outside the staged baseline/candidate pair; no test run')
        return
    boot_id = q.read('/proc/sys/kernel/random/boot_id')
    output = Path(config['output']) / release / boot_id
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (output / '.capture.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (output / 'complete.json').exists():
            print(f'Already captured this boot: {output}')
            return
        status = {'schema': 1, 'kernel_release': release, 'boot_id': boot_id, 'profile': profile['role'],
                  'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'capturing',
                  'scenario': 'normal owner desktop; uncontrolled workloads; observational, not matched A/B'}
        def save_status():
            temporary = output / 'status.json.new'
            temporary.write_text(json.dumps(status, indent=2) + '\n')
            temporary.replace(output / 'status.json')
        save_status()
        try:
            image, boot_image = Path(profile['kernel_image']), Path(config['boot_image'])
            if q.digest(image) != profile['kernel_image_sha256'] or q.digest(boot_image) != config['boot_image_sha256']:
                raise ValueError('staged kernel/shared boot payload identity changed')
            live = q.live_kernel_identity('/sys/kernel/notes', image)
            if not live['kernel_image_matches_live_build_id']:
                raise ValueError('running build ID does not match staged kernel image')
            for name, expected in profile['module_hashes'].items():
                if q.digest(Path('/usr/lib/modules') / release / name) != expected:
                    raise ValueError('staged module/DTB identity changed: ' + name)
            while float(Path('/proc/uptime').read_text().split()[0]) < config.get('minimum_uptime_s', 300):
                time.sleep(5)
            deadline = time.monotonic() + 120
            while not q.read_active().get('available'):
                if time.monotonic() >= deadline:
                    raise ValueError('active display/refresh context unavailable after login')
                time.sleep(5)
            journal = output / 'kernel-journal.jsonl'
            with journal.open('w') as stream:
                subprocess.run(['journalctl', '-b', '-k', '-o', 'json', '--no-pager'], stdout=stream, check=True)
            before, state_before = cpu(), inventory()
            receipt_path = output / 'hardware.json'
            if receipt_path.exists():
                raise ValueError('incomplete prior capture exists; retain it and use a new manual run directory')
            record = q.collect(Path('/'), receipt_path, image, boot_image, journal, config.get('duration_s', 120), 1)
            after = cpu()
            total = sum(b - a for a, b in zip(before, after))
            idle = (after[3] - before[3]) + (after[4] - before[4])
            diagnostics = {'before': state_before, 'after': inventory(), 'cpu_total_ticks': total,
                           'cpu_busy_fraction': (total - idle) / total if total > 0 else None}
            q.write_new(output / 'inventory.json', diagnostics)
            subprocess.run([sys.executable, str(HERE.parents[1] / 'hardware/kernel-smoke.py'),
                            '--receipt', str(receipt_path), '--work', str(output), '--output', str(output / 'smoke.json'),
                            '--kernel-image', str(image), '--boot-image', str(boot_image)], check=True, timeout=90)
            status.update(status='complete-scoped', completed_at=datetime.now(timezone.utc).isoformat(),
                          power=record['power']['summary'], controls_unchanged=record['controls_unchanged'],
                          source_config_sha256=q.digest(config_path), runner_sha256=q.digest(__file__),
                          full_hardware_qualification=False, power_improvement_claim=False)
            q.write_new(output / 'complete.json', status)
            save_status()
            power = status['power']
            summary = f"# {profile['role']} kernel observation\n\nKernel: `{release}`. Boot: `{boot_id}`.\n\n"
            summary += 'Boot/PMP/idle-accounting receipts, read-only device/temperature inventory, GPU shader/readback and 1 MiB fsync smoke results are retained beside this report.\n\n'
            if power:
                summary += f"Observed SMC power: median {power['median_w']:.2f} W; p10 {power['p10_w']:.2f} W; p90 {power['p90_w']:.2f} W; n={power['n']}.\n\n"
            summary += f"Controls unchanged: {status['controls_unchanged']}. CPU busy fraction: {diagnostics['cpu_busy_fraction']}.\n\n"
            summary += 'Normal owner desktop, uncontrolled workloads. This is not an idle baseline, paired A/B result, battery-life improvement, suspend/recovery test or stable qualification.\n'
            (output / 'SUMMARY.md').write_text(summary)
            print(summary)
        except Exception as error:
            status.update(status='failed-scoped-capture', error=str(error), full_hardware_qualification=False)
            save_status()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('/etc/mseries-kernel-trial.json'))
    capture(parser.parse_args().config)
