# Gravity M4 mini integration — 2026-10-21

Gravity Linux's September 18 developer-alpha announcement reports working J773g
HDMI/DCP and GPU. This corrects the earlier audit's incomplete upstream scope.
https://gravitylinux.org/blog/early-alpha-m4-mac-mini/

The project flags limited testing, unreliable shutdown/reboot, and missing
suspend, USB-C display and Thunderbolt/USB4. These are project reports, not
local acceptance of elementary OS or this owner's 16 GB machine.

`research.json` now pins Gravity's kernel, Mesa, bootloader, U-Boot, packaging,
installer and image-description heads. Current development heads are not asserted
to be the exact September alpha release bundle. Package specs and release
provenance must be reconciled before building an elementary boot bundle.

The new gravity-mini source profile captures its J773g DT and complete include
closure. `build-dtb.py --source gravity-mini` verifies that capture and compiles
it, retaining diagnostics. Both Asahi and Gravity source versions read 7.1.13,
but their histories diverge: Gravity is 117 commits ahead and 73 behind the
pinned Asahi head. GitHub's comparison returns exactly 300 files and is capped;
it is not a complete patch series and must not be used as one.

Unlike the initial Asahi DT, Gravity's board adds GPU, native external display,
Ethernet and protected speaker resources. Its reserved ramoops address must be
checked against the actual 16 GB loader memory map and bootloader reservations;
source compilation alone does not establish that reservation is usable.

The J713-derived Kb2uka mini tester remains a separate unsuccessful path: issue
136 reports no HDMI after OS approval on October 20 and explicitly holds new
installations. Its source fixes do not supersede Gravity's independent support.
https://github.com/Kb2uka/Omarchy-M4-Native/issues/136

Next: obtain the complete Gravity source and packaging provenance, build its
kernel with a separate module release, reconcile its Mesa UAPI and firmware
handoff, and map the required services to elementary OS without replacing the
working J314S kernel or bootloader. No mini support is enabled in the installer.

## Packaging versus current kernel

The pinned packages sources.json selects kernel dea38a96aa86679d5e24da16b799030fe07ad2f6
and bootloader f64760b501214c749788f89620c078d8b39b0453. Those differ
from the development heads. Mesa is already the same pinned revision. The
current kernel is 13 commits ahead, with 14 changed files. The direct J773g
change corrects the SPMI SID 8 USB-PD select interrupt from 64 to 65. Other
changes include Air MTP and DCP support and shared DART/display changes, so
mini regression validation still matters. The current research build includes
that interrupt correction; it is not described as the original alpha build.

The full build applies Gravity config overlays after Asahi config. In particular
CONFIG_DRM_ASAHI_M4=m is required; the unmodified Asahi fragment leaves it off.
The build wrapper checks this resolved setting rather than treating any successful
Image build as an M4 graphics build. Its first full end-to-end run is pending.

## Reviewed firmware contract

At the pinned kernel, g16.rs validates `mBoot-18000.161.10`, the private VM
region, and five aligned non-overlapping loader-reserved regions before GPU
startup. dcp.c checks actual firmware `26.6.2`. The board's native HDMI
configuration uses the enabled primary `dcp` node with HDMI-A connector and
DPTX PHY 4; older dcpext0-only experiments must not substitute for this profile.
These source-level checks make a coherent loader/firmware bundle necessary.
They have not been exercised on the owner's mini.

## U-Boot branch correction

GravityLinux/u-boot defaults to main at a44f46af, an upstream maintenance
commit. The M4 patch tip recorded in packaging is instead
a2f6913694ff26908c16948af3f8372429782263 on gravity-alpha-20260925.
The selected research pin now uses that branch. Its final change supplies
J773g Wi-Fi calibration alongside Bluetooth, with reported full Fedora
EFI boot validation. These source reports are not local hardware tests.
Default branch discovery is retained as provenance, not used for the build.

## Owner's confirmed configuration

16 GB RAM, 1 TB SSD, 10 Gb Ethernet, macOS 27, HDMI output. SSD free space,
actual model/board identity, monitor mode and exact boot firmware remain unknown.
The reviewed mini prior art uses BCM57762 gigabit Ethernet; it cannot qualify
the optional 10 Gb controller. Initial defconfig leaves both AQTION and TIGON3
disabled. The elementary target overlay now enables both modules and config
gates require them. The live full build was reconfigured with this overlay; both required
NIC modules are required artifacts before payload packaging.

