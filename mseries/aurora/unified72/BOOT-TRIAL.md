# J314S wip2: staged, unarmed experimental trial

## Installed state, October 21, 2026

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
   automatically. The current authorization stops at unarmed staging.
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
