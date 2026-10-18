#!/usr/bin/env python3
"""Read three fixed CD321x registers; no task/configuration writes or bus scan.

The one-byte write message selects a register for the following READ in the
same I2C_RDWR transfer. It is not a command/data/configuration payload write.
The adapter locks each combined transfer, not the entire snapshot; the bound
driver's IRQ/command work can occur between reads. This is not a timeline or
proof that DATA1 belongs to any preceding role-change attempt.
"""
import argparse
import ctypes
import errno
import json
import os
from pathlib import Path
import sys

DEVICE = "/dev/i2c-0"
ADDRESS = 0x3F
I2C_RDWR = 0x0707
I2C_M_RD = 0x0001
REGISTERS = {0x08: ("CMD1", 5), 0x1A: ("STATUS", 5), 0x09: ("DATA1", 2)}


class I2CMsg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]


class I2CRdwr(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(I2CMsg)), ("nmsgs", ctypes.c_uint32)]


def validate_layout():
    # Linux aarch64 ABI, matching include/uapi/linux/{i2c,i2c-dev}.h.
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError("Requires the 64-bit Linux ABI")
    if (ctypes.sizeof(I2CMsg), I2CMsg.buf.offset,
            ctypes.sizeof(I2CRdwr), I2CRdwr.nmsgs.offset) != (16, 8, 16, 8):
        raise RuntimeError("Unexpected Linux I2C ctypes structure layout")


def validate_mapping(root=Path("/sys")):
    device = (root / "bus/i2c/devices/0-003f").resolve(strict=True)
    port = (root / "class/typec/port2").resolve(strict=True)
    driver = (device / "driver").resolve(strict=True)
    if driver.name != "tps6598x" or device not in port.parents:
        raise RuntimeError("Refusing: port2 is not under tps6598x 0-003f")
    pd = (device / "of_node").resolve(strict=True)
    bus = (root / "bus/i2c/devices/i2c-0/of_node").resolve(strict=True)
    if pd.name != "usb-pd@3f" or bus.name != "i2c@39b040000" or pd.parent != bus:
        raise RuntimeError("Refusing: unexpected fixed port2 OF controller mapping")
    return {"typec_port": "port2", "i2c_bus": 0, "address": "0x3f",
            "driver": driver.name, "of_controller": bus.name, "of_pd": pd.name}


def combined_read(fd, reg, length, ioctl):
    if reg not in REGISTERS or length != REGISTERS[reg][1]:
        raise ValueError("Register/length is outside the fixed read plan")
    pointer = (ctypes.c_uint8 * 1)(reg)
    data = (ctypes.c_uint8 * length)()
    messages = (I2CMsg * 2)(
        I2CMsg(ADDRESS, 0, 1, pointer),
        I2CMsg(ADDRESS, I2C_M_RD, length, data))
    request = I2CRdwr(messages, 2)
    # No I2C_SLAVE_FORCE, SMBus command, task write or raw os.write is used.
    result = ioctl(fd, I2C_RDWR, ctypes.byref(request))
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    if result != 2:
        raise OSError(errno.EIO, f"Expected 2 transferred messages, got {result}")
    return bytes(data)


def snapshot(fd, ioctl):
    result = []
    for reg in (0x08, 0x1A):
        result.append(read_record(fd, reg, ioctl))
    command = result[0]
    # DATA1 is read only after a valid, idle CMD1 observation. The driver can
    # still start a command between these transfers; never claim atomicity.
    if command.get("prefix_sufficient") and command.get("value_le") == 0:
        result.append(read_record(fd, 0x09, ioctl))
    else:
        result.append({"name": "DATA1", "register": "0x09", "skipped": True,
                       "reason": "CMD1 failed, had a short prefix, or was not idle"})
    return result


def read_record(fd, reg, ioctl):
    name, length = REGISTERS[reg]
    record = {"name": name, "register": f"0x{reg:02x}", "raw_length": length}
    try:
        raw = combined_read(fd, reg, length, ioctl)
        record.update(raw_hex=raw.hex(), length_prefix=raw[0],
                      prefix_sufficient=raw[0] >= length - 1, errno=0)
        if record["prefix_sufficient"]:
            record["value_le"] = int.from_bytes(raw[1:], "little")
        else:
            record["interpretation"] = "Short length prefix; driver block_read returns EIO"
    except OSError as exc:
        record.update(raw_hex=None, length_prefix=None, errno=exc.errno,
                      error=str(exc))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate ABI/mapping and print plan without opening I2C")
    args = parser.parse_args()
    validate_layout()
    report = {"mapping": validate_mapping(), "device": DEVICE,
              "snapshot_is_atomic": False,
              "read_plan": ["CMD1 0x08: 5 raw bytes", "STATUS 0x1a: 5 raw bytes",
                            "DATA1 0x09: 2 raw bytes only if valid CMD1 value is zero"]}
    if args.dry_run:
        report["dry_run"] = True
        print(json.dumps(report, indent=2))
        return 0
    if os.geteuid() != 0:
        raise RuntimeError("Run with sudo in the owner's regular Terminal")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
    libc.ioctl.restype = ctypes.c_int
    fd = os.open(DEVICE, os.O_RDWR | os.O_CLOEXEC)
    try:
        report["reads"] = snapshot(fd, libc.ioctl)
    finally:
        os.close(fd)
    print(json.dumps(report, indent=2))
    return 1 if any(item.get("errno") or item.get("prefix_sufficient") is False
                    for item in report["reads"]) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as exc:
        print(json.dumps({"inspection_failed": str(exc),
                          "errno": getattr(exc, "errno", None)}), file=sys.stderr)
        sys.exit(1)
