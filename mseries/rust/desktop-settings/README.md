# Rust desktop settings

This crate replaces the owner-session setup in `mseries/apply-desktop-settings.py`.
It preserves existing XKB and screenshot shortcuts, writes the custom launcher
bindings through GSettings, applies the existing Pantheon/window/power settings,
creates the screenshot redirect only when safe, and installs user autostart files
for the launcher key watcher and brightness helper.

The factory image stages the binary at
`/usr/libexec/mseries/apply-desktop-settings` and stages its launcher assets under
`/usr/share/elementary-mac/mseries`. The `settings` user stage in
`mseries/post-install.sh` invokes the binary; image creation itself does not apply
these per-user settings. `gsettings` and `xdg-user-dir` provide the system settings
and XDG directory interfaces.

The Python implementation remains the comparison reference. Runtime feature
parity on Pantheon has not yet been verified, and the settings stage continues to
require a logged-in user's D-Bus/GSettings session.
