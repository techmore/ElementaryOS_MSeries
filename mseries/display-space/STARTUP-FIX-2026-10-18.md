# Aurora .20 full-height panel and startup repair — 2026-10-18

Installed on the J314S running `7.1.12-2-20261017.20-sep-ARCH`. The earlier
[hotplug/cleanup report](../aurora/hardware-tests/2026-10-18-j314s-hotplug-and-module-cleanup.md)
recorded the symptoms. This follow-up repairs three desktop paths without a
kernel/boot change. **The new Wingpanel is running; a fresh login and owner
visual/startup confirmation remain pending.** No improvement in complete
power-on time is claimed from isolated tests.

## Fixes

1. **Bound the panel's initial width.** Stock `PanelWindow.measure()` starts
   with `int.MAX` before a surface has a monitor. On the patched full-height
   layout this can submit an oversized initial panel request. The follow-up
   `wingpanel-startup-layout.patch` uses the entered monitor, surface monitor,
   then the display's first monitor, with a finite fallback. Monitor-change
   updates remain active. Both Wingpanel installers apply the patch after
   the existing full-height and optional clock-order patches.
2. **Repair indicator transitions.** Empty FlowBoxes previously requested zero
   children per row, producing GTK criticals. Clamp to at least one. Detach
   indicator widgets before refiltering/rebinding bars when moving the clock
   between centered and notch layouts, avoiding two FlowBox parents.
3. **Remove the disabled panel from readiness accounting.** The owner's guarded
   dock launcher intentionally runs a no-window process. Gala still expected
   one dock panel, delaying shell readiness until its five-second timeout.
   A user shell configuration now sets only that dock's `wait-for-n-panels=0`.
   The marker, guarded launcher, command, binary and disabled state are preserved;
   Wingpanel still requires its real panel. Other clients/session types remain.
4. **Migrate cropped saved layouts.** `monitors.xml` requested the old
   `3024x1890@120` at unsupported 1.5 scale; saved desk/laptop profiles also
   used cropped modes. Both now use `3024x1964`, with 2x in the stale XML
   configuration. The desk's `+vrr` suffix is retained. The live built-in display
   is selected at `3024x1964@120.000+vrr`, scale 2. This is selected VRR, not a
   new sustained-VRR qualification.

The live external display remains `3840x2160@30`, scale 1, x=1512. The saved
external desk-profile preference remains `1920x1080@60`; it already differed
from the active display at the start of this repair. Neither was rewritten to
match the other. The current dual-monitor layout was also saved persistently.
Gala's in-memory store reintroduced the old single-monitor configuration when
saving the dual layout; it was corrected again. A board/mode-guarded, nonfatal
`ExecStartPre` helper repairs stale cropped records **before Gala loads them**
on subsequent sign-ins. This avoids a compositor restart during active work.

The repair guard requires the 14-inch M1 Pro model, `show_notch=Y` and an eDP
`3024x1964` mode. Other machines/cropped boots are skipped. It reads only the
explicit saved files; absent files are skipped. A failure cannot block login:
the systemd pre-start command is prefixed with `-`. It does not apply modes,
change external settings, start the dock or probe audio/Touch ID.

## Installation and rollback

```sh
# Build/install the patched panel. It does not install or enable the dock.
bash mseries/install-wingpanel-codexbar-left.sh
# Back up explicit user files, install guarded pre-start repair and adjust readiness.
bash mseries/install-desktop-startup-fix.sh
# Sign out/in when ready to exercise the complete startup path.
```

The configuration installer prints a private timestamped backup directory under
`~/.local/state/mseries-desktop-startup/`, with replaced paths and existing files.
Restore those files individually; remove newly introduced files listed in the
path manifest that had no backup. Reload user systemd units after restoring the
Gala drop-in. Do not replace the dock guard or remove its disabled marker.

This host also has the exact **pre-repair** Wingpanel, XML and profile backup,
plus a file-presence manifest, in private Codex outputs
`2026-10-18/pok/outputs/desktop-startup-backup`. The user shell override,
`20-full-height-layout.conf` and private `display-startup` helper were newly
introduced by this repair. Remove these additions when restoring the exact
pre-repair configuration. The reusable installer's later backup reflects the
already-repaired host, not the initial baseline. Check current config before
restoring; restoring cropped display records under full-height boot reintroduces
the original mismatch. Binary/raw configuration backups remain private.

## Verification

- Built the composed Wingpanel from pinned upstream
  `6b8ae0453b1fd6dc07bd246642998011f04b2125` plus the existing full-height,
  clock-order and new startup patches. Installed/running binary SHA-256:
  `40daf0834854f0f832b572c196818d208b1095a7e9ca0102b92f5086294e674a`.
- Restarted Wingpanel only; Gala relaunched it. `/proc/<pid>/exe` bytes matched
  the installed binary. No GTK criticals were recorded for the new panel during
  the observed restart and display update. No compositor restart/logout occurred.
- Native tests compiled the **actual patched Wingpanel sources** and ran under
  isolated headless Gala: pre-surface width equals 1512, not `int.MAX`; empty
  bars and 20 clock-parent transitions pass with fatal GTK criticals enabled.
- The same isolated Gala test reproduced the baseline missing-panel timeout,
  then removed it after applying the session helper to a no-window fake client.
  It never invoked the owner's dock launcher or installed dock binary.
- Existing native GTK notch/crowding allocation test passed. Twelve Python
  display-space tests passed, covering boot provenance and repair transforms,
  external/VRR preservation, custom sessions and idempotence. Shell syntax,
  ShellCheck on the new scripts and `git diff --check` passed.

Run the native regressions on a host with the existing Wingpanel build
prerequisites, private Gala, `dbus-run-session`, `rg`, GTK4 and Xvfb:

```sh
python3 -m unittest discover -s mseries/display-space -p 'test_*.py'
bash mseries/display-space/test-notch-layout.sh
bash mseries/display-space/test-panel-startup.sh
```

`MSERIES_TEST_GALA_PREFIX` selects a separate staged Gala; optional
`MSERIES_WINGPANEL_SOURCE` supplies a Git source containing the pinned revision.
The native startup test uses temporary XDG config, keyfile settings, a private
D-Bus and Wayland display. It requires a private Gala installation and is not
claimed as part of the generic Ubuntu CI job.

Next: one fresh login under the same `.20` full-height boot; confirm bar width,
clock position, dock remains disabled, no rejected cropped mode, no panel timeout,
and measure time to usable desktop. Compare firmware/boot-menu, kernel and desktop
intervals separately. Dock USB/Thunderbolt faults, Ethernet firmware and audio
causality from the earlier report remain separate open issues.
