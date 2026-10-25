# Rust launcher key watcher

This crate ports `mseries/mseries-launcher-keys.py` to Rust. It clears
`<Super>space` from Pantheon's input-source bindings, ensures the launcher
shortcuts and their relocatable settings exist, and monitors the media-keys
`custom-keybindings` setting so the entries are restored if that list changes.

The factory image installs it at `/usr/libexec/mseries/launcher-keys`. The
desktop-settings coordinator copies it into the user's launcher helper path;
older images without the Rust binary retain the Python fallback. It uses the
`gsettings` command for settings access and change monitoring.

`cargo test` covers the GVariant string/array parser and shortcut filtering.
Live GSettings and Pantheon session behavior has not yet been verified, so this
is an implemented Rust candidate rather than a feature-parity-qualified
replacement. The Python source remains the behavioral reference.
