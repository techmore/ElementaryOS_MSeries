# OS 9 implementation / Claude Code handoff

Updated 2026-10-13. Repository: techmore/ElementaryOS_MSeries.

## Source verified

The official public elementary/os repository was cloned to
/tmp/elementary-os9-public-source. Its main HEAD is
7024fd04646a6a8565bf6805989b59fd72de928c, already merged into this port.
OS 9 is developed on main, not a 9.0 branch. No sponsor-only source or
Early Access binary was used. Component source/licensing still needs
per-component review before importing new patches.

## First implementation

- Replaced the fork's scheduled release workflow (which needed upstream
  signing/R2 secrets) with a manual arm64 build. It uploads an experimental
  ISO, checksum, commit record, and build logs to GitHub Actions artifacts.
  Failed builds retain logs. No official release is published.
- Fixed an image-layer dependency gap: apple-silicon/mkosi.finalize deletes
  package payloads; ExtraTrees cannot resolve apt dependencies. The liveiso
  and sysupdate arm64 configs now explicitly install pipewire-pulse,
  pipewire-alsa, rtkit, and python3-gi.
- Added test-image-wiring.py to catch lost runtime packages in either consumer.
- Fixed finalize deleting the brightness helper and its Pantheon autostart
  entry. A temporary-image cleanup test verifies all shipped helper files
  survive while package payloads are pruned.
- Completed the pending audit/status-page edits and specific bug-fix roadmap.

## Next tasks, in order

Coordination: Codex handles implementation and review; OpenCode handles
build preflight/log analysis using its configured provider (explicitly
approved by the owner). Claude Code can take over from this file. All
agents must document commands, outcomes, blockers, and next steps; commit
and push completed batches. Coordinate Git writes through one agent at a
time. OpenCode's assigned preflight writes only OPENCODE-BUILD-REPORT.md;
Codex reviews and commits its report alongside the implementation.

Model preference recorded from the owner: use Muse 1.3 for OpenCode build
work (`opencode/muse-spark-1.3` is listed as available); DeepSeek 4.1
(`opencode/deepseek-v4.1-flash`) is another preferred option. The initial
preflight used the configured default `opencode/cat-jam-free` before this
preference was supplied. Do not silently claim that run used Muse.

Model-selection references supplied by the owner:
- https://opencode.ai/data/ — usage/session-cost data; assess task results too.
- https://anoma.ly/notes/opencode-2-0/ — service/API and background-task design.
- Owner flagged DeepSeek V4.1 usage credits and a one-week Step 5 Preview
  promotion announced October 8. Verify current eligibility/expiry before
  assuming free use or credits. Step's listed model ID is
  `opencode/step-5-preview-free`.

## GitHub progress

Owner monitoring dashboard: `docs/build-status.html`, linked from the site
home page. It reads public GitHub workflow status every five minutes, shows
actual build stages, and explains when to poke Codex. It cannot wake agents.
GitHub Pages workflow ID 382174750 is used because its workflow is dynamic.
No access tokens are embedded. The dashboard falls back to GitHub links
when requests fail or reach anonymous API limits.

Implementation pushed as 39fd815; reviewed preflight/dependencies pushed as
401dad7. GitHub Pages deployment for 401dad7 succeeded.
The first manual runs were started at 401dad7:
- Experimental arm64 build: https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38396499561
- Validation: https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38396503055

Validation completed successfully, including mkosi config parsing. The
experimental build completed successfully on October 13 (25m 49s).
See FIRST-ISO-BUILD.md for inspected logs, installer/artifact details, and
remaining checks. The installer has not been booted or independently
checksum-verified locally; do not launch duplicate builds without new changes.

Final OpenCode review used `opencode/muse-spark-1.3-contributor-free`, as
requested. It inspected the corrected finalize allowlist, both arm64
consumer configs, workflow, and regression tests; both tests passed and
it reported no new blocker in that scope. No ISO was built by the reviewer.

## Build-log findings and source cleanup

