# J314S wip2: first boot recorded, qualification incomplete

## Actual first-boot state, October 21, 2026

Wip2 booted and matched its audited Image/live build ID. Scoped five-minute
boot/PMP/idle, M1 Pro shader/readback and 1 MiB fsync passed. Owner confirms internal
screen/input and front-left dock picture; hinge-side left port fails. External
1080p/60 observed. [Retained report and receipts](../hardware-tests/2026-10-21-j314s-wip2-first-boot/REPORT.md).
Reuse completed checks for this boot; do not repeat them as new evidence.

One-shot consumed (`next_entry` empty), persistent default `.20`, fallback files
unchanged. No automatic re-arm. Matched per-port acceptance and actual return-to-
`.20` recovery remain next, before suspend/power work. The earlier instructions
below describe preparation/arming history and how to collect a distinct future
boot; they are not instructions to re-run this completed capture.

## Earlier one-shot state, October 21, 2026

Owner authorized arming after repeat CI passed. Both matrix jobs in run
39601423970 passed; all staged/fallback hashes, package verification, GRUB syntax
and environment storage checks passed again. At 13:23:18 UTC (09:23:18 EDT),
`grub-reboot --boot-directory=/boot elementary-aurora72-wip2-trial` set and verified
that exact `next_entry`. `.20` remains persistent default; no reboot occurred.
[Arming receipt](one-shot-armed-2026-10-21.json) supersedes the earlier unarmed
status below. This authorization covers the armed one-shot; the owner controls
the attended reboot. Do not automatically re-arm after the trial.

To cancel before reboot, first verify the one-shot still equals this trial,
then use `sudo grub-editenv /boot/grub/grubenv set next_entry=` and verify it is
empty; preserve another owner's changed selection. Record cancellation separately.

## Earlier installed state, October 21, 2026

Owner approved **unarmed staging**. Installed separate package
`linux-image-elementary-aurora72-wip2` version `7.2.10+elementary.aurora72.wip2-1`,
`/boot/vmlinuz-aurora72-wip2`,
`/boot/initrd.img-7.2.10-elementary-aurora72-wip2` and non-default GRUB entry
`elementary-aurora72-wip2-trial`. No one-shot was set and no reboot occurred.
STABLE `elementary-aurora20` remains persistent default; running `.20-enh1`
is unchanged. Generated `grub.cfg` was not regenerated.

[Staging receipt](boot-preflight-2026-10-21/staging.json) records exact before/after
hashes and the root-private byte-exact backups in
`/var/lib/mseries-kernel-tests/staging/20261021T131440Z-aurora72-wip2`.
The original complete CI ZIP, package/source/provenance and private prepared
bundle remain in the owner's October 21 Codex workspace `outputs/`.
[Build receipt](native-build-2026-10-21.json) binds the actual installed package
to successful native CI at `b213999`; later documentation/host controls do not
change builder/manifest inputs or substitute the repeat CI's artifacts.

The host has `path-exclude=/usr/share/doc/*`. Initial install omitted licenses
and provenance, detected before any boot-file change. Scoped reinstall used:

```sh
sudo dpkg --path-include='/usr/share/doc/linux-image-elementary-aurora72-wip2/*' \
  --install /absolute/path/to/the/audited/wip2.deb
```

This flag may be needed on a future reinstall on this host. No global dpkg
policy was changed. All 2,042 regular payload files and symlinks matched the
audited extracted package afterward; `dpkg -V` and `dpkg --audit` were clean.

## Compatibility boundary

The shared `boot.bin` is byte-identical to the working baseline. It retains the
old J314S DTB (`a29ff688...`); the package's new J314S DTB (`2ca12547...`) is an
on-disk asset, **not selected for this boot**. Keeping the old one-cell DART
format avoids forcing the old `.20` fallback to parse new five-cell specifiers.
The unmodified new parser passed 50 host controls using this DT's geometry,
covering 37 providers / 36 explicit client specifiers. Hardware parameter
register probing is not emulated. This is not complete DT or recovery proof.

