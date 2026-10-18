#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Read-only macOS baseline collector. Run with bash; no Python/Xcode/sudo needed.
# Creates a NEW local capture directory; never uploads or changes system settings.
set -eu
umask 077

if [ "$(uname -s)" != Darwin ]; then
    echo 'Run this collector on macOS. It cannot collect macOS state from Linux.' >&2
    exit 2
fi
if [ "$#" -ne 2 ]; then
    echo 'Usage: bash collect-macos-dock.sh NEW_CAPTURE_DIRECTORY STATE_LABEL' >&2
    echo 'Example: bash collect-macos-dock.sh "$PWD/dock-capture/01-attached" attached' >&2
    exit 2
fi
capture_dir=$1
state_label=$2
case "$state_label" in
    attached|screen-off|screen-on|before-hdmi|after-hdmi|guest-attached) ;;
    *) echo 'Unknown state label; use one of the documented labels.' >&2; exit 2 ;;
esac
if [ -e "$capture_dir" ]; then
    echo 'Destination already exists; choose a new directory to preserve prior evidence.' >&2
    exit 2
fi
mkdir -p "$capture_dir/PRIVATE" "$capture_dir/REVIEW"
capture_dir=$(cd "$capture_dir" && pwd)
failed=0

collect() {
    capture_name=$1
    shift
    echo "Collecting $capture_name ..."
    if "$@" > "$capture_dir/PRIVATE/$capture_name" 2> "$capture_dir/PRIVATE/$capture_name.stderr"; then
        printf '%s\tOK\n' "$capture_name" >> "$capture_dir/REVIEW/status.tsv"
    else
        capture_rc=$?
        printf '%s\tFAILED:%s\n' "$capture_name" "$capture_rc" >> "$capture_dir/REVIEW/status.tsv"
        failed=$((failed + 1))
    fi
}

{
    printf 'state=%s\n' "$state_label"
    date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
    sw_vers
    printf 'model='
    sysctl -n hw.model
} > "$capture_dir/REVIEW/platform.txt"
collect iodevicetree.plist ioreg -a -l -p IODeviceTree
collect ioservice.plist ioreg -a -l -p IOService
collect display-dock-usb.plist system_profiler -xml SPDisplaysDataType SPThunderboltDataType SPUSBDataType
collect root-volume.plist diskutil info -plist /
collect apfs-layout.plist diskutil apfs list -plist
collect kernelcache-paths.txt find /System/Volumes/Preboot -type f -name kernelcache
collect display-kernel.log /usr/bin/log show --last 10m --style compact --predicate \
    'process == "kernel" AND (eventMessage CONTAINS[c] "DCP" OR eventMessage CONTAINS[c] "DPTX" OR eventMessage CONTAINS[c] "DPIN" OR eventMessage CONTAINS[c] "DisplayPort" OR eventMessage CONTAINS[c] "Thunderbolt" OR eventMessage CONTAINS[c] "HPD")'

# A successful command with empty/invalid critical XML must not look complete.
for capture_name in iodevicetree.plist ioservice.plist display-dock-usb.plist; do
    if [ ! -s "$capture_dir/PRIVATE/$capture_name" ] ||
       ! plutil -lint "$capture_dir/PRIVATE/$capture_name" > /dev/null 2>&1; then
        printf '%s\tINVALID_OR_EMPTY\n' "$capture_name" >> "$capture_dir/REVIEW/status.tsv"
        failed=$((failed + 1))
    fi
done
printf 'Describe visible picture, input, resolution/refresh, physical Mac port, dock HDMI socket, and monitor model here.\n' \
    > "$capture_dir/REVIEW/observations.txt"
(
    cd "$capture_dir/PRIVATE"
    shasum -a 256 ./*
) > "$capture_dir/REVIEW/private-sha256.txt"
printf 'Collection saved. Failed/invalid checks: %s\n' "$failed"
printf 'Review status: %s/REVIEW/status.tsv\n' "$capture_dir"
printf 'PRIVATE contains raw device identifiers and logs. Keep it local. REVIEW also needs inspection before publication.\n'
printf 'No dock cable change, display setting, boot setting, or upload was performed.\n'
if [ "$failed" -ne 0 ]; then exit 1; fi
