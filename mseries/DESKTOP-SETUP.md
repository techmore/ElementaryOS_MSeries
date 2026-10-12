# M1 Pro desktop setup

Hardware confirmed by the owner: elementary OS 9 Early Access boots to
Pantheon on a 2021 14-inch M1 Pro, kernel `7.1.13-3-2-ARCH`, ARM64.
This is a running transformed system; it does not establish that our factory
ISO builds or boots correctly.

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
The AppImage requires FUSE and supports automatic updates. Version observed:
8.31.0-beta.1, launched successfully on the live Wayland session.
Phone linking remains a user step.
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
backend, reads its same-user snapshot, and shows its configured providers and
remaining quota. Click the panel item for per-provider quota, Refresh, Open
CodexBar, and Settings/sign-in. Provider credentials remain managed by CodexBar.
Remove it with `bash mseries/install-codexbar-wingpanel.sh --uninstall`.
Source: https://github.com/steipete/CodexBar/tree/main/Integrations/Linux

## Camera notch and centered panel indicators

Pantheon places its date/time indicator in the center of Wingpanel and does not
avoid the MacBook camera notch. Keep `appledrm show_notch` disabled so the
desktop receives the rectangular 16:10 mode; enabling the full-height mode can
put the clock and other centered panel content behind the camera. The Apple
Silicon image no longer opts in. On this transformed install, pass
`appledrm.show_notch=0` on the custom elementary GRUB entry; the Asahi driver
loads from an Arch-named initramfs, so regenerating Ubuntu's conventional
`initrd.img-*` files does not change this boot entry.

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
