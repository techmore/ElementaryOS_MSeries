# Dock opt-out

The dock was disabled on 2026-10-18 at the owner's request after the floating
dock stole focus and prevented typing. It has been permanently enabled since
2026-10-20.

The manual GUI approval workflow (`mseries-dock-change`, `POLICY.txt` and the
`AGENTS.md` notice) was removed on 2026-10-21 at the owner's request. Dock
changes, installs and restarts no longer need a dialog.

The opt-out switch remains: `user-disabled.example` is the marker that, when
installed at `~/.config/mseries/dock/user-disabled`, makes the launcher wrapper
and `pantheon-dock.service` skip the dock. Nothing installs it by default.
The bounded trial lives in [`../dock-trial/`](../dock-trial/README.md).

## Permanent enablement approved October 20

The owner visually confirmed the dock and explicitly requested permanent
enablement. `enable-permanent.sh` removes the bounded-trial hooks and pending
login trial, disables auto-hide, selects 48-pixel icons (the size system's native token, 48 at the default step;
see [`../ui-scale/SIZE-SYSTEM.md`](../ui-scale/SIZE-SYSTEM.md)) and starts the normal
Pantheon dock service. The Rust session already wants this service at login.
It supersedes the earlier opt-out.
The dock remains the patched Vala/GTK dock hosted by the Rust compositor; a
Rust dock rewrite is separate work.
