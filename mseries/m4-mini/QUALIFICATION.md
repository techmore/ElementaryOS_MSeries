# M4 mini qualification status — 2026-10-23

Target: owner-reported plain M4 mini, 16 GB, 1 TB, 10 Gb Ethernet,
macOS 27 and HDMI. Expected Mac16,10/J773g identity is not yet measured.
The prepared artifacts do not establish that this machine is ready to install. R6 package checks passed but a fresh upstream audit exposed a WFI init-order bug, so R6 is superseded. R7 carries the early boot-CPU fix and BCM4388 fixes; its kernel build, matching full image/ISO and QEMU live-media test remain pending. Native M4 qualification has not started.
Owner confirms the M4 is currently unavailable for read-only checks and asks
to continue public-source preparation. Hardware receipts remain open; do not
repeatedly request an inventory until availability changes.

## Preparation stop point

This preparation phase ends after the selected R7 kernel and its matched full
image/ISO are built, their artifact hashes and build records are checked into
the repository, and the available ARM64 UEFI/QEMU boot paths have been tested
and recorded. Keep the profile research-only, with installer admission and
hardware qualification false. Stop there: do not write to the mini's internal
SSD or change its APFS/GPT layout. The next phase requires the owner to run the
read-only inventory on the actual mini, then qualify external-media boot and
the native hardware checklist below. Internal dual-boot work can be considered
only after those native checks, backup, and macOS/Recovery return paths pass.

| Requirement | Current evidence | Remaining acceptance |
| --- | --- | --- |
| Current source selection | All 34 tracked refs refreshed; Aurora advanced 87 commits and mainline 45. The WFI ordering and two BCM4388 fixes are adopted in R7; T8132 split-channel ADMAC support is already present in Gravity. R6 includes the built-in Apple watchdog setting | Track future changes as separate candidates; do not mix firmware contracts |
| Kernel | R6 run 39879062230 and independent checks passed for the 16 KiB Image, J773g DTB, 1,597 modules, dependencies and no package hooks, but R6 WFI selection occurs too late for the boot CPU first idle. R7 moves selection into smp_prepare_boot_cpu(), adds two BCM4388 probe fixes, and retains WFxT-off, ISO9660/SCSI CD-ROM and built-in watchdog support. R7 compile/package is pending | Native watchdog takeover, SMP, idle/wake, FP/SIMD integrity, M4 Execution/module boundary, actual 16 GB map, firmware and runtime stability remain open |
| Boot chain | Hosted boot-chain build and downloaded-bundle FAT checks pass; both NO_DISPLAY bootloader stages compile; selected U-Boot wrapper passes with matching config; bundle and synthetic ESP readback pass | Native handoff with required GPU/DCP firmware and owner OS authorization |
| Userspace | Hosted Mesa GLVND build, five AGX groups and downloaded-package software checks pass; 1,626-package research desktop root configured; package/library/schema/session-file checks, Mesa software rendering and real Casper pass | Native M4 GPU/KMS, graphical login and applications |
| Initramfs/EFI | Archive/early modules and real Casper live-hook replay pass; exact research EFI payloads and repeatability checked | Actual root identity and boot on mini; test label is not an owner partition |
| 10 Gb Ethernet | AQTION module, AQC113C PCI alias and dependency resolution verified | Read controller ID; test negotiated speed, traffic, reconnect and error counters |
| HDMI | Gravity reports native HDMI; source profile uses primary DCP/HDMI-A/PHY4 | Owner monitor mode, hotplug and sustained display on elementary |
| Radio/USB | J773g Wi-Fi mapping tests pass; early input modules present | Owner firmware/calibration, USB topology and wired/Bluetooth input |
| Audio | Kernel protection source reviewed; electrical assumptions remain explicit | Actual routing and measured protection; no speaker safety qualification |
| Factory image | Full R5/Mesa6 graph and UEFI ISO passed hosted checks, but local QEMU failed to reach Casper live root because its kernel lacked usable ISO9660/SCSI CD support. R6 added those drivers but was superseded for the WFI init-order flaw; the R6 full-image run was cancelled. R7 retains the drivers | Build and verify R7 kernel and image/ISO; boot via emulated USB and optical paths through Casper live-root/PID 1; then check graphical session, signer trust and installer integration |
| Partition export | Actual 17.48 GB raw GPT/CRC/metadata and three active payloads exported and checked locally; synthetic sector-size regressions pass; no disk import | Metadata-preserving import and destination/macOS preservation |
| Dual boot | Full pinned installer has 26 passing fixture/mock tests; synthetic macOS 27 selects separate IPSW; M4 command-line installer refuses generic disk erase; graphical installer omitted | Metadata-preserving GPT/verity import, owner partition/free-space facts, macOS/Recovery round trip and recovery plan |
| Lifecycle | Gravity reports flaky shutdown/reboot and unsupported sleep; sleep policy packaged | Physical restart/shutdown behavior; do not enable sleep based on assembly |

