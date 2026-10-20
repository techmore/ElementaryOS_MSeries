# Windows Work Mode

Windows Work Mode is an elementary OS System Settings panel for a Windows-inspired
work setup. Open **System Settings → Personal → Windows Work Mode** to turn on the
supplied Blue Flow wallpaper, choose another image, or enable a weekday schedule
with local start and end times. While active, it also shows the existing elementary
bottom dock with a 40-pixel icon size and no auto-hide. Your pinned apps and native
running-window behavior stay in the dock. This is a launcher dock preview, not a
complete Windows taskbar: it does not add Start, search, system tray or widgets.
The usual wallpaper and dock preferences are snapshotted and restored when Windows
Work Mode turns off or the work window ends.

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
