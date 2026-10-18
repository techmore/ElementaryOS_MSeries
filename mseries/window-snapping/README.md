# Native window snapping

The installed M-series desktop uses Gala 8.6.2 with Mutter 50. Half snapping
is an OS setting: `10-mseries-snapping` and `locks` keep edge tiling enabled
and retain Super+Left/Right even when a user database contains older disabled
values. `enhance.sh --only session` also stages this policy for the factory.

`Main.vala` adds quarters inside the compositor, covering native Wayland and
Xwayland windows. Drag a resizable window into any monitor's 40-logical-pixel
corner and release. A quarter preview appears; Escape cancels. Quarter sizes
use that monitor's work area, leaving panel space available. Apps retain their
own minimum size constraints. Managed quarters follow work-area changes as the
patched dock appears and hides. Starting a manual move/resize or changing the
window size ends that managed layout. See the [dock work-area tests](../display-space/README.md#dock-space-follows-visibility).

Keyboard shortcuts:

| Layout | Shortcut | Keypad alternative |
| --- | --- | --- |
| Top left | Super+Alt+U | Super+keypad 7 |
| Top right | Super+Alt+I | Super+keypad 9 |
| Bottom left | Super+Alt+J | Super+keypad 1 |
| Bottom right | Super+Alt+K | Super+keypad 3 |

With this machine's Command/Ctrl swap, physical left **Ctrl** is Super.
The keypad alternatives support Num Lock on and off. Super+Shift+arrows
continue moving windows between monitors.

Install with `bash mseries/install-window-snapping.sh [GALA_VAPI_DIRECTORY]`.
Build dependencies match the drawers plugin: Meson, Ninja, valac, pkg-config,
libgala-dev, libmutter-18-dev, libgee-0.8-dev, plus Git for the pinned public
Gala source (`f0791434ac40a50f2aec64700a47b3bb04145752`, GPL-3.0-or-later).
The new plugin loads at the next sign-in. Installation never restarts Gala.
It installs into both private and stock Gala plugin directories so the existing
stock-compositor fallback also retains quarters.
The normal post-install menu selects this installer by default. Factory staging
includes the half-snap policy; the quarter plugin still needs this native build
and is not claimed as part of a qualified factory image.

Verified 2026-10-18 on the installed machine: compilation and isolated headless
Gala integration with a real GTK Wayland client. All four keyboard quarters,
all four corner drags and Escape cancellation passed. The 1600x1000 test monitor
produces 800x500 quarters. Run `bash mseries/window-snapping/test-nested.sh`
after installation. The fixture has its own D-Bus session, memory settings,
Wayland socket and configuration directory; it never restarts the real desktop.
The active physical-monitor session still needs its next sign-in to load the plugin.

To remove the policy, remove `/etc/dconf/db/local.d/10-mseries-snapping` and
`/etc/dconf/db/local.d/locks/mseries-snapping`, then run `sudo dconf update`.
To remove quarters, remove `libmseries-snapping.so` from the Gala plugin
directories (private and stock) and sign out/in. Leave other profile/database entries intact.
