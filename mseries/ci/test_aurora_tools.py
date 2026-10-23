from pathlib import Path
import tempfile
import unittest
from unittest import mock

import install_aurora_tools as tools
import workflow_policy


class AuroraDownloadsTest(unittest.TestCase):
    def execute(self, codes):
        calls = []
        mirrors = []
        with tempfile.TemporaryDirectory() as root:
            def run(command):
                calls.append(command)
                mirrors.append((Path(root) / 'sources/ubuntu.sources').read_text())
                return codes.pop(0)
            tools.install('resolute', 'arm64', root, run)
        return calls, mirrors

    def test_primary_success_downloads_before_install_and_never_uses_network_for_install(self):
        calls, mirrors = self.execute([0, 0, 0])
        self.assertEqual(3, len(calls))
        self.assertIn('https://ports.ubuntu.com/ubuntu-ports', mirrors[0])
        self.assertIn('--download-only', calls[1])
        self.assertIn('--no-download', calls[2])
        self.assertEqual('apt-get', calls[2][0])  # dpkg is not killed by a download timeout.
        self.assertNotIn('timeout', calls[2])
        self.assertTrue(all('--allow-unauthenticated' not in call for call in calls))

    def test_slow_download_times_out_then_uses_fallback(self):
        calls, mirrors = self.execute([0, 124, 0, 0, 0])
        self.assertEqual(['timeout', '--kill-after=15s', '60'], calls[0][:3])
        self.assertEqual(['timeout', '--kill-after=15s', '240'], calls[1][:3])
        self.assertIn('https://azure.archive.ubuntu.com/ubuntu', mirrors[2])
        self.assertIn('--no-download', calls[-1])
        self.assertIn('Acquire::https::Timeout=30', calls[0])

    def test_failed_metadata_uses_fallback_and_both_failures_prevent_install(self):
        calls, mirrors = self.execute([100, 0, 0, 0])
        self.assertIn('https://azure.archive.ubuntu.com/ubuntu', mirrors[1])
        with self.assertRaisesRegex(RuntimeError, 'Both Ubuntu mirrors'):
            self.execute([124, 124])

    def test_both_download_timeouts_never_start_dpkg(self):
        run = mock.Mock(side_effect=[0, 124, 0, 124])
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(RuntimeError, 'Both Ubuntu mirrors'):
            tools.install('resolute', 'arm64', folder, run)
        self.assertEqual(4, run.call_count)
        self.assertTrue(all('--no-download' not in call.args[0] for call in run.call_args_list))

    def test_main_refuses_to_install_on_developer_host(self):
        with mock.patch.dict(tools.os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, 'ephemeral GitHub'):
            tools.main()

    def test_install_failure_is_not_retried_as_a_mirror_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'Package installation failed'):
            self.execute([0, 0, 100])

    def test_signed_sources_preserve_release_and_reject_unexpected_architecture_or_mirror(self):
        source = tools.sources('resolute', tools.MIRRORS[0])
        self.assertIn('resolute resolute-updates resolute-backports resolute-security', source)
        self.assertIn('Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg', source)
        self.assertNotIn('Trusted:', source)
        for codename, mirror in [('resolute\nTrusted: yes', tools.MIRRORS[0]), ('resolute', 'https://untrusted.invalid')]:
            with self.assertRaises(ValueError):
                tools.sources(codename, mirror)
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            tools.install('resolute', 'amd64', folder, mock.Mock())

    def test_workflow_uses_installer_and_bounds_rustup(self):
        workflow = workflow_policy.load(workflow_policy.ROOT / '.github/workflows/aurora-enhancements.yml')
        step = next(s for s in workflow['jobs']['build']['steps'] if s.get('name') == 'Install native build tools')
        self.assertIn('install_aurora_tools.py', step['run'])
        self.assertIn('timeout --kill-after=15s 300 rustup', step['run'])
        self.assertEqual('20', step['timeout-minutes'])
        self.assertIn('mseries/ci/**', workflow['on']['pull_request']['paths'])


if __name__ == '__main__':
    unittest.main()
