import gzip
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('diagnostics', Path(__file__).with_name('prepare-boot-diagnostics.py'))
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)
audit_spec = importlib.util.spec_from_file_location('audit', Path(__file__).with_name('audit-trial-initrd.py'))
audit_module = importlib.util.module_from_spec(audit_spec)
audit_spec.loader.exec_module(audit_module)

INIT = '''#!/bin/ash
mount_setup
    modprobe -qab ${earlymodules//,/ } $MODULES
if rootdev="$(resolve_device "$root")"; then
    :
fi
"$mount_handler" /sysroot
rdlogger_stop
'''
FUNCTIONS = '''run_hookfunctions() {
    for hook in "$@"; do
        "$fn"
    done
}
'''


class BootDiagnosticsTests(unittest.TestCase):
    def image(self):
        rows = []
        for ino, (name, data) in enumerate((('init', INIT.encode()), ('init_functions', FUNCTIONS.encode()),
                                           ('config', b'HOOKS="encrypt"'), ('usr/bin/cryptsetup', b'cryptsetup'),
                                           ('hooks/encrypt', b'unchanged unlock hook'),
                                           ('usr/lib/modules/candidate/modules.dep', b'kernel/driver.ko:\n'),
                                           ('usr/lib/modules/candidate/kernel/driver.ko', b'unchanged module')), 1):
            rows.append((name, [ino, stat.S_IFREG | 0o755, 0, 0, 1, 0, len(data), 0, 0, 0, 0, 0, 0], data))
        trailer = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        return gzip.compress(diagnostics.trial.newc.encode(rows, trailer))

    def test_archive_preserves_unlock_modules_metadata_and_executable_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output, report = (root / n for n in ('source', 'diagnostic', 'receipt'))
            source.write_bytes(self.image())
            receipt = diagnostics.prepare(source, output, report)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertTrue(receipt['all_other_entries_unchanged'])
            rows = diagnostics.trial.newc.parse(gzip.decompress(output.read_bytes()))[0]
            entries = {n: (v, d) for n, v, d in rows}
            self.assertEqual(entries['hooks/encrypt'][1], b'unchanged unlock hook')
            self.assertEqual(entries['init'][0][1], stat.S_IFREG | 0o755)
            self.assertIn(b'before switch_root', entries['init'][1])
            self.assertEqual(json.loads(report.read_text()), receipt)
            with self.assertRaises(ValueError):
                diagnostics.prepare(source, output, report)

    def test_unknown_and_repeated_instrumentation_refused(self):
        with self.assertRaises(ValueError):
            diagnostics.instrument(INIT.replace('mount_setup', 'different_setup'), FUNCTIONS)
        init, functions = diagnostics.instrument(INIT, FUNCTIONS)
        with self.assertRaises(ValueError):
            diagnostics.instrument(init, functions)

    def test_refuses_live_destination_and_same_output_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                diagnostics.prepare(root / 'input', Path('/boot/never-write-diagnostic-fixture'), root / 'report')
            with self.assertRaises(ValueError):
                diagnostics.prepare(root / 'input', root / 'same', root / 'same')

    def test_trace_preserves_failure_status_without_shell_tracing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Redirect only the test helper to ordinary private files.
            helper = diagnostics.TRACE.replace('/dev/kmsg', str(root / 'kernel')).replace('/dev/console', str(root / 'console'))
            result = subprocess.run(['bash', '-c', helper + '\nmseries_boot_trace "end test status=7" 7\n'], capture_output=True)
            self.assertEqual(result.returncode, 7)
            self.assertIn('end test status=7', (root / 'kernel').read_text())
            self.assertNotIn('set -x', helper)

    def test_archive_audit_rejects_changed_module_and_missing_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp) / 'candidate'
            (tree / 'kernel').mkdir(parents=True)
            module = tree / 'kernel/driver.ko'
            module.write_bytes(b'unchanged module')
            image = self.image()
            self.assertEqual(audit_module.audit(image, image, tree)['verified_module_count'], 1)
            module.write_bytes(b'wrong build')
            with self.assertRaisesRegex(ValueError, 'module bytes differ'):
                audit_module.audit(image, image, tree)
            module.write_bytes(b'unchanged module')
            rows, trailer = diagnostics.trial.newc.parse(gzip.decompress(image))
            updated = []
            for name, values, data in rows:
                if name.endswith('modules.dep'):
                    data = b'kernel/driver.ko: kernel/missing.ko\n'
                    values = values.copy()
                    values[6] = len(data)
                updated.append((name, values, data))
            broken = gzip.compress(diagnostics.trial.newc.encode(updated, trailer))
            with self.assertRaisesRegex(ValueError, 'dependency missing'):
                audit_module.audit(image, broken, tree)
