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

## Display Settings app

`mseries-display-settings` (installed by `install-display-profiles.sh`, appears as "Display Settings (M-series)"):

- **Arrange:** drag monitors (snap edge to edge), resolution / refresh rate / scale / rotation from what each
  monitor actually offers, "recommended" markers, primary, on/off, full mode list, 15 s keep-or-revert on Apply,
  save/apply profiles.
- **Diagnose:** plain-language findings from DRM, Gala, the kernel log and Thunderbolt, e.g. "detected, but the screen
  is not getting a picture" (with a re-apply button), "dock connected for USB but no video yet", "4K only offered at 30 Hz".
- Preview without touching the display: `MSERIES_DISPLAY_FAKE=1 mseries-display-settings`.
- Tests: `python3 -I mseries/display-settings/test_display_diag.py`.
- Verified: unit tests and headless renders only. Drag, Apply and the diagnostics against the live system are not yet exercised in a real session.

## After an unplug

Gala falls back to its own saved single-monitor layout, which can differ from yours (observed: built-in scale 2.0 with
the monitor attached, 1.5 after unplugging). Save the layout you want with only the built-in display attached
(`mseries-display-profiles save laptop-only`, or "Save layout as profile" in Display Settings); the watcher then
re-applies it after an unplug. The watcher also logs how long Gala took to drop the external output.
