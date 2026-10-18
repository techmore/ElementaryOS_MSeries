# One controlled DP-IN test

2026-10-16. This supersedes the paused deployment blocker in the earlier handoff.
Apply patches 0001–0011 in order. Current frozen source: private reconstruction
commit `46bb8b63089c0fed0ccdc3bd8b62fc87e99ee88c` (patch 0011 adds the
first-boot R1/R2 fixes on top of `c6fd9068fb69a3d4235a705fef2e0364748ff2b4`);
public patch hashes and final module, DT, initramfs evidence for 0001–0010 are
in
[evidence/2026-10-16-controlled-test-preflight.json](evidence/2026-10-16-controlled-test-preflight.json),
and the fix/re-stage record is
[evidence/2026-10-16-r1-r2-fix-and-restage.md](evidence/2026-10-16-r1-r2-fix-and-restage.md).
No repeated binary/port/dock discovery was needed.

## Current branch entry point

The deployment records below describe older payloads. Use [STATE-OF-PLAY.md](STATE-OF-PLAY.md)
for the latest retained E4 record and [DOCK-CODE-REVIEW.md](DOCK-CODE-REVIEW.md) for software checks.
The existing fallback-preserving installer deliberately rejects E4's wider DT changes; do not bypass
its compatibility check. This audit neither changes installed payloads nor arms another boot.

## Historical deployment status

**Re-staged with the R1/R2 fixes; no boot armed — 2026-10-16.** The first
one-shot entry ran 11:45:04–11:47:13 with the exact intended parameters
(`allow_dp_tunnel=1 dprx_bypass=1 dprx_timeout=15000`) and all five rebuilt
modules loaded. The bridge engaged automatically on the dock tunnel
(`0:5 <-> 1:14`) and failed in the DP-IN path: the first attempt returned
`-67` (`-ENOLINK`) from `phy_power_on` (DP-IN HPD low at activation, ~4 s
after bring-up); the second attempt Oopsed in `dpin_init` (stale PHY after
the ACIO re-probe). A Gala/simpledrm boot race also crashed the desktop, so
the collector was not run. Full record and excerpts:
[evidence/2026-10-16-controlled-test-first-boot-outcome.md](evidence/2026-10-16-controlled-test-first-boot-outcome.md).

Revision `46bb8b6` (patch 0011) fixes both DP-IN failures. The refreshed
payload was installed through the reviewed rollback → stage → verify → plan →
apply sequence: image `486be1d9…`, same append-only `custom.cfg` (`9eadf091…`)
and fallback-safe `boot.bin` (`6702f2c7…`); rollback set
`/home/sdolbec/dptunnel-logs/rollback-46bb8b6` (the c6fd906 set is superseded).
`next_entry` is empty; root modules/original initramfs/kernel/default/grubenv
remain unchanged. Re-arm only when the session race (R4) is addressed or
accepted — its cause is recorded and the `lightdm-wait-for-drm.conf` drop-in
is installed (effective next boot, unverified); the fixed payload is otherwise
ready for one re-run with the collector. Record:
[evidence/2026-10-16-r1-r2-fix-and-restage.md](evidence/2026-10-16-r1-r2-fix-and-restage.md).

> **Current applied payload (2026-10-16 late).** The base image `486be1d9…`
> above has since been superseded twice on the `elementary-usb4-dpin-controlled`
> entry only: first by the `DPINDBG` diagnostic image `a6db46fa…`, now by the
> **E1** image `46116374…` (patch `0013`, only `appledrm.ko` changed) which is
> installed and armed (`next_entry=elementary-usb4-dpin-controlled`). `boot.bin`,
> `custom.cfg`, kernel, default entry and root modules are unchanged. Stage/
> rollback:
> [evidence/2026-10-16-e1-nonfatal-tunnel-hpd-boot.md](evidence/2026-10-16-e1-nonfatal-tunnel-hpd-boot.md).

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
Final staging directory: `controlled-test-46bb8b6` (previous: `controlled-test-c6fd906`).
Boot candidate: `deployment/boot-fallback-safe-c6fd906.bin`.
Install manifest: `controlled-test-46bb8b6/install-manifest.json`.
Rollback directory: `/home/sdolbec/dptunnel-logs/rollback-46bb8b6` (previous set `rollback-c6fd906` is superseded).

The installer checks frozen input/output hashes and the separate compatibility
record. It backs up the original boot payload, custom.cfg and grubenv, writes
the uniquely named initramfs, appends the separate entry, then writes boot.bin
last. It never modifies root modules, the default entry or grubenv and never
reboots. It refuses stale targets and collisions. Scratch tests exercised
apply, exact rollback and refusal after another writer modifies a target.

From that workspace, the current reviewed manifest was applied with (the
installer refuses re-application by design):

```sh
sudo python3 test-staging/apply-controlled-test.py apply \
  --manifest controlled-test-46bb8b6/install-manifest.json \
  --expect-manifest-sha256 fdfe9ab56a58107b46f4293e2d3fd67e810396f1ce8d8bca0ab70e58fb8f10a5
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
  --stage-manifest /home/sdolbec/Documents/Codex/2026-10-16/hey-x20/work/dpin-implementation/controlled-test-46bb8b6/stage-manifest.json \
  --output /home/sdolbec/dptunnel-logs/controlled-46bb8b6-first-boot
```

First require the intended kernel, bypass Y, timeout 15000 and all five loaded
module identities. Save source/PHY errors and external DP/HDMI status, modes,
EDID checks and kernel log. The collector excludes eDP and cannot infer a
picture from bypassed DPRX, tunnel activation or USB enumeration. A bypass-off
DPRX qualification is a later test, not part of this one.

DeepSeek: the R1/R2 fixes, fresh bundle, re-staged initramfs and re-installed
payload are recorded in
[evidence/2026-10-16-r1-r2-fix-and-restage.md](evidence/2026-10-16-r1-r2-fix-and-restage.md).
The five-second source-start deadline remains unchanged; record its
errno/timing if it fires. Hardware results remain pending.
