#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Read-only host inventory. Does not identify the separate Linux stub firmware.
set -euo pipefail
export LC_ALL=C
if [[ $(uname -s) != Darwin ]]; then
    printf 'Run this inventory on the M4 mini in macOS.\n' >&2
    exit 2
fi
printf 'macOS version\n'
sw_vers
printf '\nModel and installed memory\n'
sysctl hw.model hw.memsize
m4_types=$(system_profiler -listDataTypes)
if [[ $m4_types == *SPHardwareDataType* ]]; then
    printf '\nHost boot firmware\n'
    system_profiler SPHardwareDataType | sed -n -E '/^[[:space:]]*(Model Identifier|Chip|Memory|System Firmware Version|OS Loader Version):/p'
fi
if [[ $m4_types == *SPEthernetDataType* ]]; then
    printf '\nEthernet PCI identity\n'
    system_profiler SPEthernetDataType | sed -n -E '/^[[:space:]]*(Type|Bus|Vendor ID|Device ID|Subsystem Vendor ID|Subsystem ID|Revision ID|BSD name):/p'
fi
if [[ $m4_types == *SPDisplaysDataType* ]]; then
    printf '\nConnected display modes\n'
    system_profiler SPDisplaysDataType | sed -n -E '/^[[:space:]]*(Chipset Model|Display Type|Resolution|UI Looks like|Main Display|Online|Connection Type):/p'
fi
printf '\nRoot APFS capacity\n'
diskutil info / | sed -n -E '/^[[:space:]]*(Disk Size|Container Total Space|Container Free Space|APFS Container Reference|FileVault):/p'
if [[ -d /System/Volumes/Data ]]; then
    printf '\nData volume available space (1 KiB blocks)\n'
    df -k /System/Volumes/Data
fi
