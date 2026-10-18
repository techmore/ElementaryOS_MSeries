#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Snapshot all public Aurora refs/PRs and compare pinned energy implementations.

Discovery only. Never updates build pins, installs a kernel or promotes a release.
Unchanged immutable heads reuse their already-recorded graph comparison.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import quote
import urllib.request

from release import HERE, PINS
from qualification import write_new

REPO = "omacom/linux-aurora"
ENERGY_FILES = ["drivers/soc/apple/apple-pmgr-misc.c", "drivers/soc/apple/pmp.rs",
                "drivers/soc/apple/pmp_power.rs", "drivers/soc/apple/pmp_bootargs.rs",
                "drivers/cpuidle/cpuidle-apple.c", "drivers/cpufreq/apple-soc-cpufreq.c",
                "drivers/nvme/host/apple.c", "arch/arm64/boot/dts/apple/t6000-j314s.dts",
                "tools/asahi/pmp-power-tests.rs", "tools/asahi/pmp-bootargs-tests.rs"]


def api(endpoint, paginate=False):
    args = ["gh", "api"] + (["--paginate"] if paginate else []) + [endpoint]
    text = subprocess.check_output(args, text=True)
    decoder, pages = json.JSONDecoder(), []
    while text.strip():
        value, length = decoder.raw_decode(text.lstrip())
        pages.append(value)
        text = text.lstrip()[length:]
    if paginate:
        return [item for page in pages for item in page]
    return pages[0]


def audit(previous, output):
    prior = json.loads(Path(previous).read_text())
    prior_by_name = {branch["name"]: branch for branch in prior["branches"]}
    metadata = api(f"repos/{REPO}")
    branches = api(f"repos/{REPO}/branches?per_page=100", True)
    prs = api(f"repos/{REPO}/pulls?state=open&per_page=100", True)
    unified = json.loads((HERE / "unified72/series.json").read_text())["source"]

    def compare(branch):
        name, head = branch["name"], branch["commit"]["sha"]
        previous_branch = prior_by_name.get(name)
        if prior["base_kernel_source"] == PINS["kernel_source"] and previous_branch and previous_branch["head"] == head:
            result = dict(previous_branch)
            result["graph_evidence"] = "same immutable base/head as prior receipt; graph result reused"
        else:
            data = api(f"repos/{REPO}/compare/{PINS['kernel_source']}...{head}")
            result = {"name": name, "head": head, "status": data["status"], "ahead_by": data["ahead_by"],
                      "behind_by": data["behind_by"], "merge_base": data["merge_base_commit"]["sha"],
                      "files_returned": len(data.get("files", [])), "files_may_be_capped": len(data.get("files", [])) >= 300,
                      "decision": "review_required", "compare_url": data["html_url"],
                      "graph_evidence": "fresh GitHub immutable comparison"}
            if name == "fix/t8140-j700-internal-display-dart":
                result.update(decision="other_hardware_candidate", reason="J700/T8140 display-DART fix; no J314S compatible")
        return result

    with ThreadPoolExecutor(max_workers=6) as executor:
        comparisons = list(executor.map(compare, branches))

    def source_hash(path):
        hashes = {}
        for lane, commit in (("aurora20", PINS["kernel_source"]), ("unified72", unified["commit"])):
            url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{path}"
            data = urllib.request.urlopen(url, timeout=45).read()
            hashes[lane] = hashlib.sha256(data).hexdigest()
        return {"path": path, "sha256": hashes, "byte_identical": len(set(hashes.values())) == 1}

    with ThreadPoolExecutor(max_workers=6) as executor:
        files = list(executor.map(source_hash, ENERGY_FILES))
    result = {"schema": 1, "captured_at": datetime.now(timezone.utc).isoformat(), "repository": REPO,
              "base_kernel_source": PINS["kernel_source"], "previous_receipt": Path(previous).name,
              "previous_receipt_sha256": hashlib.sha256(Path(previous).read_bytes()).hexdigest(),
              "default_branch": metadata["default_branch"],
              "default_branch_head": next(b["commit"]["sha"] for b in branches if b["name"] == metadata["default_branch"]),
              "branch_count": len(branches), "branches": comparisons,
              "open_pr_count": len(prs),
              "open_prs": [{"number": pr["number"], "title": pr["title"], "head": pr["head"]["sha"],
                            "repository": pr["head"]["repo"]["full_name"], "draft": pr["draft"],
                            "url": pr["html_url"], "body_sha256": hashlib.sha256((pr["body"] or "").encode()).hexdigest()}
                           for pr in prs],
              "pinned_unified72_source": unified, "energy_source_comparison": files,
              "limits": ["Complete branch and open-PR inventory, targeted energy source review; not a full kernel security audit.",
                         "GitHub PR commits endpoint is capped at 250 and comparison files at 300; neither is treated as complete source coverage.",
                         "Upstream J316S reports are contributor evidence, not local J314S qualification.",
                         "No automatic build-pin update or performance claim."]}
    write_new(output, result)
    print(f"Recorded {len(branches)} branches, {len(prs)} open PRs, {len(files)} immutable source comparisons")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, default=HERE / "branch-audits/2026-10-17.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.previous, args.output)
