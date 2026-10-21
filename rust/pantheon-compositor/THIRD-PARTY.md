# Third-party source

`src/` adapts Smithay's `smallvil` example compositor from
<https://github.com/Smithay/smithay/tree/023b78b1c5a05ca512767cacc07efca55fae8be4/smallvil>.
The upstream license is included as `SMITHAY-LICENSE.txt`.

`protocol/pantheon-desktop-shell-v1.xml` is based on elementary/Gala's
`protocol/pantheon-desktop-shell-v1.xml` at commit `f0791434`
(<https://github.com/elementary/gala/tree/f0791434/protocol>), released under
LGPL-2.1-or-later. This copy advertises protocol version 2 and includes the
M-series `set_offset` request already used by this repository's Gala/Dock
patches. The source XML retains its copyright and SPDX notice.

The `org.gnome.Mutter.DisplayConfig` compatibility interface follows the public
D-Bus contract in GNOME Mutter's
`data/dbus-interfaces/org.gnome.Mutter.DisplayConfig.xml`
(<https://gitlab.gnome.org/GNOME/mutter/-/blob/gnome-46/data/dbus-interfaces/org.gnome.Mutter.DisplayConfig.xml>).
The Rust implementation is original code for the current output inventory and
the supported subset of `ApplyMonitorsConfig`; it does not copy Mutter
implementation code. Mirroring, output disabling, and other unsupported
configuration properties return errors.

The `org.gnome.Shell` accelerator compatibility surface follows the client
interfaces in elementary/Wingpanel `lib/KeybindingHelper.vala` at
`e737de88bc02ddc82a9f4d23f574cc3c04098c03` and
elementary/wingpanel-indicator-sound `src/Services/ShellKeyGrabber.vala` at
`115d1495b754e2692c112fa5b02f9f3b5860a314`. These files are API references;
the Rust D-Bus service and accelerator matcher are original implementation.
