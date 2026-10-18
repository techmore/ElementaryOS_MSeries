#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Collect read-only hardware evidence and freeze content-addressed kernel releases.

No installation, kernel parameters, display settings, suspend, or boot selection
are changed. Frozen-experimental is explicitly different from stable-qualified.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import statistics
import time

HERE = Path(__file__).resolve().parent
STABLE_SCOPES = {"boot", "graphics", "gpu", "storage", "network", "input",
                 "suspend_resume", "recovery_boot", "thermal", "energy_ab"}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(json.dumps(data, indent=2) + "\n")


def read(path):
    try:
        return Path(path).read_text().strip().replace("\x00", " ").strip()
    except (OSError, UnicodeError):
        return None


def number(path):
    value = read(path)
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def percentile(values, fraction):
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def idle_snapshot(root):
    values = {}
    for state in sorted((root / "sys/devices/system/cpu").glob("cpu[0-9]*/cpuidle/state*")):
        label = str(state.relative_to(root / "sys/devices/system/cpu"))
        values[label] = {"name": read(state / "name"), "time_us": number(state / "time"),
                         "usage": number(state / "usage")}
    return values


def idle_delta(before, after):
    result = {}
    for key in before.keys() & after.keys():
        a, b = before[key], after[key]
        if a["name"] != b["name"]:
            continue
        if any(x is None for x in (a["time_us"], b["time_us"], a["usage"], b["usage"])):
            continue
        dt, du = b["time_us"] - a["time_us"], b["usage"] - a["usage"]
        if dt >= 0 and du >= 0:
            result[key] = {"name": b["name"], "time_us": dt, "usage": du}
    return dict(sorted(result.items()))


def context(root):
    return {
        "backlights": {p.name: {k: read(p / k) for k in ("brightness", "actual_brightness", "max_brightness")}
                       for p in (root / "sys/class/backlight").glob("*")},
        "power_supplies": {p.name: {k: read(p / k) for k in ("type", "status", "online", "capacity", "energy_now")}
                           for p in (root / "sys/class/power_supply").glob("*")},
        "drm_connectors": {p.name: {k: read(p / k) for k in ("status", "enabled", "modes")}
                           for p in (root / "sys/class/drm").glob("card*-*") if (p / "status").exists()},
        "cpufreq": {p.name: {k: read(p / k) for k in ("scaling_governor", "scaling_min_freq", "scaling_max_freq")}
                    for p in (root / "sys/devices/system/cpu/cpufreq").glob("policy*")},
        "parameters": {str(p.relative_to(root / "sys/module")): read(p)
                       for name in ("apple_pmgr_misc", "thunderbolt_apple", "appledrm")
                       for p in (root / "sys/module" / name / "parameters").glob("*")},
        "mem_sleep": read(root / "sys/power/mem_sleep"),
    }


def power_sensor(root):
    for sensor in (root / "sys/class/hwmon").glob("hwmon*"):
        if read(sensor / "name") != "macsmc_hwmon":
            continue
        for label in sensor.glob("power*_label"):
            if read(label) == "Total System Power":
                return label.with_name(label.name.replace("_label", "_input"))
    return None