The first successful image log review and dispositions are recorded in
[BUILD-ERROR-REVIEW-2026-10-13.md](BUILD-ERROR-REVIEW-2026-10-13.md).
The ISO label repair now has a focused CI regression test. Follow-up cleanup
also removes a duplicate D-Bus sysuser definition and fixes the image's stale
tmpfiles entries. Run 38400807824 was still building when reviewed; it includes
the ISO-label repair but predates the later sysusers/tmpfiles cleanup. Its
artifact and log should be inspected before starting another full build.

## Next implementation tasks

1. Continue checksum/content/boot qualification from FIRST-ISO-BUILD.md.
   Future workflows retain a small checksum manifest separately from the
   7 GB installer artifact, avoiding a full ISO download just to read its hash.
2. Package the tested Ubuntu speaker chain into the image. Ubuntu supplies
   speakersafetyd/asahi-audio/alsa-ucm-conf-asahi, but its PipeWire build lacks
   the LV2 filter plugin. Build the plugin against the exact image PipeWire
   version and package it reproducibly before enabling DSP. See
   install-pipewire-lv2.sh and install-audio-stack.sh. Do not expose raw
   internal speakers as a fallback or bypass speakersafetyd.
3. Qualify an Asahi kernel and boot path for the factory image. The working
   host uses a custom fairydust kernel; Ubuntu generic is unverified. Do not
   alter this host's bootloader or install an experimental kernel to it.
4. Audit public OS 9 component changes (Gala, Wingpanel, Granite, settings)
   against installed package versions; choose reproducible fixes, not blanket
   desktop upgrades. Record source commits and licenses for each import.
5. Keep omacom/omarchy-mac-pkgs as the Apple hardware behavior reference at
   222f7a8599bbdd287ac6a95362cd51c5b024baae. Translate Arch behavior to
   Ubuntu/Pantheon. Its package repository was not modified by this work.

## Preserve unrelated work

These pre-existing untracked Gala drafts were not changed or committed:
- mseries/gala-daemon-fix/build.py
- mseries/install-gala-osk-fix.sh
- mseries/patches/gala-disabled-osk-input-purpose.patch

Inspect and reproduce the reported OSK issue before incorporating them.

## Verification

Run python3 mseries/test-image-wiring.py and git diff --check.
CI also parses all mkosi configs with just mkosi summary. This workstation
now has just and podman installed and local read-only mkosi summary passed.
Local full image assembly is blocked by disk headroom (see LOCAL-BUILD.md).
The first ISO build succeeded in GitHub CI; no hardware qualification
is claimed. See FIRST-ISO-BUILD.md. This handoff supports manual takeover by Claude Code; it does
not install a timer or automatic agent switch.

## After the successful first build

Public CI log analysis by OpenCode/Muse 1.3 was explicitly authorized by
the owner and completed; see BUILD-38396499561-REVIEW.md. Codex corrected
ARM APT disc architecture metadata and the non-compliant ISO volume label.
Future build records also retain the installer checksum and size separately.
These changes require a new image build; the existing successful artifact
at 401dad7 predates these follow-up fixes. No local kernel/boot/audio changes
were made. Shell syntax and target architecture/label checks passed.

Follow-up runs launched at c1891b6 (queued when recorded):
- Rebuilt installer: https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38400807824
- Validation: https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38400810884
The build dashboard selects the latest run automatically. Inspect these
before starting more builds; the earlier 38396499561 build is complete.

## Local build preparation (October 13)

Owner requested local builds and chose internal storage only if it passes
capacity checks. Installed official Ubuntu just/podman plus dependencies;
local read-only mkosi summary passed and its container sees all 10 CPUs.
Full local image assembly has not started: 37.4 GiB free is below the
conservative 60 GiB disk guard. See LOCAL-BUILD.md and run
`python3 mseries/local-build-preflight.py` before starting a local image.
Disk-boundary/new-directory/tool/architecture tests pass. The public
build monitor now distinguishes this blocked local build from GitHub CI.

## Storage cleanup and expansion plan

Owner authorized clearing downloaded Hugging Face models, disposable caches,
and Fairydust build working copies after validation. The source trees were
archived (452 MiB, zstd integrity test passed), missing build config and actual
running config were preserved in Git, and installed/recovery kernel files
were retained. Six exact snapshots were deleted after explicit approval:
4–7 and migration copies ending 102330/102435; newest rollbacks and all OS
roots remain. Filesystem free space increased from 37.4 to 49.6 GiB.
Full local image build remains blocked by the conservative 60 GiB guard
(10.4 GiB short). See STORAGE-PLAN.md for the actual partition layout and
APFS/Recovery assessment needed before allocating more space to Linux.
No partition resize was performed. Model/browser caches must be downloaded
again when needed; account metadata and installed applications were kept.

