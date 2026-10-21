# Unified Aurora 7.2.10 build candidate

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
identical test-count/coverage claim is made.

Native source/config/Image/modules/DTBs/package inspection for this revision is
pending the existing Aurora enhancement CI. Earlier wip1 build receipts do not
qualify wip2. Full source/config/toolchain provenance and LICENSES travel with
its generated artifacts. No local 7.2 boot, power saving or hardware acceptance
is claimed.

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

This remains **build-only**. The [October 18 parity inventory](../branch-audits/2026-10-18-review-parity.json)
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
the newer DTBs. Retaining an old kernel entry alone does not prove recovery.
Review exact DT/m1n1/U-Boot, initramfs/root-unlock and accessible byte-exact
rollback together. Display/GPU/storage/radio/input/thermal/suspend and recovery
acceptance remain separate from compilation and source review.

## Historical wip1 evidence

The prior revision pinned draft PR #139 at `582e9ef3d44c93082e8abc740ad3e0a8dde29752`
as `7.2.10-elementary-aurora72-wip1`. Its stock-bindgen policy port and native
build/package inspection passed in [run 39114197052](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39114197052).
Those frozen source/build receipts remain unchanged and are not wip2 results.