def collect(root, output, kernel_image, boot_image, kernel_log, duration=30, interval=1):
    if duration <= 0 or interval <= 0 or interval > duration:
        raise ValueError("require 0 < interval <= duration")
    if Path(output).exists():
        raise ValueError("evidence already exists; choose a new receipt")
    release = read(root / "proc/sys/kernel/osrelease") or platform.release()
    boot_id = read(root / "proc/sys/kernel/random/boot_id")
    model = read(root / "proc/device-tree/model")
    compatible = read(root / "proc/device-tree/compatible")
    if not compatible or "apple,j314s" not in compatible.split():
        raise ValueError("this collector currently qualifies only the owner's J314S")
    identity = {"kernel_release": release, "board": "apple,j314s", "soc": "apple,t6000",
                "kernel_image_sha256": digest(kernel_image), "boot_payload_sha256": digest(boot_image)}
    modules = root / "usr/lib/modules" / release
    identity["modules"] = {str(p.relative_to(modules)): digest(p)
                           for pattern in ("kernel/drivers/gpu/drm/apple/appledrm.ko*", "kernel/drivers/soc/apple/apple-sep.ko*",
                                           "kernel/drivers/soc/apple/apple-pmgr-misc.ko*", "dtbs/t6000-j314s.dtb")
                           for p in modules.glob(pattern) if p.is_file()}
    before_context, before_idle = context(root), idle_snapshot(root)
    identity["runtime_parameters"] = before_context["parameters"]
    identity["feature_cmdline"] = sorted(word for word in (read(root / "proc/cmdline") or "").split()
                                         if word.startswith(("user4k=", "appledrm.", "apple_pmgr_misc.", "thunderbolt_apple.")))
    entries = [json.loads(line) for line in Path(kernel_log).read_text().splitlines() if line.strip()]
    if not entries or {entry.get("_BOOT_ID") for entry in entries} != {boot_id.replace("-", "")}:
        raise ValueError("kernel log must be journal JSON from exactly the observed boot")
    log = "\n".join(entry.get("MESSAGE", "") for entry in entries if isinstance(entry.get("MESSAGE", ""), str))
    readiness = [line for line in log.splitlines() if re.search(r"PMP firmware and endpoint ready|PMP started|PMP manages fabric", line)]
    severe = [line for line in log.splitlines() if re.search(r"Oops:|BUG:|Kernel panic|watchdog:.*lockup", line)]
    sensor, samples = power_sensor(root), []
    started = time.monotonic()
    while True:
        if sensor:
            value = number(sensor)
            if value is not None and value >= 0:
                samples.append({"elapsed_s": round(time.monotonic() - started, 3), "watts": value / 1e6})
        remaining = duration - (time.monotonic() - started)
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    if read(root / "proc/sys/kernel/random/boot_id") != boot_id:
        raise ValueError("boot changed during sampling")
    after_context = context(root)
    # Battery energy naturally changes; brightness/modes/online/status must not.
    def controls(data):
        result = json.loads(json.dumps(data))
        for supply in result["power_supplies"].values():
            supply.pop("energy_now", None)
            supply.pop("capacity", None)
        return result
    fixed_controls = controls(before_context) == controls(after_context)
    uptime = float((read(root / "proc/uptime") or "0").split()[0])
    idle = idle_delta(before_idle, idle_snapshot(root))
    checks = {
        "boot": {"result": "pass" if uptime >= 300 else "not-run", "scope": "running boot observed >=300 seconds; no recovery/soak claim", "uptime_s": uptime},
        "pmp_ready": {"result": "pass" if len(readiness) >= 3 else "not-run", "scope": "firmware ready and PMGR ownership messages", "lines": readiness},
        "cpu_idle_accounting": {"result": "pass" if idle and any(v["time_us"] > 0 for v in idle.values()) else "not-run", "scope": "nonnegative per-CPU idle-counter deltas; no efficiency improvement claim"},
        "kernel_severe_log": {"result": "fail" if severe else "pass", "scope": "selected severe messages in supplied current-boot log only", "lines": severe},
    }
    for scope in STABLE_SCOPES - checks.keys():
        checks[scope] = {"result": "not-run", "scope": "requires dedicated hardware acceptance evidence"}
    watts = [s["watts"] for s in samples]
    receipt = {"schema": 1, "kind": "hardware-test", "captured_at": datetime.now(timezone.utc).isoformat(),
               "identity": identity, "identity_sha256": hashlib.sha256(canonical(identity)).hexdigest(),
               "boot_id": boot_id, "model": model, "status": "hardware-tested-scoped; incomplete qualification",
               "context_before": before_context, "context_after": after_context, "controls_unchanged": fixed_controls,
               "duration_s": round(time.monotonic() - started, 3), "checks": checks, "idle_deltas": idle,
               "power": {"source": "macsmc_hwmon Total System Power", "samples": samples,
                         "summary": {"n": len(watts), "median_w": statistics.median(watts), "p10_w": percentile(watts, .1), "p90_w": percentile(watts, .9)} if watts else None,
                         "interpretation": "observational; active workloads uncontrolled; not an A/B or claimed saving"}}
    write_new(output, receipt)
    return receipt