The original Arch mkinitcpio encrypt/userspace/keymap/firmware entries and early
archive remain identical. Only module selectors/dependencies changed. The two
absent fcrypt/pcbc modules are outside observed AES-XTS LUKS2 root requirements;
AES/XTS/SHA256 are built in. RAID6 moved paths and is included through the new
Btrfs closure. All 91 embedded module bytes match the pinned original package.
`prepare-j314s-trial.py` reproduces offline preparation and refuses unexpected
identities/transitions; it does not install or arm anything. Its output must be
private. `check-legacy-dtb.py` runs the bounded parser controls against verified
source and the pinned retained DTB. All 71 repository tests pass.

[Preflight receipt](boot-preflight-2026-10-21.json) and its adjacent evidence
retain the exact Mesa/UAPI and firmware checks and host controls. The live
compositor uses Mesa 26.0.8; Asahi UAPI declarations are unchanged. GPU/internal
and external DCP firmware compat 13.5.0 is explicitly supported in the merged
source. Actual clients on the new kernel remain untested.

DART firmware (63), Bluetooth (46), tunnel-route and DCP host controls passed.
The original DART range fixture is stale and failed compilation; retained patch
ports only its host stubs/expectations, with 12 passing controls and unchanged
production source. The initial DCP suite passed 55/56 groups; its USB Kconfig
producer passed all four cases when rerun with an absolute output path.
Do not report a single 56/56 invocation or hide the initial failure. Host mocks
retain command17 replay counterexamples; they do not prove firmware timing or
replay exclusion. Full 64-fix semantic parity remains open.

## Later attended boot, after owner/Claude coordination

1. Recheck installed package/Image/initramfs and protected fallback hashes
   against the staging receipt; confirm `.20` default and empty `next_entry`.
   Preserve another owner's armed trial if anything has changed.
2. With an owner present and explicit go-ahead, select
   **TRIAL: Aurora 7.2 wip2** once at GRUB. A separately authorized one-shot may
   be used; do not change the persistent default. No service should arm this
   automatically. Owner has since authorized and completed this one-shot arming; do not repeat it automatically.
3. Use the password for root unlock/login initially. Do not re-enroll Touch ID,
   disable xART, or add optional sleep/user4k parameters. Upstream records M1
   first-attempt Touch ID regression and an unexplained M1 Pro early hang.
4. If it hangs, record the visible last message. If unresponsive, power off and
   select **STABLE: Aurora .20** at the next GRUB menu. The menu has a five-second
   timeout. The rollback payloads exist; recovery has not yet been demonstrated
   after a new-kernel boot. Do not rewrite `boot.bin` to attempt a repair.
5. After a successful boot, verify exact `uname -r`, live build ID against the
   new Image, module vermagic/hashes, unchanged shared payload, selected legacy
   DART bindings and firmware compatibility. Confirm internal/dock picture and
   input and examine current-boot logs for panic/oops/lockup before more tests.
6. Collect current-boot kernel logs privately and invoke `qualification.py
   collect` with explicit new Image and shared `boot.bin`, then
   `hardware/kernel-smoke.py` with that matching receipt. Its GPU shader/pixel
   readback and 1 MiB fsync must actually run on wip2; old-kernel results do not
   qualify wip2. Keep any missing power/display fields unknown. Do not publish
   raw UUIDs, kernel logs or unlock archives.
7. Record the scoped results, then perform an attended return to default `.20`
   and bind a separate receipt to that boot. Only after basic acceptance and
   actual fallback recovery proceed to suspend, dock replug and paired power
   tests. Staging, CI or a single desktop boot is not stable promotion.

The automatic session timer currently expects a compositor `PowerSaveMode`
property that this Rust compositor does not expose. Use explicit manual
collection for this first trial. Qualification's packaged DTB hash describes
an asset under the module tree; record the retained selected boot DTB separately.

## Reversing staging

