# Ghidra second pass over matching T6000 Apple drivers

2026-10-16. Offline analysis only; no Neo SSH, device access, kernel install,
reboot or cable change was required. The exact matching Apple inputs were
already available locally. See [REA-DPIN-FINDINGS](../REA-DPIN-FINDINGS.md).

Used the official [NSA Ghidra 12.1.4 release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build),
release source revision `8b6bbb857accdfa20dc5b2f5dea471178c2e9fbc`.
Official ZIP: 569,649,598 bytes, SHA256
`ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db`.
Java: official Temurin `21.0.12.1+1`, Linux aarch64 archive SHA256
`23e37e026f12f3e706f18938ff611db3032d075b09d0879a25d06718c773e223`.
All staged privately. The release ZIP's native decompiler was x86-only for
Linux; a native ARM64 decompiler was built from its included C++ source with
`make -j4 ghidra_opt ARCH_TYPE= OSDIR=linux_arm_64`, then placed in the private
Ghidra `os/linux_arm_64/decompile` directory. No global app/Java changes.

The headless Mach-O loader imported extracted ARM64e AppleDisplayCrossbar
and AppleT8103TypeCPhy drivers. Analysis completed for both; a Java script
selected the known function entry addresses and ran `DecompInterface`.
Temporary projects were deleted. Original binaries were not modified.

| Original entry | Independently corroborated behavior |
| --- | --- |
| `0xfffffe000938c154` | inactive request at `+0x0c`, ACK at `+0x10`, activation watches HPD bit 2 while pending; one-second bound |
| `0xfffffe0009389f68` | stable status/HPD/status reads at `+4/+0/+4`, captured status acknowledgment, HPD acknowledgment on status bit 0 |
| `0xfffffe0009384584` | register byte offsets address 32-bit accesses |
| `0xfffffe0009389264` | DP-IN port initialization and role/HPD-support attributes |
| `0xfffffe0009d60088` | per-tunnel PCLK enable/select and shared tunnel configuration path |
| `0xfffffe0009d63a00` | fixed descriptor, APB 0 then 0x2000, up-to-500ms lock wait, command 3 on failure |
| `0xfffffe0009d3c11c` | descriptor-field packing consistent with derived Linux constants |
| `0xfffffe0009d63ed8` | tunnel PLL/output shutdown path |

This is a second tool cross-check of selected functions, not a runtime trace
or independent proof of the entire tunnel protocol. Both decompilers can
misidentify authenticated indirect-call receivers; original instructions
and resolved authenticated-chain slots remain authoritative for dispatch.
The earlier REA/Kuna results were not replaced with guessed decompiler C.
Full Apple decompiler output and binaries remain private. Original Linux
patches, derived facts, addresses and tool provenance are the shared output.
