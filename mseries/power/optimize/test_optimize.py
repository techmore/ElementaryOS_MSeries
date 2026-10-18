#!/usr/bin/python3
"""mseries-power-tune applies and reverts exactly; power_ab.py only claims an effect under matched, repeatable conditions."""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TUNE = HERE / 'mseries-power-tune'

FAKE_SYSTEMCTL = r'''#!/bin/bash
# Fake systemctl: unit state lives in $FAKE_UNITS/<unit> as "enabled active"; every call is logged.
echo "$*" >> "$FAKE_UNITS/.log"
cmd=$1; shift
now=0
[[ ${1:-} == --now ]] && { now=1; shift; }
for u in "$@"; do
  f=$FAKE_UNITS/$u; [[ -f $f ]] || echo "disabled inactive" > "$f"
  read -r en ac < "$f"
  case $cmd in
    is-enabled) echo "$en"; [[ $en == enabled ]]; exit;;
    is-active) echo "$ac"; [[ $ac == active ]]; exit;;
    enable) en=enabled; (( now )) && ac=active;;
    disable) en=disabled; (( now )) && ac=inactive;;
    start) ac=active;;
    stop) ac=inactive;;
  esac
  echo "$en $ac" > "$f"
done
'''


class Tune(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.units = root / 'units'
        self.units.mkdir()
        for u, st in {'cups.service': 'enabled active', 'cups.socket': 'enabled active',
                      'cups-browsed.service': 'enabled active', 'rpcbind.service': 'enabled active',
                      'rpcbind.socket': 'enabled active', 'smartmontools.service': 'enabled active'}.items():
            (self.units / u).write_text(st + '\n')
        bindir = root / 'bin'
        bindir.mkdir()
        (bindir / 'systemctl').write_text(FAKE_SYSTEMCTL)
        (bindir / 'systemctl').chmod(0o755)
        self.sys = root / 'sys'
        lan = self.sys / 'bus/usb/devices/2-1.4.4'
        (lan / 'power').mkdir(parents=True)
        (lan / 'power/wakeup').write_text('enabled\n')
        (lan / '2-1.4.4:1.0/net/enx0').mkdir(parents=True)
        hub = self.sys / 'bus/usb/devices/2-1'
        (hub / 'power').mkdir(parents=True)
        (hub / 'power/wakeup').write_text('enabled\n')
        self.proc = root / 'proc'
        self.proc.mkdir()
        (self.proc / 'mounts').write_text('/dev/nvme0n1p5 / ext4 rw 0 0\n')
        self.state = root / 'state'
        self.env = {**os.environ, 'MSERIES_SYSTEMCTL': str(bindir / 'systemctl'), 'FAKE_UNITS': str(self.units),
                    'MSERIES_SYS': str(self.sys), 'MSERIES_PROC': str(self.proc), 'MSERIES_TUNE_STATE': str(self.state),
                    'MSERIES_TUNE_ALLOW_NONROOT': '1'}

    def tearDown(self):
        self.tmp.cleanup()

    def tune(self, *args, ok=True, env=None):
        r = subprocess.run(['bash', str(TUNE), *args], env=env or self.env, capture_output=True, text=True)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        else:
            self.assertNotEqual(r.returncode, 0, r.stdout)
        return r

    def unit(self, u):
        return (self.units / u).read_text().split()

    def test_apply_and_revert_restore_prior_state(self):
        self.tune('apply', 'cups-browsed', 'rpcbind')
        self.assertEqual(self.unit('cups.service'), ['enabled', 'active'])
        self.assertEqual(self.unit('cups-browsed.service'), ['disabled', 'inactive'])
        self.assertEqual(self.unit('rpcbind.socket'), ['disabled', 'inactive'])
        self.assertIn('applied', self.tune('list').stdout)
        self.tune('revert-all')
        for u in ('cups-browsed.service', 'rpcbind.service', 'rpcbind.socket'):
            self.assertEqual(self.unit(u), ['enabled', 'active'], u)
        self.assertEqual(list(self.state.glob('*.prev')), [])

    def test_revert_keeps_a_previously_disabled_unit_disabled(self):
        (self.units / 'cups-browsed.service').write_text('disabled active\n')
        self.tune('apply', 'cups-browsed')
        self.tune('revert', 'cups-browsed')
        self.assertEqual(self.unit('cups-browsed.service'), ['disabled', 'active'])

    def test_reapply_keeps_first_prior_state_and_unapplied_revert_is_refused(self):
        self.tune('apply', 'cups-browsed')
        self.assertIn('already applied', self.tune('apply', 'cups-browsed').stdout)
        self.tune('revert', 'cups-browsed')
        self.assertEqual(self.unit('cups-browsed.service'), ['enabled', 'active'])
        self.tune('revert', 'rpcbind', ok=False)
        self.tune('apply', 'nonsense', ok=False)

    def test_dry_run_changes_nothing(self):
        out = self.tune('--dry-run', 'apply', 'cups-browsed', 'dock-lan-wake').stdout
        self.assertIn('would run', out)
        self.assertEqual(self.unit('cups-browsed.service'), ['enabled', 'active'])
        self.assertFalse(self.state.exists())
        self.assertEqual((self.sys / 'bus/usb/devices/2-1.4.4/power/wakeup').read_text().strip(), 'enabled')

    def test_rpcbind_refused_with_nfs_mount(self):
        (self.proc / 'mounts').write_text('srv:/x /mnt nfs4 rw 0 0\n')
        self.tune('apply', 'rpcbind', ok=False)
        self.assertEqual(self.unit('rpcbind.service'), ['enabled', 'active'])

    def test_dock_lan_wake_touches_only_ethernet_and_reverts(self):
        wake = self.sys / 'bus/usb/devices/2-1.4.4/power/wakeup'
        hub = self.sys / 'bus/usb/devices/2-1/power/wakeup'
        self.tune('apply', 'dock-lan-wake')
        self.assertEqual(wake.read_text().strip(), 'disabled')
        self.assertEqual(hub.read_text().strip(), 'enabled')
        self.tune('revert', 'dock-lan-wake')
        self.assertEqual(wake.read_text().strip(), 'enabled')

    def test_tampered_state_cannot_reach_audio_or_display_units(self):
        self.state.mkdir()
        (self.state / 'cups-browsed.prev').write_text('unit wireplumber.service enabled active\n')
        r = self.tune('revert', 'cups-browsed', ok=False)
        self.assertIn('out of scope', r.stderr)
        self.assertNotIn('wireplumber', (self.units / '.log').read_text() if (self.units / '.log').exists() else '')

    def test_needs_root_without_dry_run(self):
        env = {**self.env, 'MSERIES_TUNE_ALLOW_NONROOT': '0'}
        if os.geteuid() != 0:
            self.tune('apply', 'cups-browsed', ok=False, env=env)


def load_ab(sys_root, proc_root):
    os.environ['MSERIES_SYS'] = str(sys_root)
    os.environ['MSERIES_PROC'] = str(proc_root)
    spec = importlib.util.spec_from_file_location('power_ab', HERE / 'power_ab.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cond(ac='0', drm=('card2-eDP-1',), bl='307'):
    return {'ac_online': ac, 'battery_status': 'Discharging', 'battery_capacity': '70', 'battery_energy_now': '1',
            'drm_connected': list(drm), 'backlight': {'apple-panel-bl': bl}, 'loadavg': ['0.1', '0.1', '0.1']}


def arm(name, median, busy=5.0, **c):
    return {'arm': name, 'median': median, 'p10': median - 0.5, 'p90': median + 0.5, 'n': 60, 'cpu_busy': busy,
            'started': cond(**c), 'ended': cond(**c)}


def result(pairs):
    return {'label': 't', 'pairs': [{'order': 'AB' if i % 2 == 0 else 'BA', 'A': arm('A', a), 'B': arm('B', b)}
                                     for i, (a, b) in enumerate(pairs)]}


class Verdict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        hw = root / 'sys/class/hwmon/hwmon2'
        hw.mkdir(parents=True)
        (hw / 'name').write_text('macsmc_hwmon\n')
        (hw / 'power1_label').write_text('Total System Power\n')
        (hw / 'power1_input').write_text('12500000\n')
        (root / 'proc').mkdir()
        (root / 'proc/stat').write_text('cpu  100 0 100 800 0 0 0 0 0 0\n')
        (root / 'proc/loadavg').write_text('0.10 0.20 0.30 1/100 1\n')
        cls.ab = load_ab(root / 'sys', root / 'proc')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_consistent_saving_above_noise_is_reported(self):
        v, reasons, stats = self.ab.verdict(result([(10.0, 9.0), (10.1, 9.1), (10.05, 9.0)]))
        self.assertEqual(v, 'saving measured', reasons)
        self.assertAlmostEqual(stats['median_delta'], -1.0, places=2)

    def test_small_or_mixed_effects_are_inconclusive(self):
        v, reasons, _ = self.ab.verdict(result([(10.0, 9.9), (10.1, 10.0), (10.0, 9.9)]))
        self.assertEqual(v, 'inconclusive')
        self.assertTrue(any('noise floor' in r for r in reasons))
        v, reasons, _ = self.ab.verdict(result([(10.0, 9.0), (10.0, 11.0), (10.0, 9.0)]))
        self.assertTrue(any('sign' in r for r in reasons))

    def test_baseline_drift_raises_the_noise_floor(self):
        v, reasons, stats = self.ab.verdict(result([(10.0, 9.4), (12.0, 11.4), (11.0, 10.4)]))
        self.assertEqual(v, 'inconclusive')
        self.assertEqual(stats['noise_floor_w'], 2.0)

    def test_too_few_pairs_ac_and_display_changes_block_claims(self):
        v, reasons, _ = self.ab.verdict(result([(10.0, 9.0), (10.0, 9.0)]))
        self.assertTrue(any('pair' in r for r in reasons))
        r = result([(10.0, 9.0)] * 3)
        for p in r['pairs']:
            p['A']['started']['ac_online'] = p['B']['started']['ac_online'] = '1'
            p['A']['ended']['ac_online'] = p['B']['ended']['ac_online'] = '1'
        v, reasons, _ = self.ab.verdict(r)
        self.assertTrue(any('AC' in x for x in reasons))
        v, _, _ = self.ab.verdict(r, allow_ac=True)
        self.assertEqual(v, 'saving measured (on AC, system rail only)')
        r = result([(10.0, 9.0)] * 3)
        r['pairs'][1]['B']['ended']['backlight'] = {'apple-panel-bl': '200'}
        v, reasons, _ = self.ab.verdict(r)
        self.assertTrue(any('display' in x for x in reasons))

    def test_workload_mismatch_blocks_claims(self):
        r = result([(10.0, 9.0)] * 3)
        r['pairs'][0]['B']['cpu_busy'] = 30.0
        _, reasons, _ = self.ab.verdict(r)
        self.assertTrue(any('CPU busy' in x for x in reasons))

    def test_sampling_reads_the_smc_rail(self):
        watts, busy = self.ab.sample(0.03, interval=0.01)
        self.assertEqual(watts, [12.5, 12.5, 12.5])
        self.assertEqual(self.ab.quantile([1, 2, 3, 4], 0.5), 2.5)
        c = self.ab.conditions()
        self.assertEqual(c['loadavg'], ['0.10', '0.20', '0.30'])

    def test_summarize_round_trip(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(result([(10.0, 9.0)] * 3), f)
        try:
            self.assertEqual(self.ab.main(['summarize', f.name]), 0)
        finally:
            os.unlink(f.name)


class Hygiene(unittest.TestCase):
    def test_chromium_processes_are_grouped_by_app_profile_and_type(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / '4242'
            p.mkdir()
            (p / 'cmdline').write_bytes(b'/opt/brave.com/brave/brave\0--type=renderer\0'
                                        b'--user-data-dir=' + os.path.expanduser('~').encode() + b'/.config/brave-youtube\0')
            os.environ['MSERIES_PROC'] = d
            spec = importlib.util.spec_from_file_location('app_hygiene', HERE / 'app_hygiene.py')
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.assertEqual(mod.describe('4242', 'brave'), ('brave', 'renderer', '~/.config/brave-youtube'))
            self.assertEqual(mod.describe('9999', 'gala'), ('gala', 'main', None))


if __name__ == '__main__':
    unittest.main()
