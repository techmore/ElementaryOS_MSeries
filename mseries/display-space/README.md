# Full-height native desktop on the 14-inch M1 Pro

## Startup repair on the full-height Aurora .20 host

[October 18 repair](STARTUP-FIX-2026-10-18.md) fixes initial unbounded panel sizing,
empty/transitioning indicator bars, stale cropped saved modes and the disabled
dock readiness timeout. The patched Wingpanel is deployed; full-login validation
remains pending. The historical setup description below predates that boot.

`bash mseries/install-desktop-space.sh` builds the native Wingpanel and elementary
dock, installs them, applies a compact dock profile, and prepares a full-height
boot choice. Run as the desktop user; system changes use sudo. Reboot when ready.
The profile is also an optional post-install stage:
`bash mseries/post-install.sh --only desktop-space`.

The running J314 display exposes 3024×1890 with the camera strip cropped.
`appledrm.show_notch=1` exposes 3024×1964, restoring 74 physical rows. The camera
itself remains opaque. The patched Wingpanel uses the existing date/time indicator
and calendar on the left, alongside Applications and CodexBar. On the full-height
internal M1 Pro panel, two equal scrollable halves protect a conservative 400
physical-pixel center gap plus 16 logical pixels of clearance. The panel is at
least 74 physical pixels tall, scaled to the current logical width. At 2×, that
is a 37-pixel bar in the newly exposed strip. Crowded controls scroll within
each half rather than covering the camera. Cropped mode and external screens
retain the centered native clock. Monitor/scale changes update the layout.
Full-screen applications can still draw behind the physical camera.

The dock uses 40 logical-pixel icons and hides when **any** window overlaps.
Existing pinned apps and the drawer integrations are preserved. Command-drag
(Control-drag with our Command/Ctrl mapping) saves position to
`org.techmore.mseries.dock offset`. Position is clamped to the current screen
and recalculated when the dock size/layout changes. This requires the existing
Gala panel protocol v2 patch for movement; stock protocol v1 still works without
movement. No polling service is added and no power saving is claimed.

## Dock space follows visibility

The private Gala build applies `gala-dock-workarea.patch`: a visible dock reserves
its actual frame height, including the bottom margin. Once the dock is fully
hidden, that space returns to the work area. Maximized windows and native half
snaps follow Mutter's work area; the quarter plugin now reflows its managed
quarters on work-area changes. Windows you resize manually keep their chosen
size. Fullscreen applications retain the complete monitor. The reservation only
affects the monitor containing the dock, and changing hide modes takes effect
without restarting it. Boundary contact still counts as overlap, avoiding an
intelligent-hide resize loop. No polling process or per-frame client resize is
added.

Install with `bash mseries/install-gala-screen-corners.sh` followed by
`bash mseries/install-window-snapping.sh`. Both load on the next sign-in; the
installers leave the current desktop running. This compositor behavior is
separate from the full-height boot profile and requires no boot changes.

`bash mseries/display-space/test-dock-workarea.sh` tests the real private dock,
a GTK Wayland client, native half snaps, all four quarters, repeated reveal/hide,
fullscreen and a second monitor in a separate headless Gala. It uses a temporary
keyfile settings database and its own D-Bus/Wayland session. To test a staged
Gala build, set `MSERIES_TEST_GALA_PREFIX` to its installed prefix. The quarter
plugin must be present in that prefix's `lib/gala/plugins`. Dock builds can be
selected with `MSERIES_TEST_DOCK_PREFIX`. The existing quarter regression test
also accepts `MSERIES_TEST_GALA_PREFIX`.

## Dock activation and session stops

The startup patch waits for Gala's desktop integration before synchronizing
workspaces and ignores stale workspace-removal indexes. Repeated activation of
an existing dock no longer calls `present()` or creates another window when
the panel is not the active keyboard window. Panel visibility stays with Gala.

The wrapper forwards HUP, INT and TERM to its dock child and waits for it to
exit, preventing a normal session stop from leaving an orphaned dock behind.
Signal exit statuses do not mark the private build as broken or start the stock
dock. Actual early failures, missing binaries and missing libraries retain the
stock fallback. SIGKILL cannot be trapped or forwarded by a shell wrapper.

Regression checks:

