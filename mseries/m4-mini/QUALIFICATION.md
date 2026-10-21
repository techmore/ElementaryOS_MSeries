# M4 mini qualification status — 2026-10-21

Target: owner-reported plain M4 mini, 16 GB, 1 TB, optional 10 Gb Ethernet,
macOS 27 and HDMI. Expected Mac16,10/J773g identity is not yet measured.
The prepared artifacts do not establish that this machine is ready to install.

| Requirement | Current evidence | Remaining acceptance |
| --- | --- | --- |
| Current source selection | Gravity kernel/Mesa heads rechecked; selected mainline/Aurora comparisons retained | Track future changes as separate candidates; do not mix firmware contracts |
| Kernel | Full Image/modules/DTBs pass; 16 KiB header, J773g DT, module inventory/vermagic checked | Actual 16 GB loader map, reservations and runtime stability |
| Boot chain | Both raw bootloader stages and matching U-Boot compile | Native handoff with required GPU/DCP firmware and owner OS authorization |
| Userspace | 188-package configured base root; package audit and llvmpipe pass | Complete elementary desktop, native M4 GPU/KMS, login and applications |
| Initramfs/EFI | Archive/early modules pass; exact EFI payloads and repeatability checked | Actual root identity and boot on mini; test label is not an owner partition |
| 10 Gb Ethernet | AQTION module, AQC113C PCI alias and dependency resolution verified | Read controller ID; test negotiated speed, traffic, reconnect and error counters |
| HDMI | Gravity reports native HDMI; source profile uses primary DCP/HDMI-A/PHY4 | Owner monitor mode, hotplug and sustained display on elementary |
| Radio/USB | J773g Wi-Fi mapping tests pass; early input modules present | Owner firmware/calibration, USB topology and wired/Bluetooth input |
| Audio | Kernel protection source reviewed; electrical assumptions remain explicit | Actual routing and measured protection; no speaker safety qualification |
| Dual boot | Installer policy accepts synthetic macOS 27 and selects separate IPSW | Owner partition/free-space facts, macOS/Recovery round trip and recovery plan |
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
