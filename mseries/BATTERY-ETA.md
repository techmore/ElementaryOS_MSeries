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
