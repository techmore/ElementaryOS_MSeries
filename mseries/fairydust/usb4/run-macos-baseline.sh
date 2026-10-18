#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# One-shot macOS baseline visit for the WD22TB4 video investigation.
#
# WHAT THIS DOES
#   Runs the read-only macOS baseline collection described in
#   MACOS-CUTOVER-CHECKLIST.md sections B and C, in a single paste:
#     1. downloads the reviewed tools from GitHub at a pinned commit,
#        verifying each file's SHA-256 before use;
#     2. runs collect-macos-dock.sh (state "attached") into a new capture dir;
#     3. parses the captured IODeviceTree into DP-IN metadata, if python3 exists;
#     4. inventories the Preboot kernelcache and copies it only when exactly
#        one candidate exists (never guesses UUIDs);
#     5. appends auto-detected facts to REVIEW/observations.txt.
#
# WHAT THIS DOES NOT DO
#   No sudo is requested except for the read-only Preboot kernelcache search
#   and the single unambiguous kernelcache copy. It installs nothing, changes
#   no boot/display/security setting, moves no cable, sleeps nothing and
#   uploads nothing. Raw output stays in the capture directory on this Mac.
#
# USAGE (on macOS, in Terminal)
#   bash run-macos-baseline.sh
# Options
#   --dry-run   print the plan and exit (works on any OS; used for CI checks)
#   --no-kernelcache   skip the sudo kernelcache inventory/copy
#
# The downloads are pinned to the commit below. Each file's expected SHA-256
# is embedded; a mismatch aborts that step rather than trusting the network.

set -u

PIN="${BASELINE_COMMIT:-6dad972155aeb09672708615d69738ba68504b15}"
BASE="https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/${PIN}/mseries/fairydust/usb4"

EXP_COLLECTOR="5da6ad5502b08a021a458291fafa71197ed1151b72634af4dcd304ffb63523a3"
EXP_PARSER="ce39c6a416c459bb60d2f5632c420441a6cf2e2ac2412a2607f25eee73b152c7"
EXP_CHECKLIST="9589f321ce6405562dde2b102edb77604e16a893e14659a421827536e193b3b2"

DRY_RUN=0
DO_KERNELCACHE=1
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --no-kernelcache) DO_KERNELCACHE=0 ;;
        -h|--help)
            sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s ==\n' "$*"; }

plan() {
    say "Pinned commit : ${PIN}"
    say "Tool base URL : ${BASE}"
    say "Capture dir   : \$HOME/Documents/wd22tb4-capture-<UTC-timestamp>"
    say "Kernelcache   : $([ "$DO_KERNELCACHE" -eq 1 ] && echo 'inventory + unambiguous copy (sudo, read-only search)' || echo 'skipped')"
    say "Steps         : fetch tools>verify sha256>collect attached>parse DP-IN>[kernelcache]>auto-hints"
}

if [ "$DRY_RUN" -eq 1 ]; then
    say "DRY RUN - no changes, no downloads."
    plan
    exit 0
fi

if [ "$(uname -s)" != "Darwin" ]; then
    say "This helper must run on macOS. Nothing was changed."
    say "(Use --dry-run to print the plan from another OS.)"
    exit 2
fi

plan

command -v shasum >/dev/null 2>&1 || { say "shasum missing; cannot verify downloads. Aborting." >&2; exit 2; }
command -v curl   >/dev/null 2>&1 || { say "curl missing; cannot download tools. Aborting." >&2; exit 2; }

CAPTURE="$HOME/Documents/wd22tb4-capture-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$CAPTURE/tools"
say ""
say "Capture directory: $CAPTURE"

fetch_verify() {
    # fetch_verify <filename> <expected_sha256>
    local name="$1" expect="$2" dest="$CAPTURE/tools/$1"
    printf '  %-28s ' "$name"
    if ! curl -fL --retry 2 --max-time 60 "$BASE/$name" -o "$dest" 2>"$dest.stderr"; then
        say "DOWNLOAD FAILED"
        return 1
    fi
    local got
    got="$(shasum -a 256 "$dest" | cut -d' ' -f1)"
    if [ "$got" != "$expect" ]; then
        say "SHA256 MISMATCH (got ${got:0:12}... want ${expect:0:12}...)"
        return 1
    fi
    say "ok  ${got:0:16}..."
    return 0
}

step "Fetching reviewed tools (pinned ${PIN:0:12})"
fetch_verify collect-macos-dock.sh       "$EXP_COLLECTOR" || { say "Aborting: collector did not verify." >&2; exit 3; }
fetch_verify inspect-dpin-adt.py         "$EXP_PARSER"    || say "  (parser unavailable; will parse later elsewhere)"
fetch_verify MACOS-CUTOVER-CHECKLIST.md  "$EXP_CHECKLIST" || say "  (checklist copy skipped)"

# Preserve the fetch step's own log lines for provenance.
{
    printf 'pin=%s\n' "$PIN"
    printf 'base=%s\n' "$BASE"
} > "$CAPTURE/REVIEW-fetch-provenance.txt" 2>/dev/null || {
    mkdir -p "$CAPTURE/REVIEW"; printf 'pin=%s\nbase=%s\n' "$PIN" "$BASE" > "$CAPTURE/REVIEW/fetch-provenance.txt"
}
if [ ! -f "$CAPTURE/REVIEW/fetch-provenance.txt" ]; then
    mkdir -p "$CAPTURE/REVIEW"
    printf 'pin=%s\nbase=%s\n' "$PIN" "$BASE" > "$CAPTURE/REVIEW/fetch-provenance.txt"
