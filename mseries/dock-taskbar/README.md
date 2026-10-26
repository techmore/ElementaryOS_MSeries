# Windows taskbar and CodexBar

`install-dock-drawers.sh` uses `prepare-source.sh` as its canonical source path.
It applies the pinned upstream dock, drawers, startup, **Windows taskbar**, then
CodexBar/Start-menu integration and app-tracking patches. It copies the CodexBar indicator sources
from `mseries/codexbar-wingpanel/` so account/quota fixes have one owner.
`TaskbarCodexBar.vala` is the taskbar anchor; it does not replace the launcher model.

## Launcher badge binding lifecycle backport

The canonical source preparation applies
`patches/dock-launcher-binding-lifecycle.patch`, backported from
[elementary/dock commit `1f55ec4c5fda41b41f6c92e31e80122608500ce7`](https://github.com/elementary/dock/commit/1f55ec4c5fda41b41f6c92e31e80122608500ce7).
That upstream change removes the retained `GLib.Binding` field and its explicit
unbind during Launcher cleanup, and extracts the badge count transform into a
static callback. The backport adapts upstream's newer `dispose` path to the
pinned source's `cleanup` method. It is based on elementary/dock 8.3.3 source
(`8b45a68a122947ad3a6427bf6e159ec2acf04ad0`) and retains that source's
GPL-3.0 license/provenance. The upstream commit is reachable from elementary/dock
`main` at `2b70be3e0cb39ff0e421f24bc1a2f733e0614eac`; the source pin is unchanged
pending package/version coordination with task 03.

The full clean build and `test-launcher-qualification` exercise the resulting
production Launcher with pointer/keyboard actions in light and dark themes.
These establish source compilation and interaction behavior; they do not measure
long-running memory use or qualify the live dock session. Installation, service
restart and native hardware acceptance remain separate gates.

CodexBar sits left of Wi-Fi with a divider and 12 logical pixels on each side.
Popup text is another 25% larger (1.5625em total), with a 400-pixel minimum body width and a
480-pixel scroll viewport so the larger rows remain usable.
Hover waits 250 ms and opens the existing native menu without a keyboard grab.
Leaving gives 450 ms to cross into the popup; clicking pins/toggles the menu.
The updated native Start menu and its scoped Windows 11 stylesheet are bundled
with the taskbar, rather than depending on an untracked user CSS override.

The status area also has an AirDrop button. It opens the same
`MSeries.AirDropPanel` used by Quick Settings, including the receive switch and
expanded visibility, duration and received-files controls. It uses the existing
`omdrop` backend and polls only while the popover is open. Since Windows Work
Mode hides the top panel, this taskbar button keeps AirDrop available in that
desktop mode.

Build without changing the desktop:

```sh
bash mseries/install-dock-drawers.sh --build-only
# CI/review path, without requiring an installed distro dock:
bash mseries/dock-taskbar/test-build.sh
```

The clean-build check links the complete application and verifies the Windows
TaskbarRow, StartMenu, TaskbarCodexBar and AirDrop controls. The GTK probe uses a fake HOME,
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

## T3 token dropdown

The existing T3 launcher dropdown displays provider-wide token history (total,
input, output, cached input, reasoning and available estimated cost), its date
window and freshness. Provider totals include all accounts and are explicitly
distinguished from the selected account's plan windows. Unknown or stale quota
data never becomes a zero-percent or live gauge.

The native T3 connection writes the local status snapshot; the Dock only watches
that file and opens no second server connection. Native GTK/Granite controls
follow the desktop theme. Hover, click pinning and launcher actions are retained
in floating and taskbar layouts.

The updated native producer and private Dock were built, installed and loaded
on 2026-10-26. A connected snapshot supplied nonzero token totals with its source
correctly marked stale. Native Rust tests passed (77), RepoBar tests passed (26),
and the complete patched Dock linked successfully. Both-mode pointer acceptance
and a physical reboot remain separate checks, not implied by these results.


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