## Old OS retirement and local build readiness

Owner explicitly approved the remaining old OS roots and snapshots after
learning that the compiled kernel does not depend on the old build OS.
All approved subvolumes were removed; only @elementary/@elementary-home
remain. Private old-home/config and boot archives passed integrity checks.
Stale Omarchy GRUB entries were removed, preserving elementary's custom USB4
default; active kernel/initramfs/m1n1 SHA-256 checks passed unchanged.
Free space is 69.4 GiB, so local-build preflight now passes. Legacy Arch
rebuild scripts require a new build environment. See STORAGE-PLAN.md.

local-build-worker.sh provides an isolated-checkout build worker with
preflight, source revision, phase/status JSON, build log, final exit status,
and checksum records. It does not install an image or alter host boot files.

First native OS 9 build started at 09:42 EDT October 13, source 89e959d,
isolated checkout `/home/admin/Documents/os9-local-build-20261013`.
User unit: elementary-os9-local-build-20261013.service (Nice=10, no CPU cap).
Worker status/logs are in local-build-records; advancing image-build logs
were verified. Local monitor http://127.0.0.1:8767/ was opened and shows real
phase/log activity. See LOCAL-BUILD.md. Check that job before launching any
more local builds; no local build success or hardware boot is claimed yet.

Native build 89e959d completed successfully October 13, 09:59:08 EDT,
exit 0, elapsed 16m39s. ISO and SHA-256 are recorded in LOCAL-BUILD.md.
Local monitor reads success/complete from the worker status file. Build
artifacts/caches now leave about 39 GiB free; check capacity before rebuilding.
This was image assembly only; no factory-image hardware boot is claimed.

Post-build inspection: ISO SHA-256 verification passed, but the live installer
was missing its Apple hardware overlay. mkosi.profiles/aarch64 is opt-in and
was not selected by daily builds. Fixed by using an Architecture=arm64
mkosi.conf.d drop-in and explicit apple-silicon dependencies. Effective local
summary passes for liveiso and sysupdate. Tests also inspect actual built
liveiso payloads, now called by CI and the local worker. Rebuild required;
the 89e959d image is assembled/hashed successfully but lacks those live-session
helpers. See LOCAL-BUILD.md. Do not describe it as ready for hardware boot.

## Generic VM boot milestone

While corrected GitHub build 38410538372 runs, the existing local 89e959d
ISO booted in QEMU/KVM to the graphical installer language screen. VM had
4 CPUs/4 GiB, network disabled, read-only ISO, no host or writable guest disk.
Screenshot and reproducible command are in VM-SMOKE-TEST.md. Stop at this
milestone: no installer selection, installed guest, or Mac hardware boot was
verified. That ISO still predates the live-session overlay fix; repeat the
content/VM checks on the corrected build before progressing.

## Corrected image completed — 2026-10-13

Run 38410538372, source 32877a7, succeeded at 14:35:12 UTC after 28m27s.
Downloaded small public build records to /tmp/os9-build-38410538372.
image-content.log confirms actual liveiso hardware payload check passed;
checksum manifest and source provenance inspected. Exact ISO/checksum are
in FIRST-ISO-BUILD.md. Installer and records upload steps succeeded.
Next: independently hash and VM-boot this corrected ISO, then implement a
reproducible Asahi kernel/firmware path against KERNEL-REPORT.md. The previous
local ISO's VM boot does not qualify this corrected artifact or Mac hardware.
Untracked Gala drafts remain untouched. No host boot/audio changes.

## Enhanced kernel Debian port started — 2026-10-13

Owner requested merging our kernel enhancements into the test image. Added
fairydust/debian/build.sh: pinned archive/config/USB4 patch hashes, clean patch
application, strict driver/page ABI gate, isolated output, distinct kernel
release, bindeb-pkg, all CPU jobs (explicit dpkg override), and low-space stop.
Source preparation and native Rust toolchain check passed. Installed missing
build dependencies only; no kernel or host boot/audio changes.

