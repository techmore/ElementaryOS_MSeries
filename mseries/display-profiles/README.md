# Display profiles

## Built-in VRR on the current Aurora .20 host

The owner enabled builtin VRR in the saved `desk-4k` profile; external fixed
1080p/60 mode, scale, position and primary selection were preserved. The watcher
reapplies a saved fixed mode on `MonitorsChanged`, so a temporary VRR selection
alone can revert: save the intended builtin mode in the matching profile as well.
The laptop-only profile is separate and remains unchanged in this trial.

[Scoped hardware receipt and next-kernel checklist](../aurora/hardware-tests/2026-10-18-j314s-vrr-and-boot-archive.md)
record a user visual pass and brief kernel activation, not sustained VRR. Save a
private backup/rollback before changing profiles. No default installer setting
or watcher implementation was changed by the host-specific opt-in.

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

## October 26, 2026 restore correction

The live J314S watcher had been sending `ApplyMonitorsConfig` with a malformed
GVariant signature, so laptop-only restoration after unplug and saved layout
application failed before Gala could apply anything. Each logical-monitor
tuple needs its own final properties dictionary, followed by the method-level
dictionary; each logical-monitor entry also needs its own properties element.
The repository source and the owner's installed copy now provide both.

The owner's saved dock profile was for an Insignia TV, while the recorded dock
monitor is an AOC 24E2QA. The private profile store now has a separate
identity-matched AOC profile at 1920x1080/60, plus a laptop-only layout matching
the current built-in 3024x1964/120 mode and 1.25 scale. The settings are backed
up locally. The current wip3 session lost its DP tunnel after five DCP
target-validation timeouts. Moving the dock from rear-left to front-left brought
the AOC back on DP-2 at 1920x1080/60, confirmed by the owner. The watcher then
exposed the missing logical-monitor properties element. The installed copy now
includes both corrections and has been restarted. On October 26, an explicit
`mseries-display-profiles apply aoc-dock` returned success and Gala reported the
saved 1920x1080/60 layout at x=2419, scale 1.0. The desktop autostart entry is
enabled and the watcher process is running. This verifies profile application,
but automatic watcher handling of a physical unplug/replug and the laptop-only
restore remain unqualified until a hardware cycle is observed.
