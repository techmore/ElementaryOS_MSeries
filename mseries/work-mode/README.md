# Windows Work Mode

Windows Work Mode is an elementary OS System Settings panel for a Windows-inspired
work setup. Open **System Settings → Personal → Windows Work Mode** to turn it on,
choose one of five supplied wallpapers or another image, enable a weekday schedule
with local start and end times, or limit it to work networks identified by public IP. While active, it also shows the existing elementary
bottom dock with a 40-pixel icon size and no auto-hide. Your pinned apps and native
running-window behavior stay in the dock. This is a launcher dock preview, not a
complete Windows taskbar: it does not add Start, search, system tray or widgets.
The usual wallpaper and dock preferences are snapshotted and restored when Windows
Work Mode turns off or the work window ends.

The included choices are Azure Bloom (the default), Blue Flow, Blue Ribbons, Violet Arc,
and Forest Flow. Azure Bloom is rendered from `work-mode-azure-bloom.svg` in this
directory (`rsvg-convert -w 3840 -h 2160`), original CC0 artwork for this project. The
other newer choices are original artwork generated for this project; none of
the bundled files are copied from Windows Spotlight or Microsoft themes. A custom
image can be selected through the file chooser.

## Rules

Windows Work Mode applies only while **every** rule you turned on is satisfied:
the main switch, the schedule (if on), and the work-network rule (if on). With
both schedule and network on, it means "during work hours, at work".

**Work network.** Turn on *Only on work networks* and list your workplace's
public addresses, comma-separated: single IPv4/IPv6 addresses or CIDR ranges
such as `203.0.113.0/28`. *Check* shows this computer's current public address and
*Add* lists it. The address comes from `https://api.ipify.org` (the
`public-ip-service` key), which is contacted only while this rule is on and the
other rules already pass. The answer is cached in
`~/.local/state/mseries/work-mode-public-ip.json` for 15 minutes per uplink; a
change of default route (Wi-Fi, Ethernet, dock, VPN) triggers a fresh check. If
a check fails, the last answer for the same uplink is reused for up to 30
minutes; otherwise the normal desktop stays.

```sh
~/.local/bin/mseries-work-mode --status      # current state, never contacts the service
~/.local/bin/mseries-work-mode --public-ip   # fresh lookup
```

The user systemd timer checks once per minute. It stores the current wallpaper
and dock preferences before the mode first applies them. If the elementary dock
was not already running, a dedicated user service starts it and stops it again
when the mode ends. GSettings stores the controls; original desktop state is
stored under `~/.local/state/mseries/`.

Install from this checkout with:

```sh
bash mseries/install-work-mode.sh
```

Remove the panel and timer with:

```sh
bash mseries/install-work-mode.sh --uninstall
```

The GSettings values and original state snapshot are retained on uninstall. The
bottom dock uses elementary's existing dock package and pinned launchers.

## Taskbar

With the M-Series dock build (`mseries/patches/dock-taskbar.patch`), Windows Work Mode turns the dock
into a full-width taskbar: weather at the left, a Start button and Search box beside the centred apps,
and status icons plus the clock at the right. Start opens a Windows 11-style Start menu. Right-click
Start for Lock, Log Out, Restart, Shut Down and System Settings. The top bar is hidden while the mode
is active, and windows cannot be placed behind the taskbar.

`icons/windows-work-mode-folder.svg` is an original Windows 11-style folder icon (CC0).
