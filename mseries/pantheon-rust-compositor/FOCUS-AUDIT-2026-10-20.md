# Dock and window focus audit — October 20, 2026

The owner reported that the floating dock had repeatedly interrupted typing, and
requested a code audit before re-enabling it. The live dock remains disabled by
`~/.config/mseries/dock/user-disabled`. This audit does not claim to reproduce the
historical October 18 event or prove its unique cause.

## Findings and fixes

| Path | Evidence | Change |
| --- | --- | --- |
| Dock activation | The retained local 8.3.3 drawer source calls `active_window.present()` on every activation and uses keyboard-active-window absence to decide whether to construct another window | Rebuilt the private dock using the existing `dock-workspace-startup.patch`: existing windows short-circuit activation; repeated activation does not present or recreate it |
| Native Rust startup | `pantheon-dock.service` executes the distro binary directly, bypassing the private patched wrapper | Package a dock launcher which honors the owner opt-out and uses the private wrapper before stock fallback |
| Reinstallation | The installer-generated wrapper previously omitted the live wrapper's disable guard | Preserve the opt-out before both patched execution and stock fallback; regression covers a missing private binary while disabled |
| First panel buffer | `xdg_shell::handle_commit` runs ordinary initial placement and keyboard focus for a panel, before panel-specific commit handling | Exclude registered panels from ordinary app placement/focus |
| Protocol panel focus | `io_elementary_pantheon_panel_v1.focus` accepts any mapped panel, without a session-lock check | Limit this explicit route to the unlocked top panel; the bottom dock cannot request keyboard focus through it |
| Activation tokens | Valid xdg activation can target a panel | Ignore panel targets; app activation and explicit top-panel menus keep their paths |
| Mixed-client restore | Runtime test showed native Wayland restore marked the window focused while leaving `x11_keyboard_focus` set, so keys went to the old X11 client | Use the common focus helper for desktop-interface restore and activation; clear X11 routing before panel and popup keyboard focus |
| Locked-session popups | xdg popup grabs did not check session lock | Reject popup grabs while locked |
| Disappearing apps | Minimized windows remain in workspace state and the desktop interface can restore them, but the dock is unavailable | Add an explicitly launched recovery chooser; no periodic focus changes or keyboard grabs |
| XWayland snapping | Tiling and drag preview return early without a native xdg toplevel | Configure X11 clients and retain their tile across work-area changes, monitor movement and overview restoration |
| Edge snapping | Drag zone selection recognizes only four corners | Add left/right half zones; preserve quarter priority and Escape cancellation |

## Other focus paths inspected

- Clicking a panel already raises it without changing keyboard focus in
  `input.rs`; application clicks use the common keyboard-focus helper.
- The dock tooltip sets `autohide=false`, `can_focus=false`, `can_target=false`,
  and `focusable=false`. Drawer assignment is an in-window panel, avoiding a
  GtkPopover grab. These paths do not explicitly request application focus.
- App icon activation and cycling intentionally call `FocusWindow`; workspace
  items intentionally activate a workspace. Context menus may take normal popup
  grabs after explicit interaction. This audit does not qualify every menu or
  physical trackpad interaction.
- Top-panel menu focus remains available. Lock checks were added to the touched
  entry points; this is not a complete security audit of every shell protocol.
- The private wrapper now forwards stop signals and reaps its child, using the
  repository's existing fix. The previous live wrapper lacked this logic.

## Qualification and deployment boundary

Native build/tests and isolated Xvfb/D-Bus tests are recorded in OS9-HANDOFF.
The isolated stock-dock run passed X11 half geometry (640×800 on 1280×800),
minimize/restore, startup/repeated-activation focus preservation. A separate run
of the rebuilt private dock additionally verified actual text delivery after
activation. The expanded native Wayland test initially failed actual typing after restore;
that failure led to the mixed-client routing fix above. The final expanded test
passes native half snapping, restore and actual text delivery too. Earlier
isolated runs also emitted intermittent dock GLib list-store/object warnings;
the final run did not, but broad dock catalog/menu stability remains unqualified.
These are scoped regressions, not a claim that every historic
focus failure is eliminated.

The live compositor must load the new binary at a fresh login. Installing the
package must not restart the current compositor, Wingpanel, or dock. The user's
disable marker remains in place. Do not re-enable a dock against the older
running compositor just because the updated binary is installed on disk.
