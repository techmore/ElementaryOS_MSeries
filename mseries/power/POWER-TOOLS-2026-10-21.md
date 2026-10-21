# Power measurement follow-up — 2026-10-21

## Audit of the prior run

The prior report at `outputs/power-task-first-run.txt` describes two 30-second
observational windows on the active desktop: medians of 17.303 W and 41.203 W.
The conditions differ and the first raw sample is absent, so these numbers do
not establish an improvement, regression, idle floor, battery runtime, or
macOS parity. The retained second-window arithmetic independently reproduces
its summary. Observer overhead and several control fields remain unknown.

The code review confirmed a separate capture-quality defect. Mutter's
`GetCurrentState` can return active modes and layout while the optional
`PowerSaveMode` property is absent. `display_status.py` previously discarded
all returned display information when that property lookup failed. The
one-shot trial then waited for a complete context that this compositor does
not expose.

## Change

`display_status.py` now reports mode, layout, and power-save capabilities
separately. It retains valid modes/layout when only `PowerSaveMode` is missing,
sets `power_save_mode` to unknown, and leaves `available` false because the
full context is incomplete. The one-shot capture waits for modes specifically
and can retain the available observation; qualification still checks the
complete `available` flag, so missing DPMS information cannot become a pass or
an unchanged-controls claim. Existing full-context results remain compatible.

## Checks and limits

- Three new D-Bus capability tests cover full support, missing optional
  `PowerSaveMode`, and unavailable display state.
- Trial-capture checks confirm partial mode data passes only the capture-readiness
  gate while complete-context availability remains false.
- `mseries/power`: diagnostics and display-status suites, 17 tests passed.
- `mseries/aurora`: trial-capture and qualification suites, 29 tests passed.
- `git diff --check`: passed.

No live display, DPMS, power, audio, kernel, boot, or session setting changed.
This is a tooling fix, not a measurement or power-saving result. It does not
establish stable hardware qualification. The current kernel task still needs an
owner-controlled recovery boot to `.20` before suspend or power acceptance.

## Next iteration

Merge the source fix after same-head CI passes. Then use a future authorized
trial to confirm that partial display data is retained with `PowerSaveMode`
explicitly unknown, while full qualification remains blocked until all required
controls are available. Resume matched power measurements only after hardware
recovery gates are satisfied.