def validate_receipt(receipt):
    identity = receipt["identity"]
    if receipt.get("schema") != 1 or receipt.get("kind") != "hardware-test":
        raise ValueError("not a hardware-test receipt")
    if receipt.get("identity_sha256") != hashlib.sha256(canonical(identity)).hexdigest():
        raise ValueError("receipt identity digest mismatch")
    for key in ("kernel_image_sha256", "boot_payload_sha256"):
        if not re.fullmatch(r"[a-f0-9]{64}", identity.get(key, "")):
            raise ValueError(f"missing measured identity: {key}")
    modules = identity.get("modules", {})
    if not modules or not any("appledrm.ko" in name for name in modules) or "dtbs/t6000-j314s.dtb" not in modules:
        raise ValueError("required driver and J314S DTB hashes are missing")
    if any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in modules.values()):
        raise ValueError("invalid module hashes")
    if not receipt.get("boot_id") or identity.get("board") != "apple,j314s":
        raise ValueError("missing boot or supported board identity")
    if not isinstance(identity.get("runtime_parameters"), dict) or identity["runtime_parameters"] != receipt.get("context_before", {}).get("parameters"):
        raise ValueError("runtime parameter identity is missing or inconsistent")
    if not receipt.get("checks") or any(c.get("result") not in {"pass", "fail", "not-run"} for c in receipt["checks"].values()):
        raise ValueError("invalid test results")
    return identity


def freeze(release_id, pins_path, evidence_paths, output, channel="experimental"):
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{2,100}", release_id):
        raise ValueError("invalid immutable release id")
    pins = json.loads(Path(pins_path).read_text())
    records = [json.loads(Path(p).read_text()) for p in evidence_paths]
    if not records:
        raise ValueError("hardware evidence is required")
    identities = [validate_receipt(record) for record in records]
    if any(identity != identities[0] for identity in identities):
        raise ValueError("cannot mix kernel, modules, board or boot-payload identities")
    if identities[0]["kernel_release"] != pins["kernel_release"]:
        raise ValueError("hardware evidence and pinned kernel release differ")
    failed = sorted({scope for r in records for scope, check in r["checks"].items() if check["result"] == "fail"})
    passed = sorted({scope for r in records for scope, check in r["checks"].items() if check["result"] == "pass"})
    missing = sorted(STABLE_SCOPES - set(passed))
    boots = {r["boot_id"] for r in records}
    if channel not in {"experimental", "stable"}:
        raise ValueError("unknown release channel")
    if channel == "stable":
        if failed or missing or len(boots) < 3:
            raise ValueError(f"stable blocked: failures={failed}, missing={missing}, distinct boots={len(boots)} (need 3)")
        for scope in ("suspend_resume", "energy_ab"):
            count = max((r["checks"].get(scope, {}).get("successful_cycles", 0) for r in records), default=0)
            if count < 3:
                raise ValueError(f"stable blocked: {scope} needs >=3 successful cycles/pairs")
        pairs = [pair for r in records for pair in r["checks"].get("energy_ab", {}).get("pairs", [])]
        if len(pairs) < 3:
            raise ValueError("stable blocked: missing measured energy pairs")
        for index, pair in enumerate(pairs):
            if pair.get("order") != ("AB" if index % 2 == 0 else "BA"):
                raise ValueError("stable blocked: energy pair order must alternate AB/BA")
            if not re.fullmatch(r"[a-f0-9]{64}", pair.get("baseline_controls_sha256", "")) or pair.get("baseline_controls_sha256") != pair.get("candidate_controls_sha256"):
                raise ValueError("stable blocked: unmatched energy controls")
            for key in ("baseline_median_w", "candidate_median_w"):
                value = pair.get(key)
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                    raise ValueError("stable blocked: invalid energy measurements")
            if pair["candidate_median_w"] > pair["baseline_median_w"] * 1.10:
                raise ValueError("stable blocked: energy regression above 10% acceptance budget")
        if any(not r.get("controls_unchanged") for r in records):
            raise ValueError("stable blocked: experimental controls changed during capture")
    result = {"schema": 1, "id": release_id, "channel": channel, "frozen": True,
              "status": "stable-qualified" if channel == "stable" else "frozen-experimental",
              "identity": identities[0], "upstream_pins": pins, "pins_sha256": digest(pins_path),
              "evidence": [{"file": Path(p).name, "sha256": digest(p), "boot_id": r["boot_id"]} for p, r in zip(evidence_paths, records)],
              "tested_scopes": passed, "failed_scopes": failed, "unqualified_scopes": missing,
              "distinct_boots": len(boots), "power_improvement_claim": False,
              "release_policy": "frozen bytes; updates create a new release id; no automatic installation or default selection"}
    write_new(output, result)
    return result