Leave the separate package installed while investigating a failed trial; it
cannot change the running kernel by itself. To remove the menu/files later,
first compare live files to this staging receipt and ensure no other agent has
updated or selected them. Restore only the backed-up `custom.cfg` if it still
matches this staged hash, and remove only the new wip2 Image/initramfs after
confirming their hashes. Do not restore or overwrite the shared payload, old
kernel files or generated GRUB as part of routine unstage. Do not remove the
wip2 modules while running wip2. Record any rollback separately.

## Manual collection after the attended wip2 boot

Run from the normal logged-in desktop terminal after confirming picture/input.
Allow at least five minutes uptime for the collector's scoped boot check. Stop
and inspect any panic/oops/lockup or unusable display before the smoke test.
These commands refuse the wrong running release. They do not arm, reboot,
suspend, reconfigure a connector or load a module.

The boot files are root-readable. Copy only the Image and shared `boot.bin`
into a fresh mode0700 evidence directory, verify their pinned hashes, and run
collectors as the desktop user. This preserves the session bus for display
queries. Do not copy or publish an unlock initramfs. Raw journal files stay
private. The example uses this trial's retained checkout; use its exact audited
copy after reboot rather than an unrelated branch.

```sh
(
  set -eu
  test "$(uname -r)" = '7.2.10-elementary-aurora72-wip2'
  MSeriesRepo=/home/sdolbec/Documents/Codex/2026-10-21/we-x20/work/mseries-handoff
  trial_dir=$(mktemp -d /home/sdolbec/Documents/Codex/2026-10-21/we-x20/outputs/aurora72-boot.XXXXXX)
  chmod 700 "$trial_dir"
  sudo -v
  sudo cat /boot/vmlinuz-aurora72-wip2 > "$trial_dir/Image"
  sudo cat /boot/m1n1/boot.bin > "$trial_dir/boot.bin"
  cd "$trial_dir"
  sha256sum --check <<'HASHES'
894c420112c94a07bf70f38d1fad95dfd63fb1085550675d3e0e5f2af4123954  Image
9c9c2d01c3bdb2784daf99cecd6f0e2327eb8f148ea43c8e522e5bae09a14d5f  boot.bin
HASHES
  sudo journalctl -b -k -o json --no-pager > kernel-journal.jsonl
  python3 "$MSeriesRepo/mseries/aurora/qualification.py" collect \
    --output hardware.json --kernel-image Image --boot-image boot.bin \
    --kernel-log kernel-journal.jsonl --duration 30 --interval 1
  printf 'Private evidence directory: %s\n' "$trial_dir"
)
```

Review `hardware.json` first. Require the live build ID match, current-boot log
identity and no failed health checks. Confirm the actual running module hashes,
selected legacy DART cells/firmware and visual acceptance separately. Missing
`PowerSaveMode` still makes display context unavailable: keep it unknown and
`controls_unchanged=false`; a successful command is not complete acceptance.

Only after that review, set `trial_dir` to the directory printed above and run
from the same normal desktop session:

```sh
MSeriesRepo=/home/sdolbec/Documents/Codex/2026-10-21/we-x20/work/mseries-handoff
python3 "$MSeriesRepo/mseries/hardware/kernel-smoke.py" \
  --receipt "$trial_dir/hardware.json" --work "$trial_dir" \
  --output "$trial_dir/smoke.json" --kernel-image "$trial_dir/Image" \
  --boot-image "$trial_dir/boot.bin"
```

The smoke receipt checks current boot identity and installed module hashes.
Its packaged new DTB hash is an on-disk asset; it does not replace the selected
legacy boot-DTB evidence. Even if its before/after unknown display dictionaries
compare equal, that is not measured display/power stability. No smoke result
substitutes for actual dock picture/input or the later attended `.20` recovery.

Pre-reboot readiness checked October21: `cc`, EGL1.5/GLES3.2 development metadata
and Python GI imports are available. No GPU or filesystem smoke was run on the
old kernel as part of this readiness check. Do not run this sequence until wip2
is actually running.
