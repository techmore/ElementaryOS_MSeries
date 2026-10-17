# Display profiles

Remember a monitor layout per set of attached displays (home desk, work dock, ...)
and re-apply it on hotplug.

```
mseries-display-profiles save desk-4k   # store what is on screen now
mseries-display-profiles list
mseries-display-profiles apply          # profile matching the attached displays
mseries-display-profiles watch          # autostarted: apply on every hotplug
```

- Matching is by monitor identity (vendor/product/serial), so a monitor on a different port still matches.
- A saved mode that the monitor no longer offers falls back to its preferred mode.
- On hotplug the watcher first sets the external screen to 1920x1080@60 for ~2 s, then the saved mode.
  Reason: on the M1 Pro built-in HDMI a replug trains the link but Gala does not re-apply a mode, so the
  screen stays at "no signal"; a changed mode forces the display coprocessor to modeset.
  Reproduced by applying 1080p then 4K by hand; the automatic replug path is not yet tested.
- The 3840x2160 mode on that TV is offered at 30 Hz only (no 60 Hz mode is advertised).
- Saved profiles: `~/.config/mseries/display-profiles.json`. Tests: `python3 -I test_display_profiles.py`.