def verify(frozen, pins_path, evidence_paths):
    manifest = json.loads(Path(frozen).read_text())
    if manifest.get("schema") != 1 or not manifest.get("frozen"):
        raise ValueError("invalid frozen manifest")
    if digest(pins_path) != manifest["pins_sha256"]:
        raise ValueError("frozen build pins changed")
    if json.loads(Path(pins_path).read_text()) != manifest["upstream_pins"]:
        raise ValueError("frozen pin contents differ")
    supplied = {Path(p).name: p for p in evidence_paths}
    if len(supplied) != len(evidence_paths):
        raise ValueError("duplicate evidence names")
    for expected in manifest["evidence"]:
        path = supplied.get(expected["file"])
        if path is None or digest(path) != expected["sha256"]:
            raise ValueError("frozen evidence missing or changed")
        if validate_receipt(json.loads(Path(path).read_text())) != manifest["identity"]:
            raise ValueError("frozen hardware identity differs")
    # Recompute every promotion field instead of trusting an edited status label.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        expected = freeze(manifest["id"], pins_path, evidence_paths, Path(tmp) / "verify.json", manifest["channel"])
    if expected != manifest:
        raise ValueError("frozen manifest contents or qualification label changed")
    return manifest


def verify_binary_proof(proof_path, evidence_path, pins_path):
    proof = json.loads(Path(proof_path).read_text())
    record = json.loads(Path(evidence_path).read_text())
    identity = validate_receipt(record)
    pins = json.loads(Path(pins_path).read_text())
    prefix = f"usr/lib/modules/{pins['kernel_release']}/"
    expected = {prefix + "vmlinuz": identity["kernel_image_sha256"],
                **{prefix + name: value for name, value in identity["modules"].items()}}
    if proof.get("evidence_sha256") != digest(evidence_path) or proof.get("upstream_archive") != pins["assets"]["kernel"] or proof.get("verified_files") != expected:
        raise ValueError("binary proof does not bind the hardware files to the pinned upstream archive")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("collect")
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--kernel-image", type=Path, required=True)
    capture.add_argument("--boot-image", type=Path, required=True)
    capture.add_argument("--kernel-log", type=Path, required=True)
    capture.add_argument("--duration", type=float, default=30)
    capture.add_argument("--interval", type=float, default=1)
    for name in ("freeze", "verify"):
        sub = commands.add_parser(name)
        sub.add_argument("--pins", type=Path, default=HERE / "release.json")
        sub.add_argument("--evidence", type=Path, action="append", required=True)
        if name == "freeze":
            sub.add_argument("--id", required=True)
            sub.add_argument("--channel", choices=("experimental", "stable"), default="experimental")
            sub.add_argument("--output", type=Path, required=True)
        else:
            sub.add_argument("manifest", type=Path)
            sub.add_argument("--binary-proof", type=Path)
    args = parser.parse_args()
    if args.command == "collect":
        result = collect(Path("/"), args.output, args.kernel_image, args.boot_image, args.kernel_log, args.duration, args.interval)
    elif args.command == "freeze":
        result = freeze(args.id, args.pins, args.evidence, args.output, args.channel)
    else:
        result = verify(args.manifest, args.pins, args.evidence)
        if args.binary_proof:
            if len(args.evidence) != 1:
                parser.error("binary proof verifies exactly one hardware receipt")
            verify_binary_proof(args.binary_proof, args.evidence[0], args.pins)
    print(json.dumps({k: result[k] for k in ("status", "tested_scopes", "unqualified_scopes") if k in result}, indent=2))


if __name__ == "__main__":
    main()