The native ARM64 Debian kernel package completed in user unit
elementary-fairydust-deb-20261013c.service, work
/home/admin/Documents/os9-fairydust-deb-20261013, log
/home/admin/Documents/os9-fairydust-build.log. The package was subsequently
rebuilt with built-in PL011 serial support for VM diagnostics. The build helper
supports `--reconfigure` for refreshing a prepared tree and no longer requires
the source archive when resuming a compile. No host kernel or boot files were
changed. Preserved earlier local ISO and build records/kernel config; removed
its regenerable mkosi intermediate outputs and synced Btrfs, restoring ~44 GiB.

Also inspected signed Ubuntu Asahi resolute candidate metadata and packages:
baseline GPU/audio config passes, experimental USB4/video symbols absent.
KERNEL-REPORT.md records verified hashes/fingerprint and the packaging boundary.
check-kernel-config.py plus four regression checks added to validation CI.
Corrected CI ISO download remains active (gh exec session 50981); verify its
checksum before repeating the isolated VM test. It is the generic kernel ISO,
not the newly compiling Fairydust-enhanced image.

## Corrected ISO VM check completed

Corrected run 38410538372 ISO downloaded to os9-corrected-38410538372;
independent sha256sum verification passed. Repeated isolated 4 CPU/4 GiB
KVM/UEFI boot, no network/writable system disk. Graphical installer language
screen and serial login reached. Screenshot committed; see VM-SMOKE-TEST.md.
VM stopped, releasing resources. Enhanced kernel compilation remains active
and separate; next inspect its .deb output and boot hooks, then integrate the
pinned enhanced kernel + m1n1/DTB path into an opt-in test image.


## Fairydust Debian build completed

Native ARM64 .3 package build passed after resolving packaging issues: first
missing libdw-dev, then concurrent DTB directory creation. Corrected source
patch precreates Apple's DTB folder. Completed `elementary-fairydust-deb-20261013f.service`
exit 0. SHA verified at package-inspection time; image .deb SHA
2f48c0619d02b036a625427c2767dc335eb34a0997ab3f371712e2b4541b4b2f.
Extracted contents confirm requested Apple modules and t6000-j314s.dtb.
Runtime dependencies fixed; generic /boot+initramfs hooks still need an
isolated mkosi adaptation. No install or boot test of the new kernel.

Corrected factory ISO independently verified and booted to graphical
installer; see VM-SMOKE-TEST.md. Commit 9edff7f. Next implementation is the
opt-in Fairydust image profile with pinned m1n1, DTBs, packages and mkosi-safe
boot hooks, then VM test. Never touch current host kernel/boot for this work.


## Opt-in image integration staged

Added base/liveiso fairydust mkosi profiles and a manual workflow input to
build the pinned kernel on ARM64 CI and feed it with hash-pinned Ubuntu Asahi
m1n1/U-Boot packages via ignored mkosi.packages. Verified the m1n1 package
contains all three required USB4 tunable/DROM strings. This profile is opt-in.
It does not yet assemble/install the m1n1 ESP boot.bin, so its installer is
for QEMU kernel/installer testing; Mac hardware boot needs that separate step.
Run the workflow with fairydust=true after this commit and inspect summary,
package apt resolution, initramfs, GRUB/ISO boot, then continue m1n1 ESP work.


## Fairydust image workflow first CI attempt (October 13)

Run 38431694534 exercised the new opt-in image workflow. Package source
download, SHA verification, USB4 patch application, config generation, and
strict Fairydust config validation passed. The kernel job then stopped at
`make rustavailable`: GitHub's active rustup stable toolchain lacked its
`rust-src` component. The image job correctly skipped because the kernel
package was not produced. No ISO or host changes resulted.

Fix: explicitly install `rust-src` into the active stable rustup toolchain
before building, and document this requirement. The fetch helper also now
truncates its upstream checksum manifest on rerun. Validation and a fresh
opt-in CI run remain pending.

## Opt-in Fairydust image CI result (October 13)

