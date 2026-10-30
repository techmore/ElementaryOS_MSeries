# Unified Aurora 7.2.10 build candidate

## Separate eGPU candidate — October 30, 2026

`egpu-series.json` pins Aurora #188 merge `c506e1c3c1d7808eddc251e3029b72e9f17e00df`, whose first parent is the wip5 source, and retains its five local display patches. The `unified72-egpu` profile has a distinct package and modules identity and requests AMDGPU as a module; the existing `unified72` profile remains unchanged. It does not enable Nouveau. Prepare with `python3 mseries/aurora/candidate.py prepare --profile unified72-egpu --cache CACHE --output OUTPUT`, then run `candidate.py check --prepared OUTPUT`. The Aurora workflow offers this profile through manual dispatch.

The pinned archive checksum, all five ordered patch applications and 12 production PMP host tests passed locally. A GCC `olddefconfig` retained `DRM_AMDGPU=m`, `DRM_AMD_DC=y`, `DRM_AMD_DC_FP=y`, and 16K pages; the local LLVM attempt lacked a working lld, so the CI LLVM build is still required. No eGPU is attached here. No build, boot, dock, shared-DTB recovery or hotplug qualification is implied by source preparation. The updated T600x PCI ranges require a matched boot-chain review; do not promote or install this candidate based on these checks.

On 2026-10-30 the live `/proc/device-tree` confirmed the shared boot DTB still has PCI high address `0x8` on tunnels 0–3, with CPU high addresses `0x8`, `0xc`, `0x10`, `0x14` respectively. #188 changes the PCI addresses for tunnels 1–3 to match their CPU addresses. The shared `/boot/m1n1/boot.bin` SHA-256 is `9c9c2d01c3bdb2784daf99cecd6f0e2327eb8f148ea43c8e522e5bae09a14d5f`, matching the documented retained fallback. Therefore the new package's DTBs alone cannot change the currently selected boot tree; updating the shared payload could also change the DTB supplied to older recovery kernels. A per-kernel or fallback-compatible boot path must be designed and verified before an eGPU trial.

The locally compiled candidate `t6000-j314s.dtb` (GCC config check, SHA-256 `7f515974eb466d075e94d435c58543e3c30b1da3bd02d5f6dcf5d067e5747698`) decompiles with only those three range changes compared with the installed wip5 package DTB (`2ca125477252e4753e8168567af99dda592bce6dea94235677d212846f49ae4c`). Separately, `prepare-egpu-boot-candidate.py` constructs a private boot image by changing those exact three bytes in the existing shared J314S tree, rather than substituting the newer packaged tree. It verifies an explicit input hash, unique expected ranges, an unchanged 110-tree structure and byte-identical data outside the target tree; it refuses `/boot` output and overwriting files. Against the current payload it produced `~/.cache/mseries-aurora-egpu-20261030/boot.bin.script-candidate`, SHA-256 `fe7ad1e9fe54591a0e85c7e05ecb063778ffbb0359d9c6d2b57939f398529913`. Decompilation confirms only the three PCI range changes; a separately constructed candidate was byte-identical. This is **uninstalled and unbooted**: it is still a shared payload and does not establish compatibility with wip4, .20 or rescue, nor does it validate hardware eGPU access. The 86 Aurora unit tests include missing and ambiguous range refusals. The native [CI build](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/41048473839) remains the source for the kernel artifact, not this local DTB-only compilation.

## wip5 revision 7 — October 29, 2026 (booted on the J314S; install record in [wip5/README.md](wip5/README.md))

The owner chose this re-pin. **Revision 7 pins `7.2.11-elementary-aurora72-wip5`**: merged omacom
`integration/aurora` at `2f725546` (still 7.2.11). Upstream #158, the wip4 source `bd526b3c`, merged on 2026-10-23
and is an ancestor of it, 388 commits back. The package is `linux-image-elementary-aurora72-wip5`, version
`7.2.11+elementary.aurora72.wip5-1`, so it cannot overwrite the installed wip4.

