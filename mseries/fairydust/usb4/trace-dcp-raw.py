# SPDX-License-Identifier: GPL-2.0-or-later
"""Load AFTER upstream trace_dcp.py, before guest start.

Preserve the raw DPTX service payload before firmware-specific decoding.
In particular, upstream validateConnection logs decoded fields only. No
hardware writes are introduced; all bytes were already read by that tracer.
"""
from functools import wraps


def install_raw_dptx(service_class, dump):
    if service_class.__dict__.get("_dock_raw_enabled", False):
        raise ValueError("Raw DPTX logging is already installed")

    def wrap(original, direction):
        @wraps(original)
        def logged(self, group, command, data):
            self.log(f"DPTX_RAW {direction} group={group} command={command} "
                     f"length={len(data) if data is not None else 0}")
            if data is not None:
                dump(data, print_fn=self.log)
            return original(self, group, command, data)
        return logged

    methods = (("handle_cmd", "command"), ("handle_reply", "reply"),
               ("handle_notify", "notify"), ("handle_notify_ack", "notify_ack"))
    originals = [(name, getattr(service_class, name), direction)
                 for name, direction in methods]
    for name, original, direction in originals:
        setattr(service_class, name, wrap(original, direction))
    service_class._dock_raw_enabled = True


if "hv" in globals():
    if "DCPDPTXPortEpicTracer" not in globals() or "chexdump" not in globals():
        raise ValueError("Load upstream trace_dcp.py before trace-dcp-raw.py")
    install_raw_dptx(DCPDPTXPortEpicTracer, chexdump)
    hv.show_timestamps = True
    hv.log("DPTX_RAW_READY: raw DPTX service payloads enabled before guest start")
