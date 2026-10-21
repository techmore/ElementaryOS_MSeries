# M4 Mac mini: Gravity Linux and upstream audit

**Conclusion:** Gravity has a substantive native J773g developer-alpha port with
project-reported HDMI/DCP and GPU operation. It is the strongest directly relevant
public stack found in this audit. It does not establish that elementary OS or the
owner's 16 GB / 1 TB / 10 Gb Ethernet / macOS 27 / HDMI configuration is qualified.

The audit inspected source, branch history, packaging provenance and selected
production tests. Compilation and synthetic tests are distinguished from physical
hardware results throughout. No kernel, graphics library, partition or bootloader
was installed on the owner's system.

| Component | Selected source | Finding |
|---|---|---|
| Kernel | GravityLinux/linux, gravity-m4, `4fc326f6c25ccceb7515e2635c22e01fde5d3bac` | Linux 7.1.13 with M4-specific storage, display, GPU, radio and speaker changes |
| Mesa | GravityLinux/mesa, `87ac51d411f0e58a9433567ec2666f457be89e1d` | Asahi OpenGL/Vulkan code; UAPI header matches the selected kernel byte for byte |
| Bootloader | GravityLinux/bootloader, `f02d4a52017915febb222539636b5b025a70407a` | Both raw stages compile; development head differs from packaging pin |
| U-Boot | GravityLinux/u-boot, gravity-alpha-20260925, `a2f6913694ff26908c16948af3f8372429782263` | Native apple_m1 build passes; includes NVMe and per-radio calibration handoff |
| Packaging | GravityLinux/packages, `711c2a110416d28010ccdd118b83111776bff207` | Fedora 44 packaging, source lock and upstream attribution |
| Installer | GravityLinux/installer, `6420623289fe7544cb8589b658355e57f0290fcc` | Explicit J773gap admission; separate 26.6.2 firmware stub |
| Image | GravityLinux/kiwi-descriptions, `07bf52cb2866069c072eb03a8f23af9839d0397c` | Fedora image descriptions; not an elementary OS image |
| Runtime scripts | GravityLinux/scripts, `12418e50125a72749a75917db578db55ea42704c` | Fedora/Asahi integration layer, also selected by packaging |

The full pins and local receipts live beside this report in research.json and
receipts/. Development heads are not represented as the exact September alpha
binary bundle.

Gravity's [September alpha announcement](https://gravitylinux.org/blog/early-alpha-m4-mac-mini/)
reports HDMI/DCP and GPU support. It calls out limited testing, unreliable
shutdown/reboot, and missing suspend, USB-C display and Thunderbolt/USB4. Its
OpenGL/GLES claims do not establish complete Vulkan conformance.

