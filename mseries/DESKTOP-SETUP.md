# M1 Pro desktop setup

Hardware confirmed by the owner: elementary OS 9 Early Access boots to
Pantheon on a 2021 14-inch M1 Pro, kernel `7.1.13-3-2-ARCH`, ARM64.
This is a running transformed system; it does not establish that our factory
ISO builds or boots correctly.

## Command+Space launcher

`mseries/mseries-launcher.py` is a small dark, rounded GTK 4 search box that
filters installed apps as you type: Enter launches, Up/Down select, Esc or
clicking away closes, and pressing the shortcut again closes it. The setup
script installs it to `~/.local/bin/mseries-launcher` and binds `<Control>space`
(physical left Command, since Command is remapped to Ctrl) and `<Super>space`
(right Command) as custom shortcuts. It clears Pantheon's default Super+Space
input-source switch; Alt+Shift still switches layouts. Alt+F2 still opens
Slingshot. Gala cannot place Wayland windows, so the launcher runs through
XWayland and moves itself: centered horizontally, top edge 80% of the screen
height up from the bottom (`HEIGHT_FROM_BOTTOM` in the script).
The shortcuts are registered by `~/.local/libexec/mseries-launcher-keys`, which
starts at Pantheon login and re-adds them if `custom-keybindings` is ever emptied
(it was after one reboot, leaving the per-shortcut entries orphaned). Undo by
deleting `~/.config/autostart/mseries-launcher-keys.desktop`, stopping that helper,
and removing the two `mseries-launcher` entries from
`org.gnome.settings-daemon.plugins.media-keys custom-keybindings`.

## Command shortcuts and brightness

Run `python3 mseries/apply-desktop-settings.py` as the desktop user.
It preserves existing XKB options and adds `ctrl:swap_lwin_lctl`: left
Command becomes Ctrl (C/V/A/Z/S etc.), and physical left Ctrl becomes Super.
Right Command is unchanged. Remove that option from
`org.gnome.desktop.input-sources xkb-options` to undo the keyboard change.
The script also uses title-bar layout `close:minimize,maximize`, adding a
Minimize button beside Maximize. Restore `close:maximize` to undo this.
Apps drawing their own decorations may need to be reopened or may ignore it.

Physical Command+Shift+3 captures the full screen; Command+Shift+4 selects an
area. Existing Print shortcuts remain. Since Command is remapped to Ctrl,
the actual Gala bindings use `<Control><Shift>3` and `<Control><Shift>4`.
Gala hardcodes `Pictures/Screenshots`; the setup script links only that folder
to `Downloads/Screenshots`, preserving the rest of Pictures. Existing real
screenshot folders are preserved and require a manual migration. Captures
save automatically with native timestamped filenames and notifications.

GNOME settings daemon 50 expects GNOME Shell to handle screen brightness
keys. Pantheon has no GNOME Shell brightness implementation. The new
`mseries-brightness` user helper grabs `XF86MonBrightnessUp/Down` through
Gala's existing accelerator API and changes the internal `eDP-1` panel
through Mutter DisplayConfig `SetBacklight`, showing Gala's brightness OSD.
It reads the current backlight serial for each request and clamps to the
panel's minimum/maximum, in 5% steps. Requires `python3-gi`.

The user installer enables it on Pantheon login. Start immediately with
`~/.local/libexec/mseries-brightness`; set a one-time level with
`~/.local/libexec/mseries-brightness --set 60`. It never forces 60% at login.
Remove `~/.config/autostart/mseries-brightness.desktop` to disable it.
The arm64 image overlay also includes the helper and autostart entry.
Confirmed live: SetBacklight and OSD calls succeed; owner confirms brighter
display. Both accelerator registrations succeed. Physical key presses
and persistence across login still need user verification.

## Signal