The first opt-in run 38431694534 failed before compilation because the
runner's Rust toolchain lacked `rust-src`. The workflow now installs that
component explicitly. The fix is commit `4c0cdb9` and has been pushed.

Run [38432118320](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38432118320)
then passed both kernel-package and image jobs. The pinned Fairydust + USB4
kernel package, m1n1 and U-Boot packages were hash-verified and installed in
the image. `test-image-wiring.py` passed; mkosi generated a 79.7 MB Fairydust
UKI and module initrd. The downloaded 7.48 GB ISO passed its independently
recorded SHA-256 and booted to the live login prompt in isolated QEMU/KVM.

Important test boundary: the ISO's GRUB live entry boots `/casper/vmlinuz`
and `/casper/initrd`, which selects the generic kernel. That ISO QEMU run
proves the installer image starts, not the Fairydust kernel. A separate direct
Fairydust-kernel VM smoke test was completed afterward; it verifies generic
ARM64 userspace handoff only. Apple DTB selection, the m1n1 ESP payload and
hardware boot qualification remain open. See `VM-SMOKE-TEST.md` for evidence.


## CodexBar refresh responsiveness (October 13)

Owner approved shortening quota polling after investigation found the local
backend configured for 300 seconds, refresh-on-open disabled, and the native
Wingpanel indicator reading cached snapshots only once per minute.

Changed the native indicator to read snapshots asynchronously every five seconds.
Opening its dropdown requests a refresh when any provider timestamp is missing
or at least 30 seconds old, unless a fetch is running. A monotonic one-minute
cooldown bounds panel-open requests and also accounts for manual refreshes.
The asynchronous reader coalesces overlapping reads, including an open request
that arrives while a snapshot is already being fetched. Provider credentials
and quota fetching remain owned by CodexBar.

Applied `{"refreshSeconds":60,"refreshOnOpen":true}` to the existing backend
through its configure IPC. Installed the tested indicator atomically and sent
Wingpanel SIGTERM so Gala reloaded it. The installed module SHA-256 matches the
built module. Original config and module are retained temporarily at
`/tmp/codexbar-linux-before-refresh.json` and `/tmp/libcodexbar-before-refresh.so`.

Validation: `meson setup /tmp/codexbar-refresh-build mseries/codexbar-wingpanel
--prefix=/usr`, `ninja -C /tmp/codexbar-refresh-build`, and `meson test -C
/tmp/codexbar-refresh-build --print-errorlogs` passed. Five GLib test cases cover
unknown/fresh usage, busy suppression, the exact one-minute cooldown boundary,
and wall-clock changes. The installer now runs these tests before installation.
A temporary GTK/Wayland probe substituted only the backend executable path with
a fake CLI: one-second snapshot delays allowed 143 main-loop ticks in 7.2 seconds,
four snapshot reads, and one refresh despite repeated opens.
`python3 mseries/test-image-wiring.py` passed all four checks; installer shell
syntax and `git diff --check` passed. Source review found no additional blocker.

Live verification observed consecutive Codex fetch timestamps at 14:03:25 and
14:04:25 ET (60 seconds), and Claude at 14:03:34 and 14:04:35 ET (61 seconds),
on October 13. Both cycles completed with empty error fields and `stale:false`.
Wingpanel restarted as PID 625220 and loaded the installed module.

This change is installed on the working desktop; no factory ISO was built.
Next: confirm everyday responsiveness with normal Codex/Claude use.

## Fairydust direct-kernel VM milestone — October 13

The kernel source config enables built-in PL011 console support so ARM64 VM
boot can be observed. Refreshed the prepared build tree with
`build.sh --reconfigure`, rebuilt natively with 10 jobs, and produced kernel
package SHA-256
`6047f67c33c78fd4c614adadb619aa612919e151497d3941fe8949ae08e084f3`.
`vm-kernel-smoke-test.sh` decompresses the Debian kernel image, builds a
temporary BusyBox initramfs, and boots with QEMU/KVM, two vCPUs, no disk, and no
network. Serial output confirmed Linux `7.1.13-elementary-fairydust-usb4`
reached `/init`, emitted `FAIRYDUST_KERNEL_USERSPACE_HANDOFF_OK`, and powered
down cleanly. Config gate and the Fairydust config unit checks pass.