macOS 27 on the host does not identify firmware used by the separate Linux
boot stub. The exact GPU/DCP firmware gates still apply. Do not downgrade the
host or alter its firmware to infer compatibility. The macOS/Recovery round trip
needs qualification on this specific setup.

## Desktop userspace requirements reconciled

Gravity packages 711c2a1 installs ASAHI_MESA_DEBUG=nocompress for desktop
sessions and the login compositor. The private-prefix run-mesa launcher now
adds that flag, selects the sibling EGL/DRI/Vulkan libraries and runs only the
requested child process. It does not change the current session or global
loader configuration. The Vulkan manifest is relocated in a temporary directory
so an extracted payload can be inspected without installing it. --software
forces llvmpipe OpenGL; the Asahi Vulkan selection is still hardware-only.

The rust-speakersafetyd README is an older unpinned scaffold; the current
platform spec deliberately dropped its dependency because J773g speaker
protection is in sound/soc/apple/t8132/pcm.c. That driver mutes on amplifier
fault and DMA stall and applies a thermal model; its electrical parameters
are explicitly assumptions awaiting measurement. Source review does not
qualify physical speaker safety. Preserve the kernel controls and do not
enable the proposed unavailable daemon as a substitute. Matching UCM and
PipeWire routing remain target-image integration requirements.

Gravity also ships vendor sleep policy disabling suspend, hibernate, hybrid
sleep and suspend-then-hibernate. The candidate package-policy.py payload now stages that unchanged vendor
policy with a dependency on the distinct M4 kernel. Package and staged config
resolution checks pass; no host sleep settings changed. Factory image selection
and physical runtime qualification remain open.

## Newer Aurora integration comparison

Aurora integration/aurora was rechecked at 6210b28b00369a4b3bbb769dc3e8c5a1e31d2e87
on October 21. Its Makefile reads 7.3.0, but its J773g board source still only
adds firmware-framebuffer HDMI power domains, and its Asahi Kconfig has no
Gravity DRM_ASAHI_M4 option. This selected-file review does not claim a full
Aurora hardware-support audit. A newer version number alone does not replace
the matched Gravity kernel/bootloader/Mesa contract.

Recent Atlantic RX/TX ring cleanup fixes were checked: aq_ring_rx_deinit and
aq_ring_tx_deinit are byte-identical to Gravity's pinned source. They need no
duplicate backport. Other aq_ring.c differences include AQC113 PTP timestamp
handling; these are not evidence of an M4-specific 10 Gb fix or hardware pass.
See receipts/2026-10-21-aurora-ethernet-comparison.json.

## Required ARM64 packaging exports

The first full compile reached modpost and failed because modular appledrm
references four ARM64 helpers exported by Gravity's packaging layer, not its
kernel Git tree. The wrapper now applies unchanged packaging patches 0003-0006
from packages 711c2a1 with zero fuzz and verifies the resulting pageattr.c/flush.c
hashes. The kernel packager requires the same source contract. The incremental
retry passed modpost and linked vmlinux; final module generation remains running.
The retained .hyp.data non-allocatable-section warning is not suppressed. No
firmware gates or driver functionality were removed to obtain this result.

## Completed kernel artifact validation

The corrected Image/modules/DTBs build and separate Debian payload now pass.
The Image encodes ARM64/16 KiB, DTB identifies J773g, and all 1598 modules are
present. Checked GPU/display/NIC modules have matching vermagic and AArch64
ELF headers. Extracted-package Image hash and modprobe dry-run dependency
resolution pass. Package contents are confined to the distinct module release
and documentation, with no maintainer scripts or boot writes. Atlantic's
AQC113C alias is present; no owner controller/link test has run. See the build
and package receipts. These are build/package results, not boot acceptance.

## Combined candidate payload overlay

`stage-stack.py --kernel KERNEL_DEB --mesa MESA_DEB --policy POLICY_DEB
--output NEW_DIRECTORY` verifies all three package hashes against retained
receipts before extracting into a new root. It runs no package scripts or
installation commands. Combined-root module dependency, sleep config and
isolated llvmpipe render/readback checks pass. Invalid package hashes are
rejected before output creation. This overlay contains no base OS, initramfs,
EFI or firmware; base package dependencies and M4 hardware remain unqualified.
A complete factory image and graphical session activation are still required.
