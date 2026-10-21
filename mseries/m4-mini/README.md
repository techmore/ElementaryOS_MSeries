# M4 Mac mini preparation

Research target: Mac16,10 / J773g / T8132, owner-reported 16 GB. Confirm the
machine identity before producing a boot bundle. Native dual boot is not qualified.

`research.json` pins public candidate sources and companion bootloader proposals.
It is intentionally separate from `../aurora/release.json`: the installed J314S
release, installer and staging tools do not consume these research pins.

Capture the selected public source files into a new directory:

```sh
python3 mseries/m4-mini/prepare-sources.py --output /path/to/new/research-directory
```

The command downloads code/documentation only, retaining source license headers
and SHA-256 receipts. It neither builds nor installs anything. A failed fetch
leaves `INCOMPLETE`; a receipt proves capture, not hardware support. Keep the
source profile beside any derived patch or build receipt.

Start with [the audit](UPSTREAM-AUDIT-2026-10-21.md). The J713 basic and graphics
series modify shared T8132 code but add Air-specific PMGR/display/GPU profiles.
Do not copy those profiles onto J773g or substitute the per-kernel OS DTB for
the shared bootloader control DTB. Firmware framebuffer handoff is distinct
from native HDMI modesetting. The 16 GB memory map must come from the loader.

Next: inspect the captured display protocol and board admission conditions,
review the full candidate diffs, and determine the minimum J773g-specific port.
Build and physical tests remain outstanding. Public J713 tests cannot close
J773g HDMI, storage, thermal or macOS/Recovery acceptance gates.

Source review: the graphics backend documents a firmware-26.6.2 J713 internal-panel profile and explicit board admission. Its DT uses apple,j713-native-piodma and apple,j713-native-scanout. External-display roles remain excluded; changing a compatible string does not establish J773g HDMI support. U-Boot proposal head cc47d3b7c86deb4094dc186d26799602272e37fb differs from the earlier basic-boot revision 6c1d2d148020.

Verification: 13 immutable source files captured; mutable references rejected before output creation; qualification flags remain false; whitespace check passed. No full build or hardware boot.

Compile the captured mini DT and keep compiler diagnostics:

```sh
python3 mseries/m4-mini/build-dtb.py --capture /path/to/research-directory --output /path/to/new/build-directory
```

The builder checks capture hashes and the exact checked-in profile before
running cpp/dtc. The retained build receipt records the immutable source,
commands, output digest and warnings. The 2026-10-21 build passed with one
upstream unit-address warning: AIC node `interrupt-controller@381180000`
has first register address `0x381000000`. This remains unmodified upstream
source. `fdtget` confirms `apple,j773g` and the framebuffer's disabled state;
its memory and framebuffer properties require loader fixups.

See [the mini patch review](MINI-PATCH-REVIEW.md) for the public diagnostic patch disposition and its verified digest.