This closes the kernel-decompression/basic-kernel/userspace-handoff check. The
next boot-path milestone is a disposable installed-system test image that can
boot the generated kernel/initramfs and prove Apple DTB selection. It still
needs a reproducible m1n1 `boot.bin`/ESP assembly method. Do not write the
shared host ESP or install this kernel on the host. Full machine boot, Apple
GPU, USB4, speakers, suspend and desktop behavior remain unqualified.

The pinned Asahi m1n1/U-Boot packages can be assembled into stage 2: in a
temporary directory, the package binaries plus 41 Fairydust `t6*.dtb` and
`t81*.dtb` files produced a 5,028,827-byte payload whose FDTs, USB4 tunables,
and compressed U-Boot member all verified. Ubuntu's separate `asahi-scripts`
package contains `update-m1n1`, but its default DTB lookup misses our package
path. Hashes and assembly checks are in `KERNEL-REPORT.md`. Next, add explicit
`DTBS`/`U_BOOT` selection and a disposable image ESP integration before any
hardware path is considered; do not write the shared ESP.

## Fairydust image build and reproducible boot payload — October 13

The opt-in GitHub Actions run 38444570042 succeeded from source commit
`aebf31c97cdb1abd9471b94cec9d2891dd4616f0`: kernel package, image assembly,
live-image hardware-payload check, checksum records, and artifact upload all
passed. The image is 7,481,858,048 bytes with SHA-256
`75b67a02230fc8ac0676e8d8ec7d39fcec8478d9ef9481be7be362c60eab368c`.
The GitHub artifact is [available from the run](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38444570042/artifacts/11841535221);
it was not downloaded because of its size. This is build/image qualification,
not a Mac hardware-boot result.

Added a non-root m1n1 payload assembler and four integration tests. It
reproduced a 5,028,282-byte `boot.bin` from the exact kernel, m1n1 and U-Boot
packages in `/tmp`; SHA-256 and the decompressed U-Boot member are recorded in
`KERNEL-REPORT.md`. The opt-in Fairydust workflow now assembles this payload
from its pinned artifacts, stages it at `efi/m1n1/boot.bin` in the disposable
sysupdate image, and checks the copied ESP file against the source checksum
using `sfdisk` and read-only `mcopy`. The fast validator covers the payload
assembler and GPT offset logic. Full CI run 38479577898 passed and verified
the target ESP entry at GPT offset 1,048,576: `m1n1/boot.bin`, 5,028,282
bytes, SHA-256 `049c5bf29e5e4f379e44e8ef8fffce3a018ede03ee19676c98cc6ee6e8608f8d`.
It completed the installer build and checksumming too. The resulting
`elementaryos-9.0-daily-arm64.20261013230825.iso` is 7,482,648,576 bytes with
SHA-256 `89c74fa25ac72dd8f20f7eb42e456c929ed828f791f77af3edb6f5ce1b7b259d`;
the installer artifact is retained by GitHub for seven days. The image has
not been booted on Apple hardware, and no host ESP was written.

The preceding run 38473436256 exposed an overbroad `elementary_*.raw` guard
that also matched separate partition images. The selector was narrowed to the
timestamped whole-disk image before the successful rerun. See the run's
[build record](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38479577898)
and `mseries/KERNEL-REPORT.md` for verification details.


## CodexBar quota ETA (October 13)

Owner requested a visible ETA for remaining usage. The existing CodexBar Linux
IPC feed already includes the CLI's pace summary for each quota; the native
indicator previously hid it in a tooltip. Added QuotaEta.vala to present those
upstream forecasts and choose the earliest available limiting window.
The bar shows session/general percent remaining plus the limiting quota label
and ETA; both percentages and individual forecasts remain in the dropdown.
An exhausted limit shows its reset countdown. Unknown pace, unsupported wording,
provider errors, snapshots older than three minutes, and expired reset boundaries
suppress forecasts. A safe measured quota does not vouch for an unknown quota.
These are quota estimates based on CodexBar's average usage pace, not exact
remaining token balances or guaranteed exhaustion times. The compact IPC does
not export structured etaSeconds, so recognized upstream summary phrases are
parsed defensively; unknown future wording falls back to unavailable.