Run `bash mseries/install-signal.sh`. Installs the official ARM64 beta,
checks its detached signature against fingerprint
`4B16B7232DFAA439AD791002EF9F501F13EED94C`, and adds a launcher.
The launcher enables Signal's tray mode: the window still opens normally, and
minimizing it leaves Signal running behind its Wingpanel icon. The icon shows
Signal's unread badge and activates the app when clicked. Install the optional
Wingpanel StatusNotifier host with `bash mseries/install-signal-wingpanel.sh`;
log out and back in to load the indicator. New message notifications continue
to use elementary's Notification Center. The AppImage requires FUSE and
supports automatic updates. Phone linking remains a user step: open Signal,
then scan its QR code from Signal on your phone.
Source: https://community.signalusers.org/t/beta-test-signal-desktop-for-linux-arm64/76184

## CodexBar

Upstream already ships a Linux Qt desktop and ARM64 CLI; a fork is unnecessary
for desktop windows. Install runtime packages on Ubuntu 26.04:

```sh
sudo apt install qml6-module-qtquick qml6-module-qtquick-controls \
  qml6-module-qtquick-layouts qml6-module-qtquick-templates \
  qml6-module-qtquick-window qml6-module-qtqml-workerscript \
  libqt6widgets6 libqt6svg6 qt6-wayland xdg-terminal-exec
bash mseries/install-codexbar.sh
~/.local/bin/codexbar-linux --settings
```

Installer pins v0.74.1 and verifies both published SHA256 checksums before
extraction. Provider authentication stays with the provider CLIs. Pantheon
may not expose a StatusNotifier tray host; desktop launcher/windows work
without one. For a native Wingpanel item that displays remaining quota and
opens a dropdown, install the separate Pantheon indicator:

```sh
sudo apt install meson ninja-build valac libwingpanel-9-dev libgranite-7-dev libjson-glib-dev
bash mseries/install-codexbar-wingpanel.sh
```

