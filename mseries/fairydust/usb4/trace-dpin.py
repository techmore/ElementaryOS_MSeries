# SPDX-License-Identifier: GPL-2.0-or-later
"""m1n1 run_guest.py hook: trace the selected crossbar AND both DP-IN blocks.

Prepare only on Linux. Execution requires a second host and macOS under m1n1.
TRACE_DPIN_XBAR must be the confirmed physical crossbar address from the ADT.
This hook registers MMIO tracing; it does not write device registers itself.
"""
import os
import re


def install_dpin_trace(hypervisor, xbar_address):
    candidates = []
    for node in hypervisor.adt["/arm-io"]:
        if re.fullmatch(r"atc\d+-dpxbar", node.name):
            if node.get_reg(0)[0] == xbar_address:
                candidates.append(node)
    if len(candidates) != 1:
        raise ValueError("Expected one guest crossbar at the confirmed address; "
                         "check the ADT and use a proxy port distinct from the dock port")
    xbar = candidates[0]
    prefix = xbar.name.removesuffix("-dpxbar")
    plan = []
    for suffix in ("dpxbar", "dpin0", "dpin1"):
        path = f"/arm-io/{prefix}-{suffix}"
        try:
            node = hypervisor.adt[path]
        except KeyError:
            raise ValueError(f"Missing guest node {path}; do not capture a partial DP-IN trace") from None
        if not 1 <= len(node.reg) <= 8:
            raise ValueError(f"Unexpected reg count for {path}")
        ranges = [node.get_reg(i) for i in range(len(node.reg))]
        if any(size <= 0 or size > 0x100000 for _, size in ranges):
            raise ValueError(f"Unexpected MMIO extent for {path}")
        plan.append((path, ranges))
    # Validate the complete capture before registering any tracer.
    for path, ranges in plan:
        for index, (address, size) in enumerate(ranges):
            print(f"DPIN_TRACE {path} reg[{index}] address={address:#x} size={size:#x}")
        hypervisor.trace_device(path, True)
    return plan


if "hv" in globals():
    if "TRACE_DPIN_XBAR" not in os.environ:
        raise ValueError("Set TRACE_DPIN_XBAR to the ADT-confirmed dock crossbar address")
    install_dpin_trace(hv, int(os.environ["TRACE_DPIN_XBAR"], 0))