Validation: `ninja -C /tmp/codexbar-refresh-build` and `meson test -C
/tmp/codexbar-refresh-build --print-errorlogs` passed (11 ETA cases plus the five
existing refresh cases). Covered session/weekly projections, exhausted-without-
pace, immediate depletion, unavailable/malformed data, stale/provider errors,
expired resets, limiting-window selection, and unknown limits alongside a safe
limit. A temporary GTK/Wayland fixture probe verified rendered bar and dropdown
labels, and the final 332×344 layout was visually inspected. Its synthetic
preview is `/tmp/codexbar-eta-preview/preview.png`; it is not a live account image.
`python3 mseries/test-image-wiring.py` passed all four checks; `git diff --check`
passed. Source review found no remaining blocker.

Installed the built module atomically and reloaded Wingpanel through Gala.
The previous module remains at `/tmp/libcodexbar-before-eta.so` for rollback.
A read-only live snapshot run through the compiled model produced a weekly
forecast for Codex and an exhausted-session reset countdown for Claude.
One-minute backend polling and five-second asynchronous panel reads are retained.
This qualifies the running desktop indicator only; no factory ISO was built.
Next: use the displayed forecasts during ordinary work and reassess if the
upstream pace format changes or a recent-rate estimate is requested.

## Network speed readout persistence — 2026-10-13

The user's panel-speed setting was already enabled, but the plugin had been
installed by replacing `libnetwork.so` in the current `/usr` image. A reboot or
OS image deployment restored the stock file. The Apple Silicon mkosi image now
builds pinned `elementary/panel-network` commit
`8685ec8e55a45e48da0c12931a353cd440d11664`, applies the three tracked network
patches, and places the resulting module into the overlay consumed by both
liveiso and sysupdate. The build checks that the target package remains 8.0.1.x.
`test-image-wiring.py --image-output` now checks the plugin is present in the
final liveiso tree; the sysupdate configuration consumes the same overlay. The
local installer remains useful for the current image, while the new image
build makes the change survive redeployments and image updates.

Validation: `just mkosi summary` parsed the new build script and confirmed
network access is enabled for image build scripts. Running
`build-network-indicator` against the matching host package compiled the
patched module into a temporary stage; the output contained only the
321848-byte `libnetwork.so` and its panel-speed toggle marker. `bash -n` and
`git diff --check` passed. No full image build has run yet. Next: run the
M-series validation workflow, then the full arm64 image build and post-build
module check before deploying the resulting image. The working desktop has the
patched module installed and `~/.config/mseries/network-speed.ini` enables the
panel readout.

## Local general agent continuation (October 13)

Crush v0.98.1 ARM64 is installed from a checksum-pinned release, with an
isolated Local Agent workspace, Applications launcher and native robot-menu
entry. `local-ai/install-agent.sh` reproduces it. Qwen3.5-9B 4-bit answered a
short loopback API request and emitted a structured synthetic tool call on
this M1 Pro. The first full Crush prefill exhausted GPU scratch; the private
server now uses 256-token prefill chunks via `configure-prefill.py`, and a full
Crush answer completed. The final profile admits 32k context and one prompt
cache (8.93 GiB estimate, not measured peak); use catalog ID to retain KV facts.
The user explicitly requested killing the port conflict: whop2p is stopped
and disabled at login. The model is an on-demand user service, not enabled
at login. NAS address/share path remains pending; no NAS writes occurred.
ANE artifacts were already staged and remain unactivated. No kernel, device
tree, bootloader or audio changes were made. See local-ai/README.md and the
October 13 agent receipt for final verification and remaining scope.

## 2026-10-14 hardware session

Dock verified (Dell WD22TB4: hub, mouse, Ethernet; no display). Lid-open
resume works without a dock but the login screen needs a power-button press;
the dock Ethernet icon is recreated on each connect. Both are recorded in
BUG-FIX-ROADMAP.md with evidence and are not fixed. Running code that was only
in PR #1 (docked lid mode, troubleshooter, netspeed) is now being merged to
main so the repository matches the installed system. Next: trace a resume,
add the Realtek firmware and a pinned profile, repeat the docked lid-close test.