Log out and back in after installation. The indicator starts CodexBar's local
backend and reads its same-user structured snapshot without changing CodexBar
preferences. The panel shows the OpenAI mark with both Codex's five-hour and
weekly remaining percentages. The dropdown groups quota windows into compact
cards, shows the reset time, and highlights the provider's estimated time left
at its current pace, plus Refresh, Quick View, Usage & Spend, Spending, and
Settings/sign-in actions. Provider credentials remain managed by CodexBar. The
monochrome mark comes from the [OpenAI 2025 symbol](https://commons.wikimedia.org/wiki/File:OpenAI_logo_2025_(symbol).svg)
and follows OpenAI's branding guidelines.
Remove it with `bash mseries/install-codexbar-wingpanel.sh --uninstall`.
Source: https://github.com/steipete/CodexBar/tree/main/Integrations/Linux

## Signal Beta in Wingpanel

The Signal launcher uses its supported `--use-tray-icon` option. Install the
GTK 4 Wingpanel host with `bash mseries/install-signal-wingpanel.sh`, then log
out and back in. The host displays Signal's unread-count icon (including a
bundled official icon when Signal's StatusNotifier metadata is incomplete) and
a Wingpanel menu with an **Open Signal** action. The action launches the local
Signal Beta build, or falls back to the Flatpak installation. Signal does not
expose an independent Wingpanel login flow, so linking or relinking opens
Signal's QR screen and must be
approved from the primary phone.

## Touch ID on M1 Pro

Touch ID is not currently supported on this M1 Pro under Asahi Linux, so it
cannot be enabled by the elementary or Omarchy desktop setup. Asahi lists
TouchID as TBA for M1 Pro/Max/Ultra devices. Omarchy issue
[#8271](https://github.com/omacom/omarchy/issues/8271) describes a separate
Apple T1 firmware/EFI risk on Intel Touch Bar MacBook Pros, not the M1 Pro.
Source: https://github.com/AsahiLinux/docs/blob/main/docs/platform/feature-support/m1.md

## Camera notch and centered panel indicators

Pantheon places its date/time indicator in the center of Wingpanel and does not
avoid the MacBook camera notch. Keep `appledrm show_notch` disabled so the
desktop receives the rectangular 16:10 mode; enabling the full-height mode can
put the clock and other centered panel content behind the camera. The Apple
Silicon image no longer opts in. On this transformed install, pass
`appledrm.show_notch=0` on the custom elementary GRUB entry; the Asahi driver
loads from an Arch-named initramfs, so regenerating Ubuntu's conventional
`initrd.img-*` files does not change this boot entry.

If the centered date/time remains hidden, install a temporary right-side
replacement with `bash mseries/install-clockright-wingpanel.sh`. It follows
Wingpanel's weekday, date, 12/24-hour, and seconds preferences. To place it
after Alerts and before Quick Settings, run
`bash mseries/install-wingpanel-clock-position.sh`. This rebuilds the matching
Wingpanel 8.0.4 revision and saves the original panel executable for rollback
with `bash mseries/install-wingpanel-clock-position.sh --uninstall`. Log out
and back in to load the indicator and ordering.

## Boot and login timing

- **Login stall (fixed):** the Files file-chooser portal and `xdg-desktop-portal`
  waited on each other for the 25 second D-Bus timeout. Install the fix with
  `bash mseries/install-files-portal-fix.sh` (undo with `--uninstall`).
- **Kernel phase, about 10 seconds:** `apple-dcp` defers probing because
  `mux-apple-display-crossbar` (its `dp-xbar`) is not in the initramfs, so the
  kernel waits out its 10 second deferred-probe timeout.
- **Disk-encryption passphrase screen:** the roughly 24 second gap before the
  root filesystem mounts is the LUKS passphrase prompt. Both systems boot the
  Arch (Omarchy) kernel and initramfs, so it shows the Omarchy Plymouth theme.
  The disk stays encrypted; auto-unlock would need a key stored on `/boot`.

Run `bash mseries/install-elementary-boot-splash.sh` to add the missing module
(`mseries/boot/zz_mseries_boot.conf`) and switch the passphrase screen to the
elementary Plymouth theme. It backs up the current initramfs images as
`*.pre-mseries`, rebuilds them in the Arch root at `/mnt/fdbuild/root`, and
`--uninstall` restores the Omarchy theme and the backups. Reboot afterwards and
check `dmesg` no longer shows `Failed to get dp-xbar`.

## Dock diagnosis

Charging is detected, but the attached USB-C dock's mouse does not enumerate.
Kernel log: `ATCPHY_PIPEHANDLER_STATE_USB4 not implemented; falling back to USB2`.
Only an ASIX USB Ethernet adapter and root hubs were visible. DRM exposes
internal `eDP-1` (connected) and built-in `HDMI-A-1` (disconnected), no USB-C
display connector. This points to USB4/Thunderbolt dock compatibility rather
than a mouse preference. Test a plain USB hub/adapter and built-in HDMI.
Do not assume a desktop settings change can enable unsupported USB4 hardware.

## OpenCode

Located at `~/.opencode/bin/opencode`; executable is native ARM64.
Log shows its working directory was `/home/admin`, and update checks returned
HTTP 500 and timed out. Available RAM was about 23 GiB of 30 GiB; no evidence
of memory pressure. These observations do not establish why model responses
are slow. Launch from this checkout to keep project discovery scoped:
`cd ~/Documents/ElementaryOS_MSeries && opencode`.
No OpenCode settings or running sessions were changed.

## Network speed in the panel dropdown

`bash mseries/install-network-throughput.sh` adds a live download/upload readout and a
60-second graph (down in the accent colour, up in grey) to the network indicator's dropdown,
directly under the connection toggles (Airplane Mode etc.). It builds `elementary/panel-network` at the commit that matches the
installed `io.elementary.panel.network` 8.0.1 with `mseries/patches/network-throughput.patch`
and replaces only `libnetwork.so`; the original is saved at
`/usr/local/lib/mseries/libnetwork.so.original`. Build needs `libnm-dev libnma-gtk4-dev
libpolkit-gobject-1-dev` besides the Wingpanel/Granite/GTK dev packages the other installers use.
Gala respawns the panel, so there is no logout. `--uninstall` restores the original.

Speeds are the sum over physical interfaces from `/proc/net/dev` (virtual ones such as `lo`,
bridges and VPN tunnels are skipped to avoid double counting), sampled once a second, so the graph
is already filled when you open the menu. Re-run the script after a package upgrade of the network
indicator, which overwrites the plugin.
