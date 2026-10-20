# Work Mode

Work Mode is an elementary OS System Settings panel for switching between the
usual wallpaper and a separate work wallpaper. Open **System Settings →
Personal → Work Mode** to select the work image, turn the mode on, and optionally
enable a weekday schedule with local start and end times.

The user systemd timer checks once per minute. It stores the current wallpaper
when it first applies the work image and restores that image when Work Mode is
turned off or the scheduled work window ends. GSettings stores the controls;
the original wallpaper snapshot is stored under `~/.local/state/mseries/`.

Install from this checkout with:

```sh
bash mseries/install-work-mode.sh
```

Remove the panel and timer with:

```sh
bash mseries/install-work-mode.sh --uninstall
```

The GSettings values and original wallpaper snapshot are retained on uninstall.
The native plugin build and visual behavior still need acceptance on the target
elementary OS 9 desktop.
