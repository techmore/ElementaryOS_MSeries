#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read preserved Apple device-tree RAM and print only DP-IN wiring metadata.

No MMIO registers, kernel parameters, boot files, or account data are written.
Use --from-file for an existing ADT dump. The live path may require root.
ADT layout follows AsahiLinux/m1n1 proxyclient/m1n1/adt.py (GPL-2.0-or-later).
"""

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import plistlib
import re
import struct


@dataclass
class Node:
    props: dict
    parent: object = None
    children: list = field(default_factory=list)

    @property
    def name(self):
        return self.props.get("name", b"").split(b"\0", 1)[0].decode("ascii")

    @property
    def path(self):
        if self.parent is None:
            return ""
        return self.parent.path + "/" + self.name


def parse_adt(data):
    offset = 0
    total = 0

    def take(size):
        nonlocal offset
        if size < 0 or offset + size > len(data):
            raise ValueError("Truncated ADT")
        result = data[offset:offset + size]
        offset += size
        return result

    def node(parent=None, depth=0):
        nonlocal offset, total
        total += 1
        if depth > 64 or total > 10000:
            raise ValueError("ADT exceeds parser bounds")
        nprops, nchildren = struct.unpack("<II", take(8))
        if nprops > 4096 or nchildren > 4096:
            raise ValueError("Invalid ADT counts")
        current = Node({}, parent)
        for _ in range(nprops):
            name = take(32).split(b"\0", 1)[0].decode("ascii")
            size = struct.unpack("<I", take(4))[0] & 0x7fffffff
            current.props[name] = take(size)
            take((-size) % 4)
        current.children = [node(current, depth + 1) for _ in range(nchildren)]
        return current

    return node()


def walk(root):
    yield root
    for child in root.children:
        yield from walk(child)


def parse_ioreg(data):
    """Import an ioreg -a -l -p IODeviceTree archive without publishing it.

    ADT binary properties retain their bytes in the plist; registry names may
    append @unit-address. Refuse ambiguous multiple roots and invalid names.
    """
    archive = plistlib.loads(data)
    # macOS 26 ioreg emits the root dictionary directly; older exports may
    # wrap it in a one-item array. Neither form permits multiple roots.
    if isinstance(archive, dict):
        archive = [archive]
    if not isinstance(archive, list) or len(archive) != 1:
        raise ValueError("Expected one IODeviceTree archive root")
    total = 0

    def node(entry, parent=None, depth=0):
        nonlocal total
        total += 1
        if not isinstance(entry, dict) or depth > 64 or total > 10000:
            raise ValueError("Invalid or oversized IODeviceTree archive")
        props = {key: value for key, value in entry.items()
                 if isinstance(key, str) and isinstance(value, bytes)}
        name = props.get("name", entry.get("IORegistryEntryName", ""))
        if isinstance(name, bytes):
            name = name.split(b"\0", 1)[0].decode("ascii")
        if not name:
            # Some live exports blank the original ADT name (memory-map),
            # while retaining the registry name. Anonymous IOMedia leaves
            # have neither and carry no ADT wiring; omit those leaves only.
            name = entry.get("IORegistryEntryName", "")
        if not name and parent is not None and not entry.get("IORegistryEntryChildren"):
            if not any(key in props for key in ("reg", "ranges", "AAPL,phandle")):
                return None
        if not isinstance(name, str) or not name:
            raise ValueError("Missing IODeviceTree node name")
        props["name"] = name.split("@", 1)[0].encode("ascii") + b"\0"
        current = Node(props, parent)
        children = entry.get("IORegistryEntryChildren", [])
        if not isinstance(children, list):
            raise ValueError("Invalid IODeviceTree children")
        current.children = [parsed for child in children
                            if (parsed := node(child, current, depth + 1)) is not None]
        return current

    return node(archive[0])


def u32(raw):
    return struct.unpack("<I", raw)[0]


def registers(node):
    raw = node.props.get("reg", b"")
    if not raw:
        return []
    parent = node.parent
    if (u32(parent.props.get("#address-cells", struct.pack("<I", 2))),
        u32(parent.props.get("#size-cells", struct.pack("<I", 2)))) != (2, 2):
        raise ValueError("Expected 64-bit ADT address/size cells")
    if len(raw) % 16:
        raise ValueError("Invalid ADT reg length")
    result = []
    for address, size in struct.iter_unpack("<QQ", raw):
        bus_address = address
        ancestor = parent
        while ancestor is not None and "ranges" in ancestor.props:
            ranges = ancestor.props["ranges"]
            if len(ranges) % 24:
                raise ValueError("Expected 64-bit ADT ranges")
            for start, translated, length in struct.iter_unpack("<QQQ", ranges):
                if start <= address < start + length:
                    address += translated - start
                    break
            ancestor = ancestor.parent
        result.append({"bus_address": hex(bus_address), "address": hex(address),
                       "size": hex(size)})
    return result


def summarize(root, context=False):
    nodes = list(walk(root))
    phandles = {u32(n.props["AAPL,phandle"]): n.path for n in nodes
                if len(n.props.get("AAPL,phandle", b"")) == 4}
    result = []
    for node in nodes:
        target = r"atc\d+-(?:dpin[01]|dpxbar|dpphy)"
        if context:
            target = r"(?:atc-phy\d+|acio\d+|dcp\d*|dcpext\d+|dart-(?:dcp|disp)(?:ext)?\d*|display-crossbar.*|pmgr)"
        if not re.fullmatch(target, node.name):
            continue
        item = {"path": node.path, "registers": registers(node),
                "property_sizes": {key: len(value) for key, value in node.props.items()}}
        item["compatible"] = node.props.get("compatible", b"").rstrip(b"\0").decode("ascii").split("\0")
        for key in ("acio-parent", "atc-phy", "dpxbar-parent", "dp-switch-parent", "interrupt-parent",
                    "dp-switch-dfp-endpoint", "dp-switch-dfp-port", "transport-index",
                    "transport-type", "transport-tunneled", "port-number", "port-type"):
            raw = node.props.get(key)
            if raw is not None and len(raw) == 4:
                value = u32(raw)
                item[key] = {"phandle": value, "path": phandles.get(value)} if key.endswith("parent") or key == "atc-phy" else value
        for key in ("interrupts", "clock-ids", "clock-gates", "power-gates"):
            raw = node.props.get(key)
            if raw is not None and len(raw) % 4 == 0:
                item[key] = [value for (value,) in struct.iter_unpack("<I", raw)]
        result.append(item)
    if not result and not context:
        raise ValueError("No Apple ATC DP-IN/crossbar nodes found")
    return result


def read_live():
    # Read the region explicitly labelled ADT by m1n1, never guessed MMIO.
    base = Path("/sys/firmware/devicetree/base/reserved-memory")
    candidates = [p for p in base.glob("flash@*")
                  if (p / "label").exists() and (p / "label").read_bytes().rstrip(b"\0") == b"adt"]
    if len(candidates) != 1:
        raise ValueError("Expected exactly one m1n1 ADT reserved-memory region")
    address, size = struct.unpack(">QQ", (candidates[0] / "reg").read_bytes())
    if not 8 <= size <= 16 * 1024 * 1024:
        raise ValueError("Invalid reserved ADT size")
    for entry in Path("/sys/class/mtd").glob("mtd[0-9]*"):
        if not re.fullmatch(r"mtd\d+", entry.name):
            continue
        if (entry / "name").read_text().strip() == "adt":
            with Path("/dev/" + entry.name + "ro").open("rb") as source:
                return source.read(size)
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_CLOEXEC)
    try:
        data = os.pread(fd, size, address)
    finally:
        os.close(fd)
    if len(data) != size:
        raise ValueError("Short reserved ADT read")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--from-file", type=Path, help="Existing binary Apple ADT")
    source.add_argument("--from-ioreg", type=Path,
                        help="macOS ioreg -a -l -p IODeviceTree plist")
    args = parser.parse_args()
    try:
        if args.from_ioreg:
            root = parse_ioreg(args.from_ioreg.read_bytes())
        else:
            data = args.from_file.read_bytes() if args.from_file else read_live()
            root = parse_adt(data)
        # Use a basename so public summaries don't expose a local account path.
        origin = args.from_ioreg or args.from_file
        print(json.dumps({"source": origin.name if origin else "m1n1 reserved ADT RAM",
                          "nodes": summarize(root),
                          "context": summarize(root, context=True)}, indent=2))
    except (OSError, ValueError, struct.error, UnicodeError,
            plistlib.InvalidFileException) as error:
        parser.exit(1, f"ADT inspection failed: {error}\n")


if __name__ == "__main__":
    main()