The five patches stay. **0001 (#157) is rebased on context only.** Its `dcp-internal.h` hunk now sits above the new
`dcp-panel-edid.h` include. Its `plane.c` hunk is regenerated 194 lines lower, because the old file applied there only
with fuzz 2. The added and removed lines are byte-identical to the wip4 file. 0002 (local) and 0003-0005 (#186) are
unchanged and apply with offsets only. `candidate.py prepare --profile unified72` applied all five to the full archive
in order (`git apply --check`, no fuzz) and passed the config gate.

**The `UDMABUF`/`DMABUF_HEAPS` overlay stays.** Upstream turned these on only in the `asahi.config` fragment
(`1b4997bb`). This build configures the `.20` recipe's full config, which has them off, so dropping the overlay
would turn udmabuf off. The enhancements lane (`enh1`, base `.20`) is unchanged for the same reason. Its
`0001-udmabuf` and `0006-egpu` patches stay.

**Not done:** native build (CI), KUnit, any boot. Receipt: [review-wip5-2026-10-29.json](review-wip5-2026-10-29.json).
wip4 revision 5 stays installed and is the running kernel; nothing is staged or armed.

## Upstream resync — October 29, 2026 (read-only)

Receipt: [upstream-resync-2026-10-29.json](upstream-resync-2026-10-29.json); branch snapshot:
[2026-10-29.json](../branch-audits/2026-10-29.json). Covers omacom/aurora-silicon, both m1n1 trees, Gravity and,
for the first time, Joshua Warren's `linux-aurora`, `linux-omarchy-m6` and `m1n1` forks (now in
`local-ai/branch-watch.json`).

- **The laptop runs revision 5, not 6.** The installed wip4 `appledrm.ko` has 0002 but not #186 (0003-0005).
- **#158 merged on 2026-10-23**, so `bd526b3c` is now an ancestor of `integration/aurora` (head `2f725546`, still
  7.2.11, 388 commits ahead). #157 and #186 are open with unchanged heads. aurora-silicon's `integration/aurora`
  moved to Linux 7.3.
- **Absorbed upstream:** the `UDMABUF`/`DMABUF_HEAPS`/`DMABUF_HEAPS_SYSTEM` overlay below (and enhancements
  `0001-udmabuf.patch`) are in the shared `asahi.config` since `1b4997bb` (2026-10-20). None of 0001-0005 is absorbed.
- **At the new head** 0002-0005 apply; 0001 needs a context rebase (one new `#include` in `dcp-internal.h`).
- `series.json` and `patches/` are unchanged: editing them starts the native kernel build. Apply the above at the
  next re-pin.

## wip4 revision 6 — October 27, 2026 (build-only, not booted)

