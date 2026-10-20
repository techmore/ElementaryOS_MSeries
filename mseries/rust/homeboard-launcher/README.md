# Rust Homeboard launcher installer

This crate ports `mseries/install-homeboard-launcher.sh`. It creates the same
Homeboard `.desktop` entry in the current user's
`~/.local/share/applications`, sets mode `0644`, and prints the same sign-in and
Evolution Data Server notes. It does not install or enable the separate Tasks
sync bridge.

Build with `cargo build --release --locked`; run the resulting
`mseries-homeboard-launcher` as the desktop user. The shell implementation
remains the installed reference until the Rust executable has been exercised
in an elementary desktop session. The current unit test checks the desktop
entry contract; session/menu discovery remains unverified.
