# Upstream contribution candidates (2026-10-19)

Read-only survey of our `mseries/patches/` against elementary `main`. Nothing
was filed or posted; each item needs the owner's go-ahead (and a clean
reproduction without our other patches) before an issue or PR.

## Ready to propose (generic fix, still unfixed upstream)

1. **gala `OSKService.set_input_purpose`** (`gala-disabled-osk-input-purpose.patch`, 17 lines).
   Upstream `main` still has `requires (model_manager != null)`, so input-focus
   updates that arrive while the OSK is disabled raise a critical. Our fix guards
   the null. Smallest and safest PR; against `elementary/gala` `daemon/OSK/OSKService.vala`
   (last touched 2026-08-08).
2. **panel-network `update_interfaces_names`** (`network-null-devices.patch`, 44 lines).
   Upstream `main` still does `devices += iface.device` for every interface, but
   the VPN row has no `NM.Device`, and `NM.Device.disambiguate_names` needs real
   devices. Possibly the same bug as the long-open
   [elementary/panel-network#140](https://github.com/elementary/panel-network/issues/140)
   (Wingpanel hangs/crashes when a VPN connects); not confirmed, test with a VPN profile first.

## Needs re-check before proposing

3. **files filechooser portal startup** (`files-portal-startup-deadlock.patch`).
   Upstream changed this file twice in the last 10 days
   ([#2851](https://github.com/elementary/files/pull/2851), then #2863) and
   [elementary/files#2861](https://github.com/elementary/files/issues/2861)
   reported the portal dialog not appearing after #2851. Our patch (wait for
   `org.freedesktop.portal.Desktop` before the blocking `Granite.Settings` call)
   targets a related startup stall. Rebase on the post-#2863 file and re-test
   before deciding whether it is still needed; if the stall still reproduces,
   comment with our evidence on #2861.
4. **Wingpanel `on_realize` SIGSEGV** (`wingpanel-on-realize-crash.md`, draft).
   Needs a repro without our patched plugins and debug symbols first.

## Keep local (M-series or product-specific)

Brightness, screen dim/corners, dock drawers/offset, power watts, network speed,
CodexBar placement, bluetooth-in-Quick-Settings, keyboard-popover state
(Wingpanel 9 specific) and icon changes are our design choices, not upstream fixes.
`sound-icon-initialization` and `dock-workspace-startup` are plausible but need
a minimal repro on stock builds.

## Housekeeping done alongside

`rust/target/` (377 files, 33 MB) was tracked on `main` and is now untracked and
ignored on `codex/rust-gala-stack-integration`.