- `bash mseries/dock-tests/test-startup.sh` compiles the production activation
  and workspace methods against controlled native services. It requires
  `git`, `valac`, a C compiler and GLib/GIO development files, and fetches the
  pinned upstream dock. `MSERIES_DOCK_SOURCE` can select a local Git checkout
  at the same source revision; only its committed files are read.
- `python3 mseries/dock-tests/test-launcher.py` executes the generated wrapper
  with private fake binaries, including signal forwarding, child reaping,
  signal exits, real errors, persistent fallback and missing dependencies.
- The isolated Wayland test above also verifies that three repeated dock
  activations preserve a GTK client's keyboard focus and typed text. It checks
  the real compiled dock, while the native method tests use controlled stubs.

These checks passed on ARM64, including the composed dock build and all eleven
private Wayland test groups. They do not establish the cause or complete repair
of every reported floating-dock incident. The owner's running dock remains
stopped; this audit does not install a new launcher or re-enable it. Physical
session, restart and monitor-transition qualification remains to be done.

## Full-height boot choice

The boot helper duplicates the **exact running kernel's existing stanza** from
`/boot/grub/custom.cfg`, changing only `appledrm.show_notch`. It retains the kernel,
initrd, root/encryption arguments, all original entries and `next_entry`. It makes
`mseries-full-height` the default on normal boots and preserves an already queued
one-shot kernel trial. If a trial is queued, that trial runs first; select the
full-height entry from GRUB or use the following normal boot. On 2026-10-18,
the owner additionally authorized enabling full height in the already queued
`.20-enh1` trial itself; that trial and the native layout now share one reboot.
This separate trial edit is not undone by the profile's `--revert`: restore its
notch parameter to 0 as well before using stock Wingpanel. The generated
`grub.cfg`, kernel/initramfs, firmware and bootloader binaries are not modified.
A missing or ambiguous matching stanza fails before installation. This profile
currently targets the transformed J314 install; factory images remain cropped
until a compatible native panel and boot profile are installed.

## Build, verify, undo

- `bash mseries/install-desktop-space.sh --build-only`: builds both from pinned
  source, checks schemas/libraries, installs nothing.
- `python3 -m unittest discover -s mseries/display-space -p 'test_*.py'`: exact
  boot provenance, encryption retention, idempotence, recovery and refusal tests.
- `bash mseries/display-space/test-notch-layout.sh`: fetches the pinned Wingpanel
  source and tests production geometry/GTK allocation under Xvfb, including
  overflowing controls and fractional scale sizes.
- `bash mseries/install-desktop-space.sh --revert`: removes the managed boot
  choice, restores previous explicit/default dock settings, previous private dock
  build/wrapper and version-matched Wingpanel backup. Log in again/reboot.

The dock schema lives in its private prefix. Only the patched wrapper sets
`GSETTINGS_SCHEMA_DIR`; other applications use their usual settings. Original
dock settings/build/wrapper are saved in
`${XDG_STATE_HOME:-~/.local/state}/mseries-desktop-space`. The first GRUB file
backup is `/boot/grub/custom.cfg.pre-mseries-full-height`; revert removes only
this profile's block so later unrelated boot entries survive.

## Source and licensing

- Wingpanel: `elementary/wingpanel` at
  `6b8ae0453b1fd6dc07bd246642998011f04b2125` (8.0.4 daily base), GPL; modified by
  `mseries/patches/wingpanel-full-height.patch`. Existing CodexBar placement and
  optional clockright ordering remain in the composed build.
- Dock: `elementary/dock` at
  `8b45a68a122947ad3a6427bf6e159ec2acf04ad0` (8.3.3), GPL-3.0; modified by
  `mseries/patches/dock-drawers.patch` and `dock-workspace-startup.patch`.
  The cached DisplayConfig implementation
  is adapted from the same pinned Wingpanel source, retaining its SPDX header.
- Gala: `elementary/gala` at `f0791434ac40a50f2aec64700a47b3bb04145752`
  (8.6.2), GPL-3.0-or-later; `gala-dock-workarea.patch` composes after the
  existing screen/window corners, dimming and panel-offset patches.
- Physical notch height comes from the J314 device-tree `apple,notch-height` (74).

ARM64 compilation and simulated GTK allocation do not establish a successful
full-height hardware boot. Record the post-reboot clock/popover, dock reveal,
placement persistence and monitor switching checks in `OS9-HANDOFF.md`.
