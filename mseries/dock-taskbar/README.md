# Windows taskbar and CodexBar

`install-dock-drawers.sh` uses `prepare-source.sh` as its canonical source path.
It applies the pinned upstream dock, drawers, startup, **Windows taskbar**, then
CodexBar/Start-menu integration and app-tracking patches. It copies the CodexBar indicator sources
from `mseries/codexbar-wingpanel/` so account/quota fixes have one owner.
`TaskbarCodexBar.vala` is the taskbar anchor; it does not replace the launcher model.

## Taskbar launcher sizing

Taskbar mode renders launcher glyphs at 90% of the active size token and trims the item inset. The configured token is
preserved for the shared size ladder and other taskbar elements. The unmanaged 48 px baseline renders at 43 px;
size-managed 40 px renders at 36 px. Horizontal padding is 5 px and the top inset is 10 px. The rendering adjustment
is taskbar-scoped, so floating and classic Dock layouts keep their configured size and upstream padding.
The linked sizing test checks the launcher, item-group width, and separator across size-policy changes. Run the full
isolated build and interaction probes with `bash mseries/dock-taskbar/test-build.sh`; it does not install or restart
the live Dock.

CodexBar sits left of Wi-Fi with a divider and 12 logical pixels on each side.
Popup text is another 25% larger (1.5625em total), with a 400-pixel minimum body width and a
480-pixel scroll viewport so the larger rows remain usable.
Hover waits 250 ms and opens the existing native menu without a keyboard grab.
Leaving gives 450 ms to cross into the popup; clicking pins/toggles the menu.
The updated native Start menu and its scoped Windows 11 stylesheet are bundled
with the taskbar, rather than depending on an untracked user CSS override.

Build without changing the desktop:

```sh
bash mseries/install-dock-drawers.sh --build-only
# CI/review path, without requiring an installed distro dock:
bash mseries/dock-taskbar/test-build.sh
```

The clean-build check links the complete application and verifies the Windows
TaskbarRow, StartMenu and TaskbarCodexBar types. The GTK probe uses a fake HOME,
backend and in-memory settings; it checks hover, focus retention, leave, converting
hover to a pinned menu and click dismissal. CI runs the same build/probe path.
No test installs a binary or restarts a live desktop service.

Future dock patches must use this full stack. App tracking changes belong after
it and must preserve `Taskbar.vala`, `TaskbarCodexBar.vala` and the Start menu.
Do not rebuild from drawers/startup patches alone. Never overwrite the live binary
from an unrelated feature build. Keep desktop deployment ownership serialized.
An installation is a separate owner-authorized action; routine source updates
and tests do not reload the dock.

The dock installer does not rewrite app icons, desktop entries, or launcher pins.
Teams uses the checksum-pinned official icon from `install-teams.sh`; Outlook uses
the transparent official SVG from `install-outlook-web.py`. Both preserve an
existing official asset when offline. Microsoft artwork is fetched locally and
is not redistributed in this repository.

## Deployment evidence

The owner-requested local integration was loaded on 2026-10-20. Its initial source
baseline's machine-code section matched the restored Windows taskbar binary.
Full build, schema, isolated interaction and layout probes passed; Teams/Outlook
entries and ordered pins were checked unchanged. Repository persistence adds the
scoped Start CSS to the resource bundle (the same CSS was previously user-local).
This repository change is validated without another live dock deployment.
Live Wayland hover/placement acceptance remains distinct from fixture results.

Running markers and identity matching: see [`../DOCK-APP-TRACKING.md`](../DOCK-APP-TRACKING.md).

## Reboot and update persistence

The session unit starts `pantheon-rust-dock`, which selects the user wrapper and
private executable under `~/.local/lib/mseries/dock`. The taskbar mode and pins
are persistent GSettings values. Work Mode's enabled login service/timer reapplies
its saved configuration; no temporary shell process is required. Official icons
and launcher metadata live under `~/.local/share` and survive normal package
updates. Repo installers preserve cached official assets on network failure.

The factory payload includes the same taskbar helpers, shared CodexBar sources,
tests and Teams/Outlook installers. The older desktop-space floating-dock profile
recognizes the private taskbar schema and preserves the owner's taskbar size,
visibility and pins during reapplication. Isolated tests build the actual payload
in a temporary root and exercise both taskbar preservation and floating-profile
apply/revert. Reboot configuration checks do not claim a physical reboot test.

## Notification bell

The bell uses a 30-pixel icon without an outer border. The unread count sits inside the bell
as larger 14-pixel plain text without a badge background or accent. History and
context menus follow native theme colors and controls, with compact Open/Reply
actions and bounded previews.

`TaskbarNotifications.vala` is added by the canonical source stack and sits next
to the clock. It reads the desktop notification service's bounded user-session
API asynchronously. Click for history/Open/Reply; right-click for local Mark all
as read and the saved elementary Do Not Disturb setting. Unknown service state
remains visible; a failed setting write does not falsely move the switch.

`bash mseries/dock-taskbar/notifications-probe/run.sh` runs synthetic native UI
checks on a private bus/display with temporary HOME and memory settings. The
fixture refuses direct startup without its private-test flag. Full builds require
the TaskbarNotifications linked type so partial taskbar builds are rejected.
See `../desktop-notifications/README.md` for protocol, insets and history limits.

GTK performance rules shared by every app here: [GTK-PERFORMANCE-ASAHI.md](../GTK-PERFORMANCE-ASAHI.md).
