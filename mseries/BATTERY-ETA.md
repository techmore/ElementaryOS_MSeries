# Native battery time to full

The elementary Power indicator already receives UPower's `TimeToFull` estimate,
but the panel previously showed it only in battery details and descriptive
text. This change adds a compact, rounded estimate beside the existing native
battery icon while charging, such as `1h 24m`; it hides the estimate when the
computer is not charging or UPower has no positive estimate. The label tooltip
spells out the approximate time to full.

`patches/panel-power-charge-eta.patch` applies to the official
`elementary/panel-power` source at commit
`e05723d8cba82b596a5efc259b4e0d15ad9a2bc4`. `install-battery-eta.sh` fetches
that exact commit, applies the patch, builds the native Wingpanel module, checks
its dependencies, backs up the installed module to
`/usr/local/lib/mseries/libpower.so.before-charge-eta`, installs the new module,
and restarts Wingpanel. Run the script with `--uninstall` to restore the backup.
The installer targets the elementary Power indicator 8.0.2 package family.

On the M1 desktop, UPower reported a positive time-to-full while charging. The
patched module built successfully, installed, and Wingpanel restarted and
remained running. The original module was retained as a backup. A visual check
of the panel label was not available in the isolated desktop command session.

## Watt meter in the menu bar (added 2026-10-14)

`patches/panel-power-watts.patch` adds a small label beside the battery icon with the live power draw from
UPower's `EnergyRate` (for example `12.1 W`), whether discharging or charging; it hides below 0.1 W (fully
charged on AC). The tooltip says whether the battery is charging at or the computer is using that power.
It is applied after the ETA patch by the same installer (`install-battery-eta.sh`), so both ship together,
and `--uninstall` restores the original module as before.

Verified: both patches apply in order to `elementary/panel-power` at `e05723d` with plain `git apply`, and the
patched indicator compiles with valac 0.56.19 into `libpower.so` (checked in a scratch tree with the
build-only `libgtop-2.0` dependency removed, since no Vala code uses it). Not verified: installation on the
running desktop and how the label looks in the panel (needs sudo and a login/panel restart).

Fix in the same change: `panel-power-charge-eta.patch` used zero-context hunks. With current `git apply`
they were placed after the end of the class in `DisplayWidget.vala`, which cannot compile; the patch was
regenerated with three lines of context and now lands in the right place.

Install: `sudo apt install libgtop2-dev` (build dependency), then `bash mseries/install-battery-eta.sh`
(or `bash mseries/apply-pending.sh --only wattmeter`).
