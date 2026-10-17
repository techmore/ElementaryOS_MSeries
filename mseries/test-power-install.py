#!/usr/bin/env python3
"""Stage the real enhancement installer into a temp root; never touch the host OS."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class PowerInstall(unittest.TestCase):
    def test_factory_and_live_installer_ship_the_same_policy_units(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindir = root/'bin'
            bindir.mkdir()
            # enable() calls systemctl --root; emulate only that offline operation on macOS too.
            tool = bindir/'systemctl'
            tool.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
root = Path(next(a.split('=', 1)[1] for a in sys.argv if a.startswith('--root=')))
unit = sys.argv[-1]
p = root/'etc/systemd/system/graphical.target.wants'/unit
p.parent.mkdir(parents=True, exist_ok=True)
if not p.is_symlink():
    p.symlink_to('../' + unit)
''')
            tool.chmod(0o755)
            # macOS install lacks GNU install's -D option, used by the Linux installer.
            tool = bindir/'install'
            tool.write_text('''#!/usr/bin/env python3
import os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
mode = int(args[args.index('-m') + 1], 8)
src, dst = args[-2:]
Path(dst).parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(src, dst)
os.chmod(dst, mode)
''')
            tool.chmod(0o755)
            staged = root/'staged'
            staged.mkdir()
            env = {**os.environ, 'PATH': str(bindir) + os.pathsep + os.environ['PATH']}
            for _ in range(2):
                result = subprocess.run(['bash', str(HERE/'enhance.sh'), '--root', str(staged), '--only', 'power'],
                                        env=env, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode() + result.stdout.decode())
            live = (HERE/'install-power.sh').read_text()
            for name in ('mseries-power.service', 'mseries-power-follow.service'):
                content = (staged/'etc/systemd/system'/name).read_text()
                self.assertIn(content, live)
                self.assertTrue((staged/'etc/systemd/system/graphical.target.wants'/name).is_symlink())
            rule = (staged/'etc/udev/rules.d/80-mseries-power.rules').read_text()
            self.assertIn(rule, live)
            self.assertIn('--no-block restart mseries-power.service', rule)
            self.assertNotIn('SYSTEMD_WANTS', rule)
            helper = staged/'usr/local/sbin/mseries-power'
            self.assertEqual(helper.read_bytes(), (HERE/'power/mseries-power').read_bytes())
            self.assertTrue(os.access(helper, os.X_OK))


if __name__ == '__main__':
    unittest.main()
