#!/usr/bin/python3 -I
"""Offline tests for peripherals.py: battery choice, cable matching, plug-in and pairing plans."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import peripherals as p  # noqa: E402


def bluez(address, name, icon, paired=True, trusted=True, connected=True, percent=None, rssi=None,
          modalias=''):
    return dict(address=address, name=name, icon=icon, modalias=modalias, paired=paired,
                trusted=trusted, connected=connected, rssi=rssi, percent=percent, path='/x')


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class Sysfs:
    """A tiny /sys with one plugged-in Magic Keyboard and its HID battery."""

    def __init__(self, root, percent='43', status='Charging'):
        usb = root / 'devices/usb1/1-1'
        write(usb / 'idVendor', '05ac\n')
        write(usb / 'idProduct', '0267\n')
        write(usb / 'product', 'Magic Keyboard\n')
        supply = usb / '1-1:1.0/0003:05AC:0267.0001/power_supply/hid-F0T123-battery'
        write(supply / 'scope', 'Device\n')
        write(supply / 'capacity', percent + '\n')
        write(supply / 'status', status + '\n')
        write(supply / 'model_name', 'Magic Keyboard\n')
        (root / 'bus/usb/devices').mkdir(parents=True)
        (root / 'bus/usb/devices/1-1').symlink_to(usb)
        (root / 'class/power_supply').mkdir(parents=True)
        (root / 'class/power_supply/hid-F0T123-battery').symlink_to(supply)
        self.power, self.usb = root / 'class/power_supply', root / 'bus/usb/devices'


class ClassifyTests(unittest.TestCase):
    def test_kind_from_name_then_icon(self):
        self.assertEqual(p.kind_of('Magic Trackpad 2'), 'trackpad')
        self.assertEqual(p.kind_of("Sam's Magic Keyboard"), 'keyboard')
        self.assertEqual(p.kind_of('Magic Mouse'), 'mouse')
        self.assertEqual(p.kind_of('MX Vertical', 'input-mouse'), 'mouse')
        self.assertEqual(p.kind_of('Headset', 'audio-headset'), 'other')

    def test_vendor(self):
        self.assertEqual(p.vendor_of('Magic Keyboard'), 'apple')
        self.assertEqual(p.vendor_of('Keys', 'bluetooth:v004Cp0267d0001'), 'apple')
        self.assertEqual(p.vendor_of('MX Vertical', 'usb:v046DpB020d0009'), 'logitech')
        self.assertEqual(p.vendor_of('Some Pad'), 'other')


class BatteryTests(unittest.TestCase):
    def test_bluez_percent_beats_a_kernel_level_without_a_number(self):
        # The MX Vertical's HID++ driver reports only "Normal"; UPower turns that into 55%.
        supply = dict(name='hidpp_battery_1', real='/sys/devices/virtual/misc/uhid/0005:046D:B020.0005/x',
                      address='E7:8F:29:0E:E9:0A', transport='bluetooth', model='', status='Discharging',
                      percent=None, level='normal')
        devices = p.merge([bluez('E7:8F:29:0E:E9:0A', 'MX Vertical', 'input-mouse', percent=100)],
                          [supply], [])
        self.assertEqual(devices[0]['battery'],
                         dict(percent=100, level='normal', charging=False, source='bluetooth'))

    def test_kernel_number_wins_and_charging_comes_from_the_kernel(self):
        supply = dict(name='n', real='/x', address='AA:BB:CC:DD:EE:FF', transport='bluetooth',
                      model='', status='Charging', percent=62, level=None)
        devices = p.merge([bluez('AA:BB:CC:DD:EE:FF', 'Magic Trackpad', 'input-mouse', percent=60)],
                          [supply], [])
        self.assertEqual((devices[0]['battery']['percent'], devices[0]['battery']['charging']),
                         (62, True))

    def test_no_reading_is_unknown_not_zero(self):
        devices = p.merge([bluez('AA:BB:CC:DD:EE:FF', 'Magic Mouse', 'input-mouse')], [], [])
        self.assertEqual(devices[0]['battery']['percent'], None)
        self.assertEqual(p.describe(devices[0])[2], 'unknown')


class CableTests(unittest.TestCase):
    def collect(self, root, paired):
        sysfs = Sysfs(root)
        with mock.patch.object(p, 'SYS_POWER', sysfs.power), mock.patch.object(p, 'SYS_USB', sysfs.usb), \
                mock.patch.object(p, 'bluez_devices', return_value=paired):
            return p.collect()

    def test_cable_merges_into_the_one_paired_device_of_its_kind(self):
        with tempfile.TemporaryDirectory() as t:
            paired = [bluez('AA:BB:CC:DD:EE:FF', 'Magic Keyboard', 'input-keyboard', connected=False)]
            devices = self.collect(Path(t), paired)
        self.assertEqual(len(devices), 1)
        keyboard = devices[0]
        self.assertTrue(keyboard['wired'])
        self.assertEqual(keyboard['address'], 'AA:BB:CC:DD:EE:FF')
        self.assertEqual((keyboard['battery']['percent'], keyboard['battery']['charging']), (43, True))
        self.assertEqual(p.describe(keyboard), ('USB + Bluetooth', 'plugged in', '43% charging'))

    def test_unpaired_cable_is_its_own_entry(self):
        with tempfile.TemporaryDirectory() as t:
            devices = self.collect(Path(t), [])
        self.assertEqual(len(devices), 1)
        self.assertIsNone(devices[0]['address'])
        self.assertFalse(devices[0]['ambiguous'])
        self.assertEqual(devices[0]['battery']['percent'], 43)

    def test_two_paired_keyboards_make_the_cable_ambiguous(self):
        with tempfile.TemporaryDirectory() as t:
            paired = [bluez('AA:BB:CC:DD:EE:01', 'Magic Keyboard', 'input-keyboard'),
                      bluez('AA:BB:CC:DD:EE:02', 'Magic Keyboard', 'input-keyboard')]
            devices = self.collect(Path(t), paired)
        wired = [d for d in devices if d['wired']]
        self.assertEqual(len(wired), 1)
        self.assertTrue(wired[0]['ambiguous'])
        self.assertIsNone(wired[0]['address'])

    def test_internal_and_non_input_usb_devices_are_skipped(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            write(root / 'devices/a/idVendor', '05ac')
            write(root / 'devices/a/product', 'Apple Internal Keyboard / Trackpad')
            write(root / 'devices/b/idVendor', '046d')
            write(root / 'devices/b/product', 'USB Receiver')
            (root / 'usb').mkdir()
            (root / 'usb/a').symlink_to(root / 'devices/a')
            (root / 'usb/b').symlink_to(root / 'devices/b')
            with mock.patch.object(p, 'SYS_USB', root / 'usb'):
                self.assertEqual(p.usb_accessories(), [])


def entry(**over):
    base = dict(key='AA:BB:CC:DD:EE:FF', name='Magic Keyboard', address='AA:BB:CC:DD:EE:FF',
                kind='keyboard', vendor='apple', paired=True, trusted=True, connected=True,
                wired=False, ambiguous=False,
                battery=dict(percent=80, level=None, charging=False, source='kernel'))
    base.update(over)
    return base


class PlanTests(unittest.TestCase):
    def test_steady_state_does_nothing(self):
        state, actions = p.plan({}, [entry()])
        self.assertEqual(actions, [])
        self.assertEqual(p.plan(state, [entry()])[1], [])

    def test_unpaired_cable_offers_pairing_once(self):
        cable = entry(key='usb:05ac:0267:1-1', address=None, paired=False, trusted=False,
                      connected=False, wired=True)
        state, actions = p.plan({}, [cable])
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0][0], 'notify')
        self.assertEqual(actions[0][4], ('keyboard', 'apple'))
        self.assertEqual(p.plan(state, [cable])[1], [])

    def test_ambiguous_cable_never_offers_pairing(self):
        cable = entry(key='usb:x', address=None, paired=False, trusted=False, connected=False,
                      wired=True, ambiguous=True)
        self.assertEqual([a[4] for a in p.plan({}, [cable])[1]], [None])

    def test_paired_untrusted_cable_gets_trusted_and_reports_charge(self):
        cable = entry(trusted=False, connected=False, wired=True,
                      battery=dict(percent=43, level=None, charging=True, source='kernel'))
        actions = p.plan({}, [cable])[1]
        self.assertEqual(actions[0], ('trust', 'AA:BB:CC:DD:EE:FF'))
        self.assertEqual(actions[1][:3], ('notify', 'Magic Keyboard is plugged in', 'Charging.'))

    def test_unplugging_reconnects_a_paired_device_that_stayed_off(self):
        state = dict(wired=['AA:BB:CC:DD:EE:FF'])
        self.assertEqual(p.plan(state, [entry(connected=False)])[1],
                         [('connect', 'AA:BB:CC:DD:EE:FF')])
        self.assertEqual(p.plan(state, [entry(connected=True)])[1], [])

    def test_low_battery_notifies_once_and_rearms_after_charging(self):
        low = entry(battery=dict(percent=12, level=None, charging=False, source='kernel'))
        state, actions = p.plan({}, [low])
        self.assertEqual([a[1] for a in actions], ['Magic Keyboard battery is low'])
        state, actions = p.plan(state, [low])
        self.assertEqual(actions, [])
        charged = entry(battery=dict(percent=50, level=None, charging=True, source='kernel'))
        state, _ = p.plan(state, [charged])
        self.assertEqual(state['low'], [])
        self.assertEqual(len(p.plan(state, [low])[1]), 1)

    def test_low_battery_ignores_unknown_and_charging(self):
        unknown = entry(battery=dict(percent=None, level='low', charging=False, source='kernel'))
        charging = entry(battery=dict(percent=5, level=None, charging=True, source='kernel'))
        self.assertEqual(p.plan({}, [unknown, charging])[1], [])

    def test_a_disconnected_device_is_not_reported_low(self):
        away = entry(connected=False, battery=dict(percent=3, level=None, charging=False, source='bluetooth'))
        self.assertEqual(p.plan({}, [away])[1], [])


class PairTests(unittest.TestCase):
    def run_pair(self, arguments, found, outputs):
        calls = []

        def fake(command, timeout=20):
            calls.append(command[1:3])
            return subprocess.CompletedProcess(command, 0, outputs.get(command[1], ''), '')
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(p, 'run', fake), mock.patch.object(p, 'candidates', return_value=found), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = p.pair(arguments)
        return code, calls, out.getvalue(), err.getvalue()

    def test_explicit_address_pairs_trusts_and_connects(self):
        code, calls, out, _ = self.run_pair(['aa:bb:cc:dd:ee:ff'], [], {'pair': 'Pairing successful'})
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], ['pair', 'trust', 'connect'])
        self.assertIn('AA:BB:CC:DD:EE:FF', out)

    def test_failed_pairing_does_not_trust(self):
        code, calls, _, err = self.run_pair(['AA:BB:CC:DD:EE:FF'], [],
                                            {'pair': 'Failed to pair: org.bluez.Error.AuthenticationFailed'})
        self.assertEqual(code, 1)
        self.assertEqual([c[0] for c in calls], ['pair'])
        self.assertIn('AuthenticationFailed', err)

    def test_one_candidate_is_paired_without_an_address(self):
        found = [dict(address='11:22:33:44:55:66', name='Magic Trackpad', rssi=-50)]
        code, calls, _, _ = self.run_pair([], found, {'pair': 'Pairing successful'})
        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ['pair', '11:22:33:44:55:66'])

    def test_several_or_no_candidates_pair_nothing(self):
        two = [dict(address='11:22:33:44:55:66', name='A', rssi=-50),
               dict(address='11:22:33:44:55:67', name='B', rssi=-40)]
        for found in (two, []):
            code, calls, _, _ = self.run_pair([], found, {})
            self.assertEqual((code, calls), (1, []))

    def test_replace_removes_the_old_bond_first(self):
        _, calls, _, _ = self.run_pair(['AA:BB:CC:DD:EE:FF', '--replace'], [], {'pair': 'Pairing successful'})
        self.assertEqual(calls[0][0], 'remove')

    def test_candidates_need_a_live_signal_and_a_matching_kind(self):
        seen = [bluez('11:22:33:44:55:66', 'Magic Keyboard', 'input-keyboard', paired=False, rssi=-48),
                bluez('11:22:33:44:55:67', 'Magic Keyboard', 'input-keyboard', paired=False),
                bluez('11:22:33:44:55:68', 'Magic Mouse', 'input-mouse', paired=False, rssi=-40),
                bluez('11:22:33:44:55:69', 'Magic Keyboard', 'input-keyboard', paired=True, rssi=-40)]
        with mock.patch.object(p, 'run'), mock.patch.object(p, 'bluez_devices', return_value=seen):
            found = p.candidates('keyboard', 'apple')
        self.assertEqual([c['address'] for c in found], ['11:22:33:44:55:66'])


class StatusTests(unittest.TestCase):
    def test_status_lines_and_json(self):
        devices = p.merge([bluez('E7:8F:29:0E:E9:0A', 'MX Vertical', 'input-mouse', percent=100)], [], [])
        with mock.patch.object(p, 'collect', return_value=devices):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                p.status([])
            self.assertIn('MX Vertical', out.getvalue())
            self.assertIn('100%', out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                p.status(['--json'])
            self.assertEqual(json.loads(out.getvalue())[0]['battery']['percent'], 100)

    def test_unknown_command_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(p.main(['peripherals', 'frobnicate']), 2)


if __name__ == '__main__':
    unittest.main()
