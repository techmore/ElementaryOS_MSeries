# M4 mini qualification status — 2026-10-21

Target: owner-reported plain M4 mini, 16 GB, 1 TB, optional 10 Gb Ethernet,
macOS 27 and HDMI. Expected Mac16,10/J773g identity is not yet measured.
The prepared artifacts do not establish that this machine is ready to install.
Owner confirms the M4 is currently unavailable for read-only checks and asks
to continue public-source preparation. Hardware receipts remain open; do not
repeatedly request an inventory until availability changes.

| Requirement | Current evidence | Remaining acceptance |
| --- | --- | --- |
| Current source selection | Gravity kernel/Mesa heads rechecked; selected mainline/Aurora comparisons retained | Track future changes as separate candidates; do not mix firmware contracts |
| Kernel | Hosted build and downloaded-package checks pass; full Image/modules/DTBs pass; 16 KiB header, J773g DT, module inventory/vermagic checked | Final-DT RAM/ramoops checker passes synthetic tests; actual 16 GB map and runtime stability still needed |
| Boot chain | Hosted boot-chain build and downloaded-bundle FAT checks pass; both NO_DISPLAY bootloader stages compile; selected U-Boot wrapper passes with matching config; bundle and synthetic ESP readback pass | Native handoff with required GPU/DCP firmware and owner OS authorization |
| Userspace | Hosted Mesa GLVND build, five AGX groups and downloaded-package software checks pass; 1,626-package research desktop root configured; package/library/schema/session-file checks, Mesa software rendering and real Casper pass | Native M4 GPU/KMS, graphical login and applications |
| Initramfs/EFI | Archive/early modules and real Casper live-hook replay pass; exact research EFI payloads and repeatability checked | Actual root identity and boot on mini; test label is not an owner partition |
| 10 Gb Ethernet | AQTION module, AQC113C PCI alias and dependency resolution verified | Read controller ID; test negotiated speed, traffic, reconnect and error counters |
| HDMI | Gravity reports native HDMI; source profile uses primary DCP/HDMI-A/PHY4 | Owner monitor mode, hotplug and sustained display on elementary |
| Radio/USB | J773g Wi-Fi mapping tests pass; early input modules present | Owner firmware/calibration, USB topology and wired/Bluetooth input |
| Audio | Kernel protection source reviewed; electrical assumptions remain explicit | Actual routing and measured protection; no speaker safety qualification |
| Factory image | Actual 6.6G factory base build passes; 1,650 packages, kernel/module hashes and Mesa retention checked | Complete image assembly, actual graphical session and Apple installer integration |
| Partition export | Metadata/payload exporter passes synthetic GPT/CRC/sector-size tests; no disk import | Real M4 sysupdate artifact, metadata-preserving import and destination/macOS preservation |
| Dual boot | Full pinned installer has 26 passing fixture/mock tests; synthetic macOS 27 selects separate IPSW; M4 command-line installer refuses generic disk erase; graphical installer omitted | Metadata-preserving GPT/verity import, owner partition/free-space facts, macOS/Recovery round trip and recovery plan |
| Lifecycle | Gravity reports flaky shutdown/reboot and unsupported sleep; sleep policy packaged | Physical restart/shutdown behavior; do not enable sleep based on assembly |

For host facts, run `bash macos-inventory.sh` on the mini in macOS. The script
uses read-only commands and selects model/memory, host firmware, Ethernet PCI
IDs, display mode and capacity fields. Serial-number/MAC-address fields are not
selected. Bash syntax and rejection on Linux are tested; macOS execution has not
run here. Host firmware data does not identify the separately selected Linux
boot-stub firmware. No firmware-version gate should be bypassed.

Keep `research.json` installer/hardware flags false until matching physical
receipts exist. The source and build work can be reviewed in PR #444 while these
requirements remain open. A VM or llvmpipe result cannot close the native M4 gates.
