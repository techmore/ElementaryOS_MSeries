# Public J773g prior-art review — 2026-10-21

**Superseding discovery:** Gravity Linux publishes an M4 mini developer alpha with project-reported HDMI/DCP and GPU support. The earlier Asahi/Aurora-only conclusions below are incomplete. See GRAVITY-INTEGRATION.md and research.json for the newly pinned stack; elementary integration and local hardware qualification remain open.


Source: https://github.com/0xSero/mac-mini-m4-linux/tree/e0d67e3ff9d5595e17ae3833d2afd9fff150e51b

The kernel patch metadata pins base 77cb8f24c2381a8abb7272d7bbdec548d6426a8a
and patch SHA-256 b5faeb76dd312df2a8f2234a20928d921629fc610c09aa891404b268135b3d3e.
The downloaded patch matches that digest. Six changed kernel files cover NVMe,
PCIe and RTKit, rather than a complete mini platform port.

The recorded physical status is dated August 28. Linux reaches init with the
NVMe driver blacklisted; Ethernet DHCP/SSH passed on one host-assisted RAM boot.
ANS mailbox access faults at 0x408168114. The proposed four-domain PMGR parent
chain was built but not tested. HDMI experiments report failures, including a
single RTKit HELLO without a demonstrated modeset. This is useful negative
board evidence, not a bootable dual-boot implementation.

## Why the old patch is not promoted

The PCIe patch adds apple,t8132-setup-stage with early successful returns at
multiple partial initialization stages, before IRQ setup and RID/SID publication.
Those switches are diagnostic controls, not a supported production path.
The NVMe patch adopts live RTKit buffers through identity RAM mappings and adds
new ANS handling. Its own physical status never establishes Linux namespace
reads. Applying it to the elementary release would not satisfy storage safety,
HDMI, thermal, reboot or macOS/Recovery acceptance.

The newer J713 basic-series apple.c at
98a8f830df94a7dcaf7de37bfa915240afa2dda8 has explicit quarantine state and
retains uncertain DMA resources. Its flush handling distinguishes post-M4 ANS
from legacy delayed-flush behavior. That code needs review as a coordinated
boot-producer/DT/kernel bundle; the older diagnostic patch should not overwrite
it or be stacked without a semantic comparison.

## What can be reused

- The mini-specific endpoint identity and DART routing evidence can guide board
  mapping review; Linux bus numbering must not substitute for physical ports.
- The firmware-derived ANS PMGR chain is an unproven hypothesis, not an accepted
  fix. Compare it with current t8132-pmgr.dtsi and captured device-tree data.
- dcpext0 is the mini HDMI investigation path. The J713 internal-panel protocol
  and native-scanout admission do not qualify that external-display path.

Next work is full-source baseline compilation and review of candidate changes
against that baseline. No legacy patch is installed or advertised as support.