The [packaging provenance](https://github.com/GravityLinux/packages/blob/711c2a110416d28010ccdd118b83111776bff207/UPSTREAM.md)
traces the kernel source packaging to Asahi, Mesa packaging to Fedora, bootloader
to m1n1, and platform/remix integration to Fedora Asahi. The declared Asahi base
is `3988dac1664c05fa7c8310fcad8eee10428b5f43`. Gravity's current branch is 70
commits ahead of it; the complete GitHub comparison has 124 changed files.

Against the newer Asahi snapshot `94fb23346d522edf53722357c426a3e58030beea`,
Gravity's graph is 117 ahead and 73 behind. That graph's capped comparison is not
a complete endpoint diff. Comparing the two complete canonical source archives
instead found 104 modified, 34 added and one removed file, across 93,960 and
93,993 non-directory entries respectively. This is a complete content inventory,
not a semantic review of every changed line. Much of the delta is Apple DRM/GPU,
T8132 device trees, audio and firmware integration. There is no basis to treat
this branch as generic mainline Linux support, or to assume it includes every
newer Asahi fix. Inherited v7.3 tags do not change the M4 branch's 7.1.13 version.

The [package source locks](https://github.com/GravityLinux/packages/blob/711c2a110416d28010ccdd118b83111776bff207/sources.json)
select kernel `dea38a96aa86679d5e24da16b799030fe07ad2f6`, rather than the current
development head. The latter adds 13 commits across 14 files, including the mini's
SPMI SID 8 USB-PD select-IRQ correction from 64 to 65, plus shared Air MTP/DCP
changes. Those Air changes require mini regression checks. Packaging also selects
an older bootloader revision. Default U-Boot main is upstream code; the correct
Gravity patch branch is gravity-alpha-20260925.

| Feature | Public/source evidence | Meaning for this owner's mini |
|---|---|---|
| Internal NVMe | Dedicated T8132 ANS2 queue-register handling and enabled board SSD; alpha reports operation | Stronger than older failed diagnostics; no local durability or standalone boot test |
| HDMI | Native 26.6 DCP implementation and J773g HDMI-A/PHY configuration; alpha report | Credible working path, but monitor/mode and owner's hardware untested |
| GPU | Separate asahi_m4 driver and matching Mesa UAPI | Driver must be enabled explicitly; firmware/loader contract remains mandatory |
| Wi-Fi/BT | Sakhalin firmware plus per-radio factory calibration | Common firmware copy alone cannot replace MAC-bound calibration |
| 10 Gb Ethernet | AQtion driver is available; no specific CTO-mini physical pass found | Controller identity, PCIe/DART route, link and sustained traffic remain open |
| Speaker | Kernel-protected J773g PCM/amp/thermal implementation | Different from legacy userspace safety profiles; no local acoustic/thermal qualification |
| Reboot/suspend/TB | Published alpha limitations | Not suitable to promise normal desktop lifecycle behavior yet |
| macOS 27 | Installer source checks a minimum host version and selects a separate 26.6.2 stub | Host version alone is not a blocker or proof of compatible boot firmware |

The GPU driver checks `mBoot-18000.161.10`, its private VM region and five
aligned, non-overlapping reserved regions. DCP requires actual firmware 26.6.2.
The source GPU DT intentionally starts disabled until loader fixups provide the
handoff. These checks must remain intact. The installer selection method accepted
a synthetic macOS 27.0/J773g fixture and chose 26.6.2. Apple's referenced IPSW
answered HTTP 200 to HEAD; that is availability evidence only, not current Apple
signing eligibility or a successful installation.

The U-Boot patch stack includes T8132 memory/NVMe support, RTKit servicing during
controller waits, reset handling, and calibration injection. Wi-Fi WCAL and
Bluetooth BTBF records are bound to the original radio address. U-Boot accepts
bounded BLOB files on the matching ESP and preserves calibration already supplied
in the DT. Reusing another Mac's calibration is not a substitute for extraction
on the target machine. No proprietary blobs were imported here.

The kernel's NVMe delta includes separate T8132 IO queue registers, avoiding the
legacy register interpretation at the same offset. The PCIe delta introduces
port power-controller setup before initialization. DART adds validated canonical
SID remapping, rejects invalid/chained maps, and refuses remapping locked DARTs.
These are source findings; they do not prove fault recovery or isolation on the
owner's hardware.

The upstream DCP AFK fragmentation boundary test passed normally and under address
and undefined-behavior sanitizers. It covers bounds, ordering, truncation,
sequence wrap and completion, not physical HDMI. Both raw m1n1 stages and selected
U-Boot compile. Gravity Mesa compilation, five selected upstream test groups (366 compiler,
10 launcher and five geometry cases, plus two disassembler groups), and private
DESTDIR staging now pass. Isolated software OpenGL creation/render/readback also
passes using llvmpipe. This is userspace loading evidence, not an M4 GPU or
Vulkan device test. The full M4 kernel build remains running. The secondary
Asahi comparison build was stopped to conserve shared filesystem capacity,
retaining its sources/config/logs; it has no successful full-build result.

Omarchy MX's [Stable kernel config](https://github.com/maralcbr/omarchy-pkgs/blob/7e2f6cfec1b3e412ad4fd6ed9611be275a246b30/pkgbuilds/linux-aurora-stable/config#L2702)
and its RC/Edge equivalents enable AQTION=m and TIGON3=m. The owner's lead is
supported at the driver-configuration level. Its [current installer scope](https://github.com/maralcbr/omarchy-mx-mac/blob/72f1906722fd042a54f1e1973610f62dd019531f/README.md)
explicitly admits M1/M2 and excludes M4, so that evidence cannot qualify an M4
10 Gb mini. The elementary candidate now requires both NIC modules too.

The older 0xSero mini diagnostics and J713-derived Omarchy tester remain useful
prior art, but their published NVMe/HDMI failures are not the ceiling of current
Gravity support. Similarly, the official Asahi M4 matrix describes that project's
integration status rather than all downstream forks.

For elementary OS, the appropriate next step is a matched, separately packaged
candidate: kernel/modules/DTB, raw loader stages, U-Boot, Mesa and machine-local
firmware. The draft preparation lane preserves the installed J314S stack. It adds
J773g BCM4388 provisioning, signature checks and firmware fixtures, with explicit
AQtion/tg3 build gates. Hardware boot, 10 Gb traffic, thermal behavior, HDMI,
shutdown/reboot and macOS/Recovery round trips are still required before calling
this setup ready for dual boot.

`package-mesa.py --stage STAGE --source SOURCE --archive PINNED_ARCHIVE
--validation BUILD_RECEIPT --output NEW_DIRECTORY` verifies the five-group
validation receipt, all four graphics library hashes and corresponding source
archive before building an arm64 Debian payload. Packaging passed; the 98 payload
members are confined to the private prefix and documentation, with no maintainer
scripts. An extracted-package llvmpipe EGL render/readback test passed. Missing
manifest and mismatched library hashes were rejected before output creation.
This package requires the build host ABI (including libc6 >= 2.43), so rebuild
against the intended image ABI before distribution. Dependency scanner warnings
are retained in the receipt; no M4 hardware or Vulkan qualification is implied.

The isolated Mesa launcher now preserves Gravity's `nocompress` session flag.
Its extracted-package software rendering and private path/manifest lifecycle
checks passed. Current platform packaging dropped the proposed speakersafetyd
dependency in favor of J773g kernel protection; the kernel explicitly describes
electrical parameters as assumptions awaiting measurement. Physical speaker
safety remains unqualified. Gravity also blocks system sleep through vendor
policy; equivalent M4 image policy and matched UCM routing remain open.
