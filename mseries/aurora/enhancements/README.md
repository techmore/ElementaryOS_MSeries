# Aurora enhancements for ElementaryOS MSeries

This is a separate source-build candidate based on the checksum-pinned `.20`
release, not a replacement binary for the existing `elementary-aurora20` entry.
The owner requested all useful enhancements identified by the
[51-branch / 11-PR audit](../UPSTREAM-BRANCH-AUDIT-2026-10-17.md).
Source integration, a successful build and a successful hardware boot are
different milestones. No measured power saving is claimed.

## Imported work

| Enhancement | Public source | Integration |
|---|---|---|
| udmabuf and system dma-buf heap | [PR #67, first commit](https://github.com/omacom/linux-aurora/commit/6984b8c07e84b0cf528243db1838dade971ff513) | Candidate config; applied to both the source fragment and the actual full build config. Requires 16K alignment, suitable permissions and application support; no local-AI performance claim. |
| M3 Air thermal fallback at state 2 | [PR #135](https://github.com/omacom/linux-aurora/pull/135) | Original patch; preserves the fallback when an experimental ceiling is raised. Does not raise clocks or change the M1 Pro policy. |
| J613 camera, firmware compatibility 14.7 | [PR #134](https://github.com/omacom/linux-aurora/pull/134) | Original two-commit patch: corrected T8122 PMU address and board/firmware-scoped filter workaround. |
| T8122 camera, firmware compatibility 26.6.2 | [PR #119](https://github.com/omacom/linux-aurora/pull/119) | Original two-commit patch, after #134. Requires a matching m1n1 ISP-heap fix and device firmware; this kernel build alone does not supply those prerequisites. |
| Readable optional SMC battery properties | [LiamRay11's branch commit](https://github.com/omacom/linux-aurora/commit/4676c48ecf1b1acaba7c442d33fe9aae0f037e77) | Rebased over `.20`'s four key-existence guards. Checks metadata, size and a complete read for all 16 optional properties, preserving newer charging and critical-battery handling. Battery reporting hardening, not a battery-life optimization. |
| AMD/Nouveau eGPU modules | [PR #67, second commit](https://github.com/omacom/linux-aurora/commit/d10d360a96f406f3b953eceb6e44e7be3f4c7c24) | Available only with `--profile egpu`; disabled in the normal candidate. No card, display-output, BAR compatibility or compute qualification. |

Original author headers remain in each patch. `series.json` pins source heads,
patch hashes, application order and the full-config settings. Updating the
release source without rebasing the series fails admission explicitly.

## Work still excluded

The 41 ancestor tips and semantic duplicates (VRR, newer Neo touchpad handling,
SEP and historical Thunderbolt display work) already have coverage in `.20`.
Omarchy-only package pinning, release tooling and an older roadmap do not add
elementary kernel behavior. We retain `.20`'s tested compute-preemption scope.

[PR #122](https://github.com/omacom/linux-aurora/pull/122) HDMI-hold fixes and
[PR #127](https://github.com/omacom/linux-aurora/pull/127) J613 clamshell support
conflict with the current display code. They require a source rebase, matched
DT/m1n1 prerequisites and display regression tests before import. The old
131-commit Neo telemetry trial also needs a selective port; only the independently
scoped optional-battery-property fix is included here. The draft J456 iMac
speaker work remains excluded pending amplifier protection/routing qualification.
These are outstanding enhancements, not features claimed as merged by this batch.

## Prepare and test without installing

From the repository root, use new private output directories:

```bash
python3 mseries/aurora/candidate.py prepare \
  --cache /absolute/work/aurora-cache --output /absolute/work/aurora-enh1
python3 mseries/aurora/candidate.py check --prepared /absolute/work/aurora-enh1
```

Preparation verifies the original source and full recipe hashes, applies the
ordered patches without fuzz, gives the candidate its own kernel release and
records modified-file hashes. Existing output directories are refused.
The check runs the upstream production Rust suite (58 cases) and the production
SMC discovery helper with all-readable plus 65 failure cases under ASan/UBSan.

The [ARM64 source-build workflow](https://github.com/techmore/ElementaryOS_MSeries/actions/workflows/aurora-enhancements.yml)
builds both profiles on PRs. A manual dispatch can select one profile. Native ARM64
Linux builds use Clang/LLVM 22, Rust 1.93.1 with rust-src, bindgen, the Linux
kernel build dependencies, zstd, dtc, kmod and rsync:

```bash
export PATH=/usr/lib/llvm-22/bin:$PATH
export LIBCLANG_PATH=/usr/lib/llvm-22/lib
python3 mseries/aurora/candidate.py build --prepared /absolute/work/aurora-enh1 \
  --output /absolute/work/aurora-enh1-artifacts --jobs 4
```

The full config is resolved with `olddefconfig`, then checked for Rust, Apple
display/SEP/USB4, 16K pages and requested memory/eGPU settings before compilation.
The candidate release is `7.1.12-elementary-aurora20-enh1` (or `-egpu`). Its
module directory, Debian package name and modprobe filename are separate from
`.20` and the other candidate profile, so their file ownership does not collide. Artifacts
include a payload-only `.deb` using zstd level 3 with bounded parallel compression,
complete patched corresponding source, resolved
config, patch series, licenses, tool versions and checksum/provenance receipts.
There are no maintainer scripts or `/boot` files. The build does not install.

**Do not use the fixed-release `.20` installer or boot stager for this candidate.**
They intentionally consume the original release pins. Candidate initramfs,
matching DT/m1n1, shared boot.bin fallback compatibility and a dedicated boot
entry still require review on the installed Linux machine. Start with the saved
[read-only preflight](../../REBOOT-QUEUE.md). No default/one-shot boot selection,
bootloader write, live audio change or reboot is part of this integration.

## Keep upstream tracking independent of package format

Elementary's Ubuntu/Debian base continues to consume native `.deb` packages;
Aurora's source revisions and patches can be tracked without adopting pacman.
The AUR contains Arch build recipes, not an OS-independent binary format.
Translate dependencies, initramfs and boot lifecycle according to
[PORT-MAP.md](../../PORT-MAP.md), while retaining upstream hashes and authors.

On the installed machine, measure download, unpack, maintainer-script and
initramfs time separately before changing installation behavior. Parallel
builds, native zstd-compressed `.deb` files and prebuilt CI packages can help;
concurrent dpkg writers are not a
safe installation strategy. The factory project's existing mkosi/sysupdate
path is the candidate for future image-based updates with rollback; the
currently installed machine has not been migrated to it.

The [dpkg-deb options](https://manpages.debian.org/unstable/dpkg/dpkg-deb.1.en.html)
document zstd support and `--threads-max` for supported compressors. These speed
the build/compression stage; they do not parallelize package-install transactions
or establish an installation-speed improvement on this machine.
