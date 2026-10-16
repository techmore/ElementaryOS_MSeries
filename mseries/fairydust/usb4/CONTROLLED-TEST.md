# One controlled DP-IN test

2026-10-16. This supersedes the paused deployment blocker in the earlier handoff.
Apply patches 0001–0010 in order. Frozen source: private reconstruction commit
`c6fd9068fb69a3d4235a705fef2e0364748ff2b4`; public patch hashes and final module,
DT, initramfs evidence are in
[evidence/2026-10-16-controlled-test-preflight.json](evidence/2026-10-16-controlled-test-preflight.json).
No repeated binary/port/dock discovery was needed.

## Current deployment status

**Staged and verified.** New initramfs, appended GRUB entry and fallback-safe
boot.bin are installed. Installed hashes/backups and GRUB syntax pass. Root
modules/original initramfs/kernel/default remain unchanged. No reboot is armed
or performed; next_entry is empty. Do not re-run apply: its collision checks
will refuse the existing installation. The commands below retain the reproducible
plan and rollback instructions. Next is the one-shot boot and collector.

## Fallback compatibility

Patch 0010 leaves DCP's original `phys` and every existing PHY supplier
reference unchanged. Only the new Apple DRM driver consumes the new
`apple,dp-tunnel-phy` phandle. Its managed getter validates the enabled T6000
provider and pins the module/device/link, deferring until probe succeeds.
Older kernels ignore the vendor phandle: their fixed fw_devlink property
parser does not turn it into a new DCP dependency. Independent source review
and 11 production lookup fault/refcount groups pass. This is static
compatibility evidence; a fallback hardware boot has not been performed.

The candidate global boot payload adds only two DP-IN nodes and three vendor
properties (paired NHI mapping plus DCP's new lookup). The payload checker
normalizes phandles and rejects any existing PHY dependency change, preserving
all other embedded DTs and prefix/suffix bytes. Do not use the old boot-dpin.bin
candidate from the paused checkpoint, which replaced DCP phys.

The existing root module tree, original initramfs, kernel image, default GRUB
entry and existing custom entries remain untouched. The new image alone
contains the five rebuilt modules and its own regenerated dependency metadata.
Actual archive inspection proves `/init` sources `/config` and loads them
before udev coldplug. The unique entry uses exactly:

```
thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=15000
```

The dependency resolver's displayed one-hour timeout belongs to the current
host /proc/cmdline, not the archived test configuration. Actual parameters and
loaded module build IDs must still be checked after boot. No module reload,
provider unbind or cable moves are part of this first test.

## Prepared local files and deployment

Workspace:
`/home/sdolbec/Documents/Codex/2026-10-16/hey-x20/work/dpin-implementation`.
Final staging directory: `controlled-test-c6fd906`.
Boot candidate: `deployment/boot-fallback-safe-c6fd906.bin`.
Install manifest: `controlled-test-c6fd906/install-manifest.json`.
Rollback directory: `/home/sdolbec/dptunnel-logs/rollback-c6fd906`.

The installer checks frozen input/output hashes and the separate compatibility
record. It backs up the original boot payload, custom.cfg and grubenv, writes
the uniquely named initramfs, appends the separate entry, then writes boot.bin
last. It never modifies root modules, the default entry or grubenv and never
reboots. It refuses stale targets and collisions. Scratch tests exercised
apply, exact rollback and refusal after another writer modifies a target.

From that workspace, the reviewed manifest can be applied with:

```sh
sudo python3 test-staging/apply-controlled-test.py apply \
  --manifest controlled-test-c6fd906/install-manifest.json \
  --expect-manifest-sha256 e163c4fdaab41905aafa56fb2ce22f033d351aec878652c66e1af5edfab13a7f
```

Check deployment status at the top of OS9-HANDOFF before running it. The same
command with `rollback` restores the verified originals and removes the test
image. If a one-shot entry was separately armed, clear `next_entry` with
`sudo grub-editenv /boot/grub/grubenv unset next_entry` before rollback/reboot.
A changed file makes rollback stop for inspection instead of overwriting it.

## One-shot boot and collection

After installation and final hash checks, arm just this entry:

```sh
sudo grub-reboot elementary-usb4-dpin-controlled
sudo grub-editenv /boot/grub/grubenv list
```

Require `next_entry=elementary-usb4-dpin-controlled`. Then one reboot; keep the
cables in place. GRUB consumes next_entry and retains the existing default for
subsequent boots. No reboot is performed by any preparation script.

After login, collect without touching drivers or cables:

```sh
sudo python3 /home/sdolbec/wt-dockvideo/mseries/fairydust/usb4/tools/collect-controlled-test.py \
  --stage-manifest /home/sdolbec/Documents/Codex/2026-10-16/hey-x20/work/dpin-implementation/controlled-test-c6fd906/stage-manifest.json \
  --output /home/sdolbec/dptunnel-logs/controlled-c6fd906-first-boot
```

First require the intended kernel, bypass Y, timeout 15000 and all five loaded
module identities. Save source/PHY errors and external DP/HDMI status, modes,
EDID checks and kernel log. The collector excludes eDP and cannot infer a
picture from bypassed DPRX, tunnel activation or USB enumeration. A bypass-off
DPRX qualification is a later test, not part of this one.

DeepSeek: fallback source fix, fresh bundle, real initramfs and guarded installer
are now prepared. The five-second source-start deadline remains unchanged;
record its errno/timing if it fires. Hardware results remain pending.
