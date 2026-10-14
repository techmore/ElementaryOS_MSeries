# Native Torrential package

This downstream packaging layer installs the Torrential Rust/GTK 4/Granite app
as an ordinary elementary OS application. It uses the system Transmission
daemon and OS libraries; it does not use Flatpak.

The build script accepts a local fork descended from upstream commit
`3af2c2ab473d074bb95a63a3bb185d5809ee8d8a`. The current M-series worktree is
`/home/admin/Documents/TorrentialFork` on `mseries-native`. To build from a
different checkout:

```sh
TORRENTIAL_SOURCE_DIR=/path/to/torrential \
  mseries/torrential-native/build-deb.sh
```

The resulting `.deb` is written under `build/torrential-native/`. Install it
with `sudo apt install ./build/torrential-native/elementary-torrential_*.deb`.
The package depends on the OS-provided `transmission-daemon`; it does not
bundle or start a Flatpak runtime. The desktop entry appears in the app menu.

This packaging recipe does not include upstream source. The audited upstream
snapshot has no license file, so do not publish the resulting package or
integrate upstream source into the public OS repository without resolving its
license. Local personal builds remain separate from the OS image.

The recipe accepts elementary's `libgranite7` package and Ubuntu's alternative
package name. Its AppArmor addition permits the daemon to save Torrential state
in `~/.config/torrential`, access `~/Downloads`, and receive SIGTERM. A custom
XDG Downloads folder needs a matching local policy rule. Other local policy
entries are preserved during installation and removal.

On a fresh desktop installation, stop the newly installed system daemon before
opening Torrential so the app can own the RPC port:

```sh
sudo systemctl disable --now transmission-daemon.service
gtk-launch com.github.davidmhewitt.torrential
```

If an existing system daemon is serving other clients, review that conflict
before stopping it. The app currently expects its own backend on loopback port
9091. See `../TORRENTIAL-PORT.md` for the live download result and remaining
qualification. Launching requires an active desktop session.
