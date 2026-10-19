# Pantheon "failed" on 2026-10-18 21:43: Gala crashed, login fell into GNOME Shell

Claude, read from the journal and coredumps on the owner's j314s (boot `a561630a`, kernel
`7.1.12-2-20261017.20-sep-ARCH`). Owner report: "we tried to boot and pantheon failed", and
GNOME Shell felt slow to come up.

## What happened

| Time (EDT) | Event |
|---|---|
| 19:57 | Boot; autologin starts Pantheon (`pantheon-wayland`) with the patched Gala (`/usr/local/lib/mseries/gala`, via `mseries-gala`). |
| 21:02 | Another worktree (`shelf-native-drop`) reinstalled the patched Gala files in place; the running Gala kept the old (deleted) binary. |
| 21:42:57 | Another worktree reinstalled `librepobar.so` and Wingpanel restarted. Not shown to be related. |
| 21:43:11 | **Gala (PID 2717) SIGSEGV.** `io.elementary.gala@wayland.service` has `OnFailure=gnome-session-shutdown.target`, so the whole Pantheon session ended. |
| 21:43:13 | LightDM greeter appears (autologin only runs once per boot). |
| 21:43:18 | Owner logs in. The greeter's remembered session was **Ubuntu** (AccountsService `Session=ubuntu`, `~/.dmrc` `Session=ubuntu` since 2026-10-14), so this started GNOME Shell, not Pantheon. |

The same crash ended the previous boot: Gala PID 2678 SIGSEGV at 19:52:43, followed by a reboot at 19:53.

## The crash

Both SEGVs have the same stack, in stock Ubuntu `mutter-50.1-0ubuntu2.4`:

```
#0 libmutter-18.so.0 + 0x1631a4          <- ldr x0, [x0, #40] with x0 = NULL
#1 clutter_sprite_invalidate_cursor (libmutter-clutter-18)
#2 libmutter-18 + 0x17dd58
#3 libmutter-18 + 0xecee8
#4 _clutter_event_process_filters
...  clutter_stage_process_event / clutter_frame_clock_dispatch (19:52: clutter_stage_handle_event)
     meta_context_run_main_loop <- /usr/local/lib/mseries/gala/bin/gala
```

So while handling a pointer event, mutter invalidates the cursor and reads a field of a NULL object
(the instruction before loads it from `[obj + 48]`). Just before 21:43 Gala logged repeated
`meta_window_set_stack_position_no_sync: assertion 'window->stack_position >= 0' failed`, which points
at a window that was being unmanaged while the pointer was over it. That link is an inference, not proven.
Ubuntu's debuginfod did not answer within the time limit, so the mutter frames are not named yet.

Not established: whether the stock `/usr/bin/gala` also hits this (it has not run for a full session today),
and which of our Gala patches (corners, drawers, snapping, shelf) is involved, if any.

## Why GNOME Shell felt slow

GNOME Shell itself started in 0.7 s (`org.gnome.Shell@ubuntu.service`). The delay came from the crash cleanup:

- 21:43:12 an app re-activated `xdg-desktop-portal` while no display existed. Its GTK backend failed with
  `cannot open display: :0`, and the portal sat in its start until the 90 s timeout (`start operation timed out`, 21:44:42).
- That queued start job made gnome-session's cleanup fail:
  `Failed to restart DBus service: ... TransactionIsDestructive (xdg-desktop-portal.service has 'start' job queued ...)`.
  So services from the dead session survived into the new login (for example the settings-daemon portal from 19:57).
- In the new session, apps (Mail, Tasks, App Center, Monitor, settings-daemon, polkit agent, Bluetooth) each blocked on
  25 s `Cannot get portal ... Timeout was reached` calls. The portal only came back at 21:45:12, about two minutes after login.

This is specific to logging in after a compositor crash; a clean login was not measured.

## Changes made

- Login default set back to Pantheon: AccountsService `SetSession`/`SetXSession` to `pantheon-wayland`, and
  `~/.dmrc` `Session=pantheon-wayland`. Autologin was already `pantheon-wayland`.
- Added `mseries/install-portal-relogin-fix.sh`: a user drop-in `ConditionEnvironment=WAYLAND_DISPLAY` for
  `xdg-desktop-portal.service`, so a portal start without a display ends at once instead of blocking the D-Bus
  restart. Installed for the owner; the running portal was not restarted. Unverified until the next compositor crash.

## Next

- Name the mutter frames (debuginfod for build ID of `libmutter-18.so.0`, or `mutter` dbgsym) and check upstream
  mutter 50.x for a fix in the cursor-invalidate path.
- If it recurs, run one session on stock Gala (`touch ~/.cache/mseries-gala-failed`, log out and in) to tell a mutter bug
  from one of our patches. That drops the rounded corners and drawers, so it is the owner's call.
- Agents reinstalling Gala or Wingpanel plugins into the live session should say so in the handoff; the crash is not tied
  to those installs, but they make the timeline harder to read.