fi

step "Running read-only collector (state: attached)"
bash "$CAPTURE/tools/collect-macos-dock.sh" "$CAPTURE/01-attached" attached || \
    say "Collector reported one or more failed/invalid checks; inspect REVIEW/status.tsv."

step "Parsing DP-IN metadata from the captured IODeviceTree"
if command -v python3 >/dev/null 2>&1 && [ -f "$CAPTURE/tools/inspect-dpin-adt.py" ]; then
    if python3 "$CAPTURE/tools/inspect-dpin-adt.py" \
            --from-ioreg "$CAPTURE/01-attached/PRIVATE/iodevicetree.plist" \
            > "$CAPTURE/01-attached/REVIEW/dpin-metadata.json" 2>"$CAPTURE/01-attached/REVIEW/dpin-metadata.stderr"; then
        say "  wrote REVIEW/dpin-metadata.json"
    else
        say "  parser failed; the original plist is retained for later parsing."
    fi
else
    say "  python3 not available; run inspect-dpin-adt.py elsewhere on the saved plist."
fi

if [ "$DO_KERNELCACHE" -eq 1 ]; then
    step "Kernelcache inventory (Preboot, read-only; may prompt for sudo)"
    inv="$CAPTURE/01-attached/PRIVATE/kernelcache-paths-root.txt"
    if sudo find /System/Volumes/Preboot -type f -name kernelcache > "$inv" 2> "$inv.stderr"; then
        count="$(grep -c . "$inv" 2>/dev/null || echo 0)"
        say "  found $count candidate path(s), saved to kernelcache-paths-root.txt"

        rootvg="$(diskutil info -plist / 2>/dev/null | plutil -extract APFSVolumeGroupUUID raw - 2>/dev/null || true)"
        rootvol="$(diskutil info -plist / 2>/dev/null | plutil -extract VolumeUUID raw - 2>/dev/null || true)"
        say "  root VolumeGroupUUID : ${rootvg:-unknown}"
        say "  root VolumeUUID      : ${rootvol:-unknown}"

        if [ "$count" = "1" ]; then
            kc="$(head -1 "$inv")"
            say "  single candidate -> copying (read-only) with ditto:"
            say "    $kc"
            if sudo /usr/bin/ditto "$kc" "$CAPTURE/01-attached/PRIVATE/kernelcache"; then
                shasum -a 256 "$CAPTURE/01-attached/PRIVATE/kernelcache" \
                    > "$CAPTURE/01-attached/REVIEW/kernelcache-sha256.txt"
                say "  copied; hash in REVIEW/kernelcache-sha256.txt"
            else
                say "  copy failed; the inventory above is still useful."
            fi
        elif [ "$count" = "0" ]; then
            say "  no candidates (Preboot may deny access); inventory retained."
        else
            say "  multiple candidates; NOT copying (never guess the volume)."
            say "  Resolve the active build against the saved apfs-layout.plist before copying."
        fi
    else
        say "  sudo search failed; see kernelcache-paths-root.stderr. Inventory is optional."
    fi
fi

step "Auto-detected observations"
hints="$CAPTURE/01-attached/REVIEW/auto-hints.txt"
{
    printf 'collected_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'model=%s\n' "$(sysctl -n hw.model 2>/dev/null)"
    printf 'macos=%s\n' "$(sw_vers -productVersion 2>/dev/null) build=$(sw_vers -buildVersion 2>/dev/null)"
    say_line() { printf '%s\n' "$*" >> "$hints"; }
    printf '\n-- displays (SPDisplaysDataType, condensed) --\n'
    system_profiler SPDisplaysDataType 2>/dev/null | sed -n '1,60p'
    printf '\n-- dock presence (SPThunderboltDataType grep) --\n'
    system_profiler SPThunderboltDataType 2>/dev/null | grep -iE 'WD22TB4|Dell|Thunderbolt|USB4|Speed|Device Name' | head -20
    printf '\n-- external display + dock usb (SPUSBDataType grep) --\n'
    system_profiler SPUSBDataType 2>/dev/null | grep -iE 'Dell|Realtek|Hub|Display' | head -20
} > "$hints" 2>&1
say "  wrote REVIEW/auto-hints.txt"

step "Done"
say "Capture: $CAPTURE"
say ""
say "Now fill in REVIEW/observations.txt (one line each):"
say "  1. Does the Amazon Basics screen show the macOS desktop through the dock?  (yes/no)"
say "  2. Monitor model (label/OSD), selected HDMI input, observed resolution/refresh."
say "  3. Physical Mac port of the USB4 cable: right side | left-near-hinge | left-near-front."
say "  4. Dock video socket used, and any adapter in the chain."
say "  5. Any standby/wake behaviour; whether the dock shows in System Information."
say ""
say "Then verify REVIEW/status.tsv shows no unexpected FAILED / INVALID_OR_EMPTY."
say "Keep PRIVATE/ local (it contains serials/UUIDs); nothing was uploaded."
say ""
say "Helper provenance: pin=${PIN}"
say "Helper script: $0"
