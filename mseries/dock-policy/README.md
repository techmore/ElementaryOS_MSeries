# Dock opt-out and approval policy

Repository copy of the owner's live dock controls, recorded so they survive a
reinstall. The dock was disabled on 2026-10-18 at the owner's request after
the floating dock stole focus and prevented typing.

| Repository file | Live location |
| --- | --- |
| `POLICY.txt`, `AGENTS.md` | `~/.config/mseries/dock/` |
| `user-disabled.example` | `~/.config/mseries/dock/user-disabled` (the marker itself) |
| `mseries-dock-change` | `~/.local/bin/mseries-dock-change` |

`mseries-dock-change 'description' -- command…` shows the exact command in a
zenity dialog. Cancel is the default, and closing it or waiting 90 seconds
cancels it. Apply runs the command once. Copying these files does not enable
or disable anything. Installing the marker disables the dock; removing it is
a dock change and goes through the helper. The bounded trial lives in
[`../dock-trial/`](../dock-trial/README.md) (on PR #314 until it merges).
