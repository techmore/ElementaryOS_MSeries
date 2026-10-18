#!/usr/bin/env python3
"""Regression checks for evidence identity, immutable freezes and promotion gates."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import qualification as q
import candidate
from release import PINS


def receipt():
    identity = {"kernel_release": PINS["kernel_release"], "board": "apple,j314s", "soc": "apple,t6000",
                "runtime_parameters": {}, "feature_cmdline": [],
                "kernel_image_sha256": "a" * 64, "boot_payload_sha256": "b" * 64,
                "modules": {"kernel/drivers/gpu/drm/apple/appledrm.ko": "c" * 64, "dtbs/t6000-j314s.dtb": "d" * 64}}
    return {"schema": 1, "kind": "hardware-test", "identity": identity,
            "identity_sha256": hashlib.sha256(q.canonical(identity)).hexdigest(),
            "boot_id": "boot-a", "controls_unchanged": True,
            "context_before": {"parameters": {}},
            "checks": {"boot": {"result": "pass"}, "pmp_ready": {"result": "pass"}}}


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pins = self.root / "pins.json"
        self.pins.write_text(json.dumps(PINS))
        self.evidence = self.root / "test.json"
        self.save(receipt())
        self.output = self.root / "frozen.json"

    def tearDown(self):
        self.temp.cleanup()

    def save(self, data):
        self.evidence.write_text(json.dumps(data))

    def freeze(self, paths=None, channel="experimental"):
        return q.freeze("mseries-aurora20-j314s-exp1", self.pins, paths or [self.evidence], self.output, channel)

    def test_partial_hardware_tests_freeze_as_experimental_only(self):
        result = self.freeze()
        self.assertEqual(result["status"], "frozen-experimental")
        self.assertIn("energy_ab", result["unqualified_scopes"])
        self.assertFalse(result["power_improvement_claim"])
        self.assertEqual(q.verify(self.output, self.pins, [self.evidence]), result)

    def test_partial_receipt_cannot_become_stable(self):
        with self.assertRaisesRegex(ValueError, "stable blocked"):
            self.freeze(channel="stable")
        self.assertFalse(self.output.exists())

    def test_existing_release_is_never_overwritten(self):
        self.freeze()
        original = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            self.freeze()
        self.assertEqual(self.output.read_bytes(), original)

    def test_identity_digest_is_checked(self):
        data = receipt()
        data["identity"]["boot_payload_sha256"] = "e" * 64
        self.save(data)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.freeze()

    def test_no_driver_hashes_cannot_be_hardware_evidence(self):
        data = receipt()
        data["identity"]["modules"] = {}
        data["identity_sha256"] = hashlib.sha256(q.canonical(data["identity"])).hexdigest()
        self.save(data)
        with self.assertRaisesRegex(ValueError, "hashes are missing"):
            self.freeze()

    def test_different_boot_payloads_cannot_be_combined(self):
        data = receipt()
        data["identity"]["boot_payload_sha256"] = "e" * 64
        data["identity_sha256"] = hashlib.sha256(q.canonical(data["identity"])).hexdigest()
        second = self.root / "second.json"
        second.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "cannot mix"):
            self.freeze([self.evidence, second])

    def test_renaming_release_string_is_not_qualification(self):
        data = json.loads(self.pins.read_text())
        data["kernel_release"] = "unrelated"
        self.pins.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "pinned kernel release differ"):
            self.freeze()

    def test_modified_evidence_is_refused(self):
        self.freeze()
        self.save(dict(receipt(), controls_unchanged=False))
        with self.assertRaisesRegex(ValueError, "evidence missing or changed"):
            q.verify(self.output, self.pins, [self.evidence])

    def test_modified_build_pins_are_refused(self):
        self.freeze()
        self.pins.write_text(json.dumps(dict(PINS, kernel_source="wrong")))
        with self.assertRaisesRegex(ValueError, "pins changed"):
            q.verify(self.output, self.pins, [self.evidence])

    def test_manually_edited_status_is_refused(self):
        data = self.freeze()
        data["status"] = "stable-qualified"
        self.output.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "qualification label changed"):
            q.verify(self.output, self.pins, [self.evidence])

    def qualified_records(self):
        paths = []
        for index in range(3):
            data = receipt()
            data["boot_id"] = f"boot-{index}"
            data["checks"] = {name: {"result": "pass"} for name in q.STABLE_SCOPES}
            data["checks"]["suspend_resume"]["successful_cycles"] = 3
            data["checks"]["energy_ab"].update(successful_cycles=3, pairs=[{
                "order": "AB" if index % 2 == 0 else "BA", "baseline_controls_sha256": "e" * 64,
                "candidate_controls_sha256": "e" * 64, "baseline_median_w": 10, "candidate_median_w": 10.1}])
            path = self.root / f"qualified-{index}.json"
            path.write_text(json.dumps(data))
            paths.append(path)
        return paths

    def test_stable_requires_complete_test_matrix_three_boots_and_matched_pairs(self):
        paths = self.qualified_records()
        self.assertEqual(self.freeze(paths, "stable")["status"], "stable-qualified")

    def test_presence_of_all_case_names_without_cycles_is_insufficient(self):
        paths = self.qualified_records()
        for path in paths:
            data = json.loads(path.read_text()); data["checks"]["suspend_resume"]["successful_cycles"] = 0
            path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "suspend_resume needs"):
            self.freeze(paths, "stable")

    def test_unmatched_power_controls_block_stable(self):
        paths = self.qualified_records()
        data = json.loads(paths[0].read_text())
        data["checks"]["energy_ab"]["pairs"][0]["candidate_controls_sha256"] = "f" * 64
        paths[0].write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "unmatched energy controls"):
            self.freeze(paths, "stable")

    def test_power_regression_blocks_stable(self):
        paths = self.qualified_records()
        data = json.loads(paths[0].read_text())
        data["checks"]["energy_ab"]["pairs"][0]["candidate_median_w"] = 12
        paths[0].write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "energy regression"):
            self.freeze(paths, "stable")

    def test_counter_reset_is_not_negative_idle_time(self):
        before = {"state": {"name": "CPU PD", "time_us": 100, "usage": 5}}
        after = {"state": {"name": "CPU PD", "time_us": 20, "usage": 1}}
        self.assertEqual(q.idle_delta(before, after), {})

    def collect_fixture(self, messages, log_boot="abc"):
        for name, content in {"proc/sys/kernel/osrelease": PINS["kernel_release"],
                              "proc/sys/kernel/random/boot_id": "abc", "proc/device-tree/model": "M1 Pro",
                              "proc/device-tree/compatible": "apple,j314s\x00apple,t6000\x00",
                              "proc/uptime": "600 1000", "kernel-image": "kernel", "boot-image": "boot"}.items():
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
        log = self.root / "journal.jsonl"
        log.write_text("\n".join(json.dumps({"_BOOT_ID": log_boot, "MESSAGE": text}) for text in messages))
        return q.collect(self.root, self.root / "capture.json", self.root / "kernel-image", self.root / "boot-image", log, .001, .001)

    def test_repeated_pmp_started_messages_do_not_prove_readiness_and_ownership(self):
        data = self.collect_fixture(["PMP started"] * 3)
        self.assertEqual(data["checks"]["pmp_ready"]["result"], "not-run")

    def test_complete_pmp_handshake_and_ownership_is_a_scoped_pass(self):
        data = self.collect_fixture(["PMP started", "PMP firmware and endpoint ready", "PMP manages fabric and DCS p-states"])
        self.assertEqual(data["checks"]["pmp_ready"]["result"], "pass")
        self.assertEqual(data["checks"]["suspend_resume"]["result"], "not-run")

    def test_journal_from_a_different_boot_is_refused(self):
        with self.assertRaisesRegex(ValueError, "exactly the observed boot"):
            self.collect_fixture(["PMP started"], "other-boot")

    def test_unified72_snapshot_has_separate_identity_and_no_moving_branch_url(self):
        data = candidate.series("unified72")
        self.assertIn(data["source"]["commit"], data["source"]["url"])
        self.assertRegex(data["source"]["sha256"], r"^[a-f0-9]{64}$")
        self.assertTrue(data["kernel_release"]["unified72"].startswith("7.2.10-"))
        self.assertEqual(data["patches"], [])
        self.assertEqual(candidate.settings(data, "unified72")["DRM_AMDGPU"], "n")


if __name__ == "__main__":
    unittest.main()
