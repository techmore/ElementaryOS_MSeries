#!/usr/bin/python3
"""Refresh only allowlisted qualification receipt metadata; never run inference.

Maintenance helper. Reads frozen case/attempt JSON and sanitized public
copies, hashes their actual bytes separately, preserves curated classifications,
and writes only the repository's qualification-index.json. No services mutated.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

FAMILY = re.compile(r"^f5-(?:app-fixtures|app-qualified|browser-editors|debug-env|deployment|publication|joined-voice|nemotron-mlx|optional-engines|payload-fixtures|real-app-fixtures|real-app-qualified|real-tasks-qualified|sustained|voice|installed|postdeploy|installed-postdeploy)-v\d+$")
RELATIVE = re.compile(r"^(?:(?:gtk3|gtk4|qt6|brave|code|newelle|tasks)/receipt\.json|receipt\.json|attempt\.json|classification\.json|(?:gtk3|gtk4|qt6|brave|code|newelle|tasks|ane|mlx|cpu)-attempt\.json|(?:ane|mlx|cpu)\.json|audio-verification\.json|cpu-supervisor-receipt-failure\.json)$")
DYNAMIC_CLASSIFICATIONS = {
    "evidence", "incomplete-no-score", "completed evidence; quality is retained metric, not an aggregate pass",
    "supervisor-or-tool-receipt; inspect paired case for quality",
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def status(row):
    if row.get("interruption"):
        return "interrupted-unscored"
    if row.get("failure_kind") or row.get("error_kind"):
        return "terminal-failure-preserved"
    if "exit_code" in row:
        return "terminal-attempt-completed" if row["exit_code"] == 0 else "terminal-attempt-child-failed"
    if row.get("complete") is True or row.get("completed") is True:
        if "passed" in row:
            return "terminal-pass" if row["passed"] else "terminal-failure-preserved"
        return "terminal-completed-with-metrics"
    return "pending"


def classification(row, state):
    if state == "pending":
        return "incomplete-no-score"
    if row.get("failure_kind") or row.get("error_kind"):
        return "harness-or-integration-failure-unscored; inspect preserved trace before attributing product or model quality"
    if "exit_code" in row:
        return "supervisor-or-tool-receipt; inspect paired case for quality"
    return "completed evidence; quality is retained metric, not an aggregate pass"


def refresh_record(item, path, public, manifest):
    row = json.loads(path.read_text())
    if not isinstance(row, dict):
        raise ValueError("Allowlisted receipt is not an object")
    state = status(row)
    previous_class = item.get("classification")
    item.update(status=state, original_receipt_sha256=sha(path))
    item.pop("receipt_sha256", None)
    item.pop("snapshot_sha256", None)
    if previous_class is None or previous_class in DYNAMIC_CLASSIFICATIONS:
        item["classification"] = classification(row, state)
    item["failure_kind"] = row.get("failure_kind", row.get("error_kind"))
    if item["failure_kind"] is None:
        item.pop("failure_kind")
    if "exit_code" in row:
        item["child_exit_code"] = row["exit_code"]
    if row.get("interruption"):
        item["interruption"] = row["interruption"]
    else:
        item.pop("interruption", None)
    identity = row.get("identity", {})
    runtime = row.get("runtime", {})
    if isinstance(runtime, dict):
        keep = {k: runtime[k] for k in ("kernel", "engine", "backend", "threads", "library_sha256", "model_sha256", "wav_sha256", "browser", "model_revision", "model_weights_sha256") if k in runtime}
        if keep:
            item["runtime"] = keep
    source = row.get("source_sha256") or identity.get("source_sha256")
    if source:
        item["source_manifest_sha256"] = fingerprint(source)
        item["source_manifest_ref"] = item["path"] + ("#source_sha256" if "source_sha256" in row else "#identity.source_sha256")
    if row.get("harness_sha256"):
        item["harness_sha256"] = row["harness_sha256"]
    policy = row.get("policy") or identity.get("policy")
    if policy:
        item["policy_sha256"] = fingerprint(policy)
        item["policy_ref"] = item["path"] + ("#policy" if "policy" in row else "#identity.policy")
    if "trials" in row:
        item["trials"] = [{k: trial[k] for k in ("run", "complete", "resident_state", "first_text_s", "first_committed_s", "normalized_wer", "final_after_audio_s", "elapsed_s", "cpu_time_s", "cpu_s") if k in trial} for trial in row["trials"]]
    if "speech" in row:
        item["speech"] = {k: value for k, value in row["speech"].items() if k in ("exact_normalized_words", "first_committed_text_s", "audio_duration_s", "elapsed_s", "native_engine_restored")}
    if "resources" in row:
        item["resources"] = {k: value for k, value in row["resources"].items() if k in ("samples", "min_available_bytes", "max_fan_rpm", "max_temp_c", "peak_process_family_rss_sum_bytes")}
    if "source_events" in row:
        item["asr_completed_trace_available"] = any(event.get("final") for event in row["source_events"])
        item["voice_stages"] = [{k: stage[k] for k in ("completed", "failure_kind", "requested_by_actual_ui", "speech_phase_at_start", "started_s") if k in stage} for stage in row.get("voice_stages", [])]
    if "fresh_asr_inference" in row:
        item["fresh_asr_inference"] = row["fresh_asr_inference"]
    if "asr_trace_reuse" in row:
        item["parent_asr_receipt_sha256"] = row["asr_trace_reuse"].get("parent_receipt_sha256")
    if "replay_latencies" in row:
        item["replay_latencies"] = row["replay_latencies"]
        item["latency_scope"] = "Recorded ASR event replay continuation, not a fresh uninterrupted live speech trial"
    if public.is_file() and not public.is_symlink():
        item["public_receipt_sha256"] = sha(public)
        item["public_checksum_manifest_match"] = manifest.get(public.relative_to(PUBLIC).as_posix()) == item["public_receipt_sha256"]
        item["public_copy_status"] = "exported-bytes-verified" if item["public_checksum_manifest_match"] else "exported-checksum-manifest-needs-refresh"
    else:
        item.pop("public_receipt_sha256", None)
        item.pop("public_checksum_manifest_match", None)
        item["public_copy_status"] = "not-exported-yet"


parser = argparse.ArgumentParser(description=__doc__)
DEFAULT_REPO = Path(__file__).resolve().parents[2]
parser.add_argument("--work-dir", type=Path, default=DEFAULT_REPO.parent)
parser.add_argument("--repo", type=Path)
parser.add_argument("--require-public", action="store_true", help="Fail after refresh if a terminal receipt lacks matching sanitized checksum bytes")
args = parser.parse_args()
WORK = args.work_dir.resolve()
REPO = (args.repo or DEFAULT_REPO).resolve()
INDEX = REPO / "mseries/dictation/qualification-index.json"
PUBLIC = REPO / "mseries/local-ai/receipts/f5-english-2026-10-18"
data = json.loads(INDEX.read_text())
manifest = json.loads((PUBLIC / "checksums.json").read_text()) if (PUBLIC / "checksums.json").is_file() else {}
cohorts = {item["id"]: item for item in data["cohorts"]}
for directory in WORK.iterdir():
    if directory.is_dir() and not directory.is_symlink() and FAMILY.fullmatch(directory.name):
        cohorts.setdefault(directory.name, {"id": directory.name, "work_path": directory.name + "/", "public_path": "../local-ai/receipts/f5-english-2026-10-18/" + directory.name + "/", "scope": "new-cohort; coordinator must curate scope", "receipts": []})
updated = 0
missing = []
for name, cohort in sorted(cohorts.items()):
    if not FAMILY.fullmatch(name):
        raise ValueError("Index cohort is outside explicit private receipt allowlist")
    directory = WORK / name
    receipts = {item["path"]: item for item in cohort["receipts"]}
    if directory.is_dir():
        for path in directory.rglob("*.json"):
            relative = path.relative_to(directory).as_posix()
            if not path.is_symlink() and RELATIVE.fullmatch(relative):
                receipts.setdefault(relative, {"path": relative})
    for relative, item in sorted(receipts.items()):
        if not RELATIVE.fullmatch(relative):
            raise ValueError("Indexed receipt path is outside explicit allowlist")
        path = directory / relative
        if path.is_file() and not path.is_symlink():
            refresh_record(item, path, PUBLIC / name / relative, manifest)
            updated += 1
            if item["status"] != "pending" and not item.get("public_checksum_manifest_match"):
                missing.append(name + "/" + relative)
    cohort["receipts"] = list(receipts.values())
    cohort["state"] = ("pending-no-result" if not receipts else "incomplete" if any(item["status"] == "pending" for item in receipts.values()) else "terminal-preserved")
data["cohorts"] = list(cohorts.values())
data["observed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
data["receipt_hash_semantics"] = {"original_receipt_sha256": "Exact original private work JSON bytes; may contain private paths and must not be copied wholesale", "public_receipt_sha256": "Actual separately sanitized public JSON bytes, checked against public checksums.json", "missing_public_hash": "No matching sanitized copy yet; not proof of publication"}
try:
    result = subprocess.run(["systemctl", "--user", "list-units", "--all", "--plain", "--no-legend", "*qualification*"], text=True, capture_output=True, check=True, timeout=5)
    data["owned_unit_observation"] = [{"unit": parts[0], "load": parts[1], "active": parts[2], "sub": parts[3]} for line in result.stdout.splitlines() if len(parts := line.split()) >= 4 and parts[0].startswith("mseries-f5-")]
except (subprocess.SubprocessError, OSError):
    data["owned_unit_observation"] = None
data["public_copy_audit"] = {"terminal_receipts_missing_matching_public_bytes": missing, "checked_receipts": updated}
encoded = json.dumps(data, indent=2) + "\n"
if "/home/" in encoded:
    raise ValueError("Index must not publish home paths")
temporary = INDEX.with_suffix(".json.tmp")
temporary.write_text(encoded)
temporary.replace(INDEX)
print(json.dumps({"cohorts": len(cohorts), "receipts_refreshed": updated, "public_missing_or_stale": missing}))
raise SystemExit(1 if args.require_public and missing else 0)