Revision 6 adds the three commits of unmerged upstream [PR #186](https://github.com/omacom/linux-aurora/pull/186)
(`patches/0003`-`0005`, tested upstream head `2a37f6f2`): take over a pipeline held by a port whose sink never asserted
HPD, **route a DP-alt port only once its sink asserts HPD**, and treat `-ENOSPC` as a taken display on every SoC. Commit 2
reports that routing before HPD left the firmware's DPTX service on that DCP answering `-110` until reboot, the same
symptom as `dcpext1` (`28cc00000`) here. It complements local patch 0002 (which recovers after a DCP goes silent).
[#163](https://github.com/omacom/linux-aurora/pull/163) is **not** carried: it fixes the same tipd bug as 0005 by a
different change and conflicts with it.

Why now: across the retained journals (Oct 20-27) the dock produced no DPTX failures on `.20` and wip2, or on a wip3
boot where it was plugged in at boot. All three failing boots (2026-10-22, 10-26, 10-27) were wip3 with the dock
**first plugged within about 4 s of resuming from s2idle**; each landed on `28cc00000`, timed out six times, then worked on
`289c00000` after the port was changed. That pattern is consistent with, not proof of, a post-resume DCP state problem.

Checked: `candidate.py prepare --profile unified72` applied all five patches to the full pinned source (exit 0),
`candidate.py check` passed, 83 aurora tests pass. **Native build:** passed in [CI run 40498010695](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/40498010695) (job *ARM64 unified72 build and payload inspection*, 2026-10-27; the 293 MB / 297 MB artifacts were not downloaded or audited here). **Not done:** KUnit, any boot; the upstream test
report did not hot-plug a dock. 0002 and 0003/0004 both edit `dcp-fabric.c`; they apply in order but their semantic
interaction is unreviewed. Receipt: [review-wip4-2026-10-27.json](review-wip4-2026-10-27.json). wip3 stays installed;
nothing is staged or armed.

## wip4 candidate — October 22, 2026 (build-only, not booted)

**Revision 5 pins `7.2.11-elementary-aurora72-wip4`:** the same #158 source and #157 patch as wip3, plus one local
patch, `patches/0002-drm-apple-free-dp-tunnel-route-from-silent-dcpext.patch`. It answers the first wip3 dock plug of
a boot (2026-10-22), where `dcpext1` (`28cc00000`) never answered the DisplayPort validate call and its port stayed
pinned to it until reboot. A DCP whose DPTX call times out is passed over for 300 s, and a timed-out release is
completed instead of kept owned. Evidence, the reasoning, and what it does **not** fix (a tunnel already attached to
the silent pipeline is not moved within that plug):
[2026-10-22-j314s-wip3-dcpext1-dptx-wedge.md](../hardware-tests/2026-10-22-j314s-wip3-dcpext1-dptx-wedge.md).
Receipt: [review-wip4-2026-10-22.json](review-wip4-2026-10-22.json). Checked: patch applies on the exact pinned
files; the routing change ran in userspace against the real `dcp-fabric-core.c`. **Not done:** kernel build, KUnit,
any boot. wip3 stays installed and is the running trial kernel; nothing is staged or armed for wip4.

## wip3 candidate — October 21, 2026 (build-only, not booted)

**Revision 4 pins `7.2.11-elementary-aurora72-wip3`:** unmerged upstream
[PR #158](https://github.com/omacom/linux-aurora/pull/158) (Asahi 7.2.11 rebase, head
`bd526b3c11cc`) plus unmerged [PR #157](https://github.com/omacom/linux-aurora/pull/157)
(DCP sRGB surfaces and link colorimetry for external displays) carried as one local patch,
`patches/0001-drm-apple-srgb-external-display-colour.patch`. The owner chose both. This replaces the
wip2 pin in `series.json`; the wip2 package, GRUB trial entry, receipts and hardware reports below stay as
history and the installed wip2 is unchanged. Package `linux-image-elementary-aurora72-wip3`, version
`7.2.11+elementary.aurora72.wip3-1`, so it cannot overwrite wip2 modules.

Checked here: the #157 diff dry-runs cleanly on the five files at #158 head (offsets only) and on current
`integration/aurora`; `candidate.py prepare` applies it to the full source tree without fuzz and the
config gate passes; `candidate.py check` and its pmp host tests pass; the aurora unit tests (72) pass.
Receipt: [review-wip3-2026-10-21.json](review-wip3-2026-10-21.json) (archive SHA256 recorded on first
download). **Native build:** passed in [CI run 39645763520](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39645763520); the artifact was audited (GitHub digest matched, `SHA256SUMS` verified, package `7.2.11+elementary.aurora72.wip3-1`, 1,876 modules, 115 DTBs, patch files present in `modified_files`) and saved as [native-build-wip3-2026-10-21.json](native-build-wip3-2026-10-21.json); the artifact itself expires in seven days. **Not established:** 64-fix parity at 7.2.11 (the old comparison is for 7.2.10),
Touch ID/dock/power/recovery on the J314S. #158 is an open proposal and #157 an open PR; re-pin if either
moves. `prepare-j314s-trial.py` now takes its identity and receipt from `series.json`/the receipt name, but no
wip3 boot payload has been prepared or staged. Nothing is installed or armed.

## Current host state — October 21, 2026

**Wip2 has booted and all three USB-C ports show a dock picture.** Later
rear-left recovery supersedes the initial blank-screen report. Real M1 Pro
shader/readback, 1 MiB fsync, boot/PMP/idle and internal input pass within their
recorded scope. External 1080p/60 on each port. One-shot consumed; `.20` remains
persistent default. No stable promotion, suspend/recovery or energy claim.

[All-port follow-up and pilot timings](../hardware-tests/2026-10-21-j314s-wip2-first-boot/PORT-TIMINGS.md):
about 4.5 s partner-detection→active desktop per port, one cycle each with 0.5 s polling;
label/boundary corrections disclosed, not physical insertion→visible-pixel latency.
[First-boot history](../hardware-tests/2026-10-21-j314s-wip2-first-boot/REPORT.md),
[upstream review](UPSTREAM-CANDIDATES.md). Both repeat native CI matrix jobs pass;
kernel build inputs unchanged since tested b213999. No automatic re-arm.

## Merged source refresh — October 21, 2026

The owner selected a refresh of this independent Aurora 7.2 candidate. Revision 3
pins merged [upstream PR #139](https://github.com/omacom/linux-aurora/pull/139) at
`644133b7799f759c5bfd88507b6246d298b6509c`. This deliberately selects the merged
7.2.10 source, rather than unmerged PR #158's 7.2.11 proposal or a moving branch.
`series.json` records the complete archive SHA256, source/config and new package
identity. [Source review receipt](review-2026-10-21.json) records the streamed
270,217,427-byte archive check, immutable file digests and validation limits.

New identity: **`7.2.10-elementary-aurora72-wip2`**, package
`linux-image-elementary-aurora72-wip2`, version
`7.2.10+elementary.aurora72.wip2-1`. It has its own module directory and namespaced
phram configuration, allowing the existing `.20`, `.20-enh1` and `wip1` payloads
to remain separate. The fixed `.20` installer/stager does not deploy this lane.
No boot entry, shared payload or running kernel is changed by building it.

The old wip1 stock-bindgen patch is **not applied** to wip2: the merged source
already contains the stock `--no-layout-tests` default and opt-in
`BINDGEN_LAYOUT_TESTS=1` policy. Its patch file and metadata remain as historical
provenance under `superseded_patches`; do not apply it twice.

Focused source review confirms that the three shared gaps reported against the
old snapshot are addressed in the inspected merged files: render/compute use
`read_supported`, SEP's OF table is not exported for autoload, and SEP capture
stop timeout continues suspend. Five original GPU-reader host tests and the nine
PMP argument-parser plus three PMP reply-correlation tests pass at this source.
These are bounded host controls, not a GPU/kernel boot or complete 64-fix audit.
The previous GPU util file had seven tests; the merged file has five, so no
identical test-count/coverage claim is made. The two omitted cases test
`read_up_to` stride consumption and zero extension; that implementation differs
from `.20` only in a local variable name and formatting.

The [refreshed 64-patch comparison](review-patch-applicability-2026-10-21.json)
checks the affected immutable files at the new source: zero patches apply
forward, 40 reverse-apply, and 24 apply in neither direction. These independent
checks locate follow-up work; they do not qualify 40 fixes or prove that the
other 24 are absent. No patch was adopted from these checks. Selected source
inspection also finds the `user4k=on` opt-in, privileged-exec page-size reset and
perf AUX speculation bound retained. Their runtime tests were not run here.

The Asahi UAPI header differs from `.20` in two comments, with declarations
unchanged after comment/whitespace removal. Installed Mesa packages were
`26.0.8-1ubuntu0.3` at observation. Header similarity does not qualify driver
behavior or actual clients on 7.2; that compatibility gate remains open.

Native source/config/Image/modules/DTBs/package build, inspection and artifact
upload passed in [run 39595756051](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39595756051)
at repository commit `b21399953faa576b17f3121087742fb597c872a5`. The unchanged
`.20` control build passed too. [Independent artifact audit](native-build-2026-10-21.json)
verified GitHub's ZIP digest, every `SHA256SUMS` entry, the full archived prepared
source-tree digest, package boundaries and the J314S DTB. Full corresponding
source, resolved config, toolchain provenance and LICENSES are included. Actions
retention is seven days; the saved receipt includes its expiry and exact digests.

The old recipe seed emits one `NETFILTER_NETLINK=m` warning; `olddefconfig`
resolves it to `y`, with `NF_TABLES=m` and `NFT_COMPAT=m` retained. This is not a
warning-free build claim. Subsequent review/test/documentation changes preserve
the recorded builder/manifest/workflow hashes; artifact-embedded documentation
remains the snapshot at the tested commit. Earlier wip1 receipts are separate.
That build checkpoint preceded the scoped first boot recorded above; no power
saving or complete hardware acceptance is claimed.

## Static contract follow-up — October 21, 2026

[Manual mismatch triage](static-contract-review-2026-10-21.json) examines all 24
mechanically-neither cases against immutable source. Nineteen retain the
described source contract, including the moved `mm/userfaultfd.c` check,
USB-C debug-command gate, read-only AWDL parameter, AFK/VFIO test dependencies,
13.5 DPTX reply handling and SEP store/autoload/suspend safeguards. This is
bounded static inspection; no new hardware tests or patch adoption occurred.

Five cases remain open or partial: io_uring accounting replacement, MGLRU
reclaim replacement, document relocation/removal, complete Type-C relink
concurrency/lifecycle and full T8140 QSPI policy equivalence. The 40 reverse
applicability results remain mechanical evidence; full 64-fix semantic parity
is still open. No newly established J314S trial blocker was identified within
this bounded inspection. Boot/Mesa/dock/recovery acceptance remains pending.

The [manual post-boot sequence](BOOT-TRIAL.md#manual-collection-after-the-attended-wip2-boot)
now includes exact private snapshot/hash/current-boot collection commands and
separate reviewed smoke invocation. It preserves the normal desktop session
bus and unknown display/power fields. It refuses the old running release.

## Reproduce in an isolated builder

```sh
python3 mseries/aurora/candidate.py prepare --profile unified72 \
  --cache /absolute/work/cache --output /absolute/work/unified72
python3 mseries/aurora/candidate.py check --prepared /absolute/work/unified72
python3 mseries/aurora/candidate.py build --prepared /absolute/work/unified72 \
  --output /absolute/work/unified72-artifacts --jobs 4
```

The builder uses the checksum-pinned `.20` **full recipe config** as its seed,
resolves it with the pinned 7.2 source and enforces Apple/Rust/16K/USB4/memory
requirements. It is not the contributor's Fedora config. eGPU drivers remain
disabled in this profile. The separate `.20` M3 camera/thermal/SMC series is not
silently layered onto this source. Preparation, build and package inspection
fail on pin/config/identity errors; none installs a package.

## Hardware and compatibility gates

This is an **experimental, booted trial with incomplete qualification**. The [October 18 parity inventory](../branch-audits/2026-10-18-review-parity.json)
records the old `582e9ef3` snapshot; retain it as history. The new focused review
supersedes only its three inspected GPU/SEP gap descriptions, not all 64 semantic
review requirements. Check the intended Mesa/kernel UAPI and actual client
compatibility before hardware promotion.

Upstream's merged PR reports M1-family Touch ID first-attempt reliability
regressions and an unexplained M1 Pro early hang. Contributor J316S/M1 Pro,
J413/M2 or J700 results do not qualify this J314S or our resolved config.
Never disable xART protections or re-provision identities as part of a routine
kernel update.

The installed `boot.bin` shares one DTB set across GRUB entries. Upstream notes
that older 7.1 fallback kernels need a compatible five-cell DART backport to use
the newer DTBs. This trial retains the byte-exact old shared DTB set; the new parser accepts
its legacy one-cell geometry in the host controls. Retaining an old kernel entry
alone does not prove recovery.
Review exact DT/m1n1/U-Boot, initramfs/root-unlock and accessible byte-exact
rollback together. Display/GPU/storage/radio/input/thermal/suspend and recovery
acceptance remain separate from compilation and source review.

## Historical wip1 evidence

The prior revision pinned draft PR #139 at `582e9ef3d44c93082e8abc740ad3e0a8dde29752`
as `7.2.10-elementary-aurora72-wip1`. Its stock-bindgen policy port and native
build/package inspection passed in [run 39114197052](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39114197052).
Those frozen source/build receipts remain unchanged and are not wip2 results.
