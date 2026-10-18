import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import touchid_core as core


class TestMessages(unittest.TestCase):
    def test_finger_label(self):
        self.assertEqual(core.finger_label("right-index-finger"), "Right index finger")
        self.assertEqual(core.finger_label("left-thumb"), "Left thumb")

    def test_enroll_known_statuses(self):
        text, finished = core.enroll_message("enroll-stage-passed", False)
        self.assertFalse(finished)
        self.assertIn("again", text)

        text, finished = core.enroll_message("enroll-completed", True)
        self.assertTrue(finished)
        self.assertIn("Enrolled", text)

        for status in ("enroll-failed", "enroll-data-full", "enroll-disconnected"):
            text, finished = core.enroll_message(status, True)
            self.assertTrue(finished, status)

        # done wins even for a status we do not know
        text, finished = core.enroll_message("enroll-something-new", True)
        self.assertTrue(finished)

        # not-done unknown status must not look finished
        text, finished = core.enroll_message("enroll-something-new", False)
        self.assertFalse(finished)

    def test_verify_known_statuses(self):
        text, finished = core.verify_message("verify-no-match", True)
        self.assertTrue(finished)
        self.assertIn("No match", text)

        text, finished = core.verify_message("verify-retry-scan", False)
        self.assertFalse(finished)

        text, finished = core.verify_message("verify-match", True)
        self.assertTrue(finished)


class TestPamState(unittest.TestCase):
    def _write(self, name, content):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_states(self):
        paths = {
            "sudo": self._write("sudo", "session    required   pam_limits.so\n"),
            "polkit": self._write("polkit-1",
                                  "auth      sufficient pam_fprintd.so\nauth      required pam_unix.so\n"),
            "missing": os.path.join(self.tmp, "nope"),
        }
        state = core.pam_state(paths)
        by_name = {p["name"]: p["state"] for p in state}
        self.assertEqual(by_name["sudo"], "password-only")
        self.assertEqual(by_name["polkit"], "fingerprint")
        self.assertEqual(by_name["missing"], "missing")

    def test_indented_comment_line_is_not_a_match(self):
        paths = {"sudo": self._write("sudo", "# auth sufficient pam_fprintd.so\n")}
        state = core.pam_state(paths)
        self.assertEqual(state[0]["state"], "password-only")

    def test_pam_plan(self):
        paths = {
            "sudo": self._write("sudo2", "auth      sufficient pam_fprintd.so\n"),
            "polkit": self._write("polkit2", "auth      required pam_unix.so\n"),
        }
        self.assertIn("polkit", core.pam_plan(core.pam_state(paths)))


class TestFindings(unittest.TestCase):
    def test_wrong_kernel_short_circuits(self):
        findings = core.sep_findings({"kernel": "7.1.13-elementary-fairydust-usb4-dptunnel"})
        self.assertEqual(len(findings), 1)
        severity, title, detail, fix = findings[0]
        self.assertEqual(severity, core.BAD)
        self.assertEqual(title, "Wrong kernel")
        self.assertIn("REBOOT-QUEUE", fix)

    def test_aurora_kernel_without_device(self):
        facts = {"kernel": "7.1.12-2-20261015.19-sep-ARCH", "sep_bio": False,
                 "apple_sep": "active", "fprintd": "active", "device": False}
        findings = core.sep_findings(facts)
        self.assertEqual(findings[0][0], core.BAD)
        self.assertEqual(findings[0][1], "No /dev/sep-bio")

    def test_ready(self):
        facts = {"kernel": "7.1.12-2-20261015.19-sep-ARCH", "sep_bio": True,
                 "apple_sep": "active", "fprintd": "active", "device": True}
        findings = core.sep_findings(facts)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0][0], core.OK)

    def test_node_without_sensor_readiness_is_not_ready(self):
        for state in ('inactive', 'busy', 'failed'):
            with self.subTest(state=state):
                f = core.sep_findings({'sep_bio': True, 'device': True, 'readiness': state})
                self.assertEqual(f[0][0], core.WARN)
                self.assertNotIn('restart fprintd', f[0][3])

    def test_ready_sensor_still_requires_fprintd_device(self):
        f = core.sep_findings({'sep_bio': True, 'readiness': 'ready', 'device': False,
                               'device_error': 'service not available'})
        self.assertEqual(f[0][0], core.WARN)
        self.assertIn('service not available', f[0][2])

    def test_older_kernel_without_diagnostics_can_use_fprintd(self):
        self.assertEqual(core.sep_findings({'sep_bio': True, 'device': True})[0][0], core.OK)

    def test_current_kernel_identity_is_case_insensitive(self):
        self.assertTrue(core.on_aurora_kernel('7.1.12-elementary-aurora20'))
        self.assertTrue(core.on_aurora_kernel('7.1.12-2-20261015.19-sep-ARCH'))


if __name__ == "__main__":
    unittest.main()
