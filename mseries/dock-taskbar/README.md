# Windows taskbar and CodexBar

`install-dock-drawers.sh` uses `prepare-source.sh` as its canonical source path.
It applies the pinned upstream dock, drawers, startup, **Windows taskbar**, then
CodexBar/Start-menu integration patches. It copies the CodexBar indicator sources
from `mseries/codexbar-wingpanel/` so account/quota fixes have one owner.
`TaskbarCodexBar.vala` is the taskbar anchor; it does not replace the launcher model.

CodexBar sits left of Wi-Fi with a divider and 12 logical pixels on each side.
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