## Native M4 acceptance sequence

All steps below remain open. Start with a verified macOS backup. The first Linux
session must boot from a disposable external device through the matched Apple
boot chain; do not write to the internal SSD or change its partition map during
hardware qualification.

1. **Identify the exact machine and firmware.** In macOS, run
   `bash macos-inventory.sh` and record model identifier, chip, memory, macOS
   build, SSD capacity/free space, Ethernet PCI identity, and connected HDMI
   mode. Confirm the expected J773g/Mac16,10 target rather than relying on the
   order description. Record the selected Linux stub firmware version and the
   external-boot/security approval state separately from macOS 27.
2. **Prove boot and recovery paths.** Boot the research system from external
   media with the matched m1n1/U-Boot/kernel/DTB/firmware set. Confirm the
   `apple,j773g` board identity, 16 KiB kernel, built-in ISO/CD drivers, built-in
   Apple watchdog, successful takeover before initramfs timeout, and the M4 WFI
   preservation message. Boot back to macOS, then Recovery, before any internal
   storage write.
3. **Exercise CPU, memory, storage, USB, and PCIe.** Confirm all cores online,
   the full 16 GB memory map, no kernel faults under sustained CPU and FP/SIMD
   integrity stress, and clean NVMe/USB/PCIe enumeration. Check NVMe health and
   run file-based read/write stress only on a disposable external filesystem;
   never run raw-device write tests on the internal drive.
4. **Qualify HDMI and graphics.** With the owner's monitor on the mini's HDMI
   port, test cold boot, hotplug, supported modes, repeated modesets, video
   playback, suspend-free screen blank/unblank, and GPU load. Capture kernel
   logs and Mesa renderer/device identity. Check for display loss, GPU reset,
   hangs, or corrupted rendering. Do not treat llvmpipe or QEMU output as a pass.
5. **Qualify both network paths.** Record PCI IDs and driver binding. For the
   10 Gb option, verify `ethtool` reports 10000 Mb/s full duplex against a
   capable peer, run sustained bidirectional traffic, and check errors, link
   recovery, reboot, and thermal behavior. Also test the 1 Gb path if present.
   Test Wi-Fi/Bluetooth only with this mini's own calibration data; never copy
   radio calibration from another Mac.
6. **Check thermal, audio, and lifecycle limits.** Observe fan/temperature
   behavior under CPU/GPU load. Test external audio first; internal-speaker
   safety remains unqualified until protection assumptions are measured. Keep
   suspend disabled. Test shutdown/reboot only after the external boot and
   macOS/Recovery return paths are reliable because Gravity reports these as
   flaky.
7. **Only then evaluate dual boot.** Confirm actual free space, APFS/GPT layout,
   backups, and a recovery plan. The current candidate has no installer
   admission; persistent installation, metadata-preserving partition changes,
   macOS boot, Linux boot, and Recovery round trips each need separate review
   and acceptance before any internal-drive write.

For host facts, run `bash macos-inventory.sh` on the mini in macOS. The script
uses read-only commands and selects model/memory, host firmware, Ethernet PCI
IDs, display mode and capacity fields. Serial-number/MAC-address fields are not
selected. Bash syntax and rejection on Linux are tested; macOS execution has not
run here. Host firmware data does not identify the separately selected Linux
boot-stub firmware. No firmware-version gate should be bypassed.

Keep `research.json` installer/hardware flags false until matching physical
receipts exist. The source and build work can be reviewed in PR #444 while these
requirements remain open. A VM or llvmpipe result cannot close the native M4 gates.
