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
