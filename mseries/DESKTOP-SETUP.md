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

## Touchpad gestures

Gala reads multitouch gestures from the Touchegg daemon, and logs "Error connecting
to Touchégg daemon" every 5 seconds at startup when it is missing. Touchegg is not
packaged for Ubuntu 26.04, so `bash mseries/install-touchegg.sh` builds upstream
2.0.18 and enables the system service. It deliberately removes Touchegg's own
`/etc/xdg/autostart/touchegg.desktop` client, since Gala handles the gestures and
the X11 client would act on the same swipes again. Gala only connects at startup,
so log out and back in afterwards. Pantheon's defaults apply: three-finger swipe up
opens multitasking, three-finger swipe left/right switches workspaces, and
four-finger gestures are unset (`io.elementary.desktop.wm.gestures`). Remove
everything with `bash mseries/install-touchegg.sh --uninstall`.

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
weekly remaining percentages. The dropdown uses Granite 7.7+ typography and
one padded card per provider, with separate five-hour and weekly limits,
remaining percentages, reset times, and estimated time left at the current pace.
Long provider lists scroll while the labeled Quick View, Usage Details,
Spending, and Settings & Sign In actions stay visible. The header refresh
button animates during updates, and the empty state offers a direct sign-in
action. Provider credentials remain managed by CodexBar. The
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

Touch ID is not enabled or verified on this M1 Pro. The earlier blanket
unsupported statement was too strong: [Omarchy M's September announcement](https://omarchy.org/news/2026/09/introducing-omarchy-m/)
reports Secure Enclave Touch ID work, and an experimental kernel was advertised
on September 29. Asahi's feature matrix still lists TouchID as TBA. A tested
M1 Pro kernel, firmware, enrollment service and PAM integration must be
identified before enabling fingerprint login. See [the optimization audit](OMARCHY-AUDIT-2026-10.md).
Issue [#8271](https://github.com/omacom/omarchy/issues/8271) concerns Intel T1
firmware/EFI, not this Apple Silicon machine.

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

The original stock-kernel diagnosis is superseded by the experimental
fairydust USB4 work. Dock USB2 peripherals and USB3 Ethernet were verified on
October 12; tunneled dock video remains unsupported. See
[fairydust USB4 status and recovery](fairydust/usb4/README.md) for the exact
hardware, kernel patches and rollback procedure. Plain DP Alt Mode and
Thunderbolt DP tunneling are separate paths.

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

## Log review and known issues (2026-10-12)

Checked after a reboot with no failed system or user units. Nothing below needs
action to keep the desktop working.

Resolved:
- **Cmd+Space launcher closed instantly:** each key press started it twice within
  milliseconds and the second start toggled it shut. Fixed by ignoring a second start
  within 400 ms. Apps it launched also inherited its `GDK_BACKEND=x11` and `GDK_SCALE`;
  it now restores the originals for them. `~/.cache/mseries-launcher.log` records opens,
  focus changes and quit reasons.
- **Shortcuts lost after a reboot:** `custom-keybindings` was found emptied while the
  per-shortcut entries survived. `mseries-launcher-keys` re-registers them at login.
- **No Files previews:** `tumblerd.service` failed with "Failed to create cgroup ...
  app.slice/tumblerd.service", and any new user service failed the same way, while
  scopes still worked. A reboot cleared it and the cause is unknown. If it returns, run
  `tumblerd` directly (`setsid nohup /usr/lib/aarch64-linux-gnu/tumbler-1/tumblerd &`)
  until the next login.
- **Touchegg missing:** see Touchpad gestures above.

Seen in logs, harmless:
- The login screen's `gala` and `wireplumber` (user 108) abort during teardown while the
  session is handed over. They do not affect the desktop session.
- `systemd-growfs: crypt_resize() of /dev/nvme0n1p5 failed: Operation not permitted` for
  `/` and `/home`; boot continues.
- `apple-dcp: Failed to get dp-xbar`, and Thunderbolt "USB3 tunnel creation failed" / "DP
  not active" (display and USB4 bring-up). Missing `rtl_nic/rtl8156b-2.fw` for a USB
  adapter. `org.gnome.Shell.Brightness` has no owner (Pantheon has no GNOME Shell).
- Wingpanel prints GTK layout and `g_str_has_prefix` assertions from the custom indicators.

Possible optimizations, not applied (each needs sudo and a decision):
- **Boot:** `cups-browsed.service` pulls `network-online.target` onto the critical chain,
  so `NetworkManager-wait-online` (about 3.1 s of the 6.1 s userspace time) delays
  `graphical.target`. Disabling `cups-browsed` should remove most of that wait.
  `snapd.*` adds roughly 3 s of parallel start-up work and is only needed for snaps.
- **Unused daemons enabled:** `ModemManager`, `avahi-daemon`, `cups`, `apport`, `snapd`.
- **No swap or zram** (30 GiB RAM, about 23 GiB available at the time). Adding zram would
  only matter under memory pressure.
- **CPU:** with the Claude and ChatGPT desktop apps open, load average sits near 3 on 10
  cores, and `gala` uses about 15% while they repaint. Not investigated further.


## OpenCode Desktop verification (2026-10-12)

The ARM64 `opencode` Debian package version 2.0.27 is already installed.
Its visible application entry is `/usr/share/applications/ai.opencode.desktop.desktop`,
launching `/opt/OpenCode/ai.opencode.desktop`. It was launched successfully
during the audit. The terminal command remains `~/.opencode/bin/opencode`.
GitHub's legacy latest release was 1.19.0 at audit time; do not downgrade the
installed desktop based solely on that endpoint.

## Local AI and performance tools

Coreglass and MLX Chat are now installed on the M1 Pro. MLX uses an isolated
Honeykrisp compute driver; the desktop Mesa package is unchanged. Start with
the Compact model pair. See [local AI setup and verification](local-ai/README.md).

## Rounded screen corners, softer accent colours

**Screen corners** (`bash mseries/install-gala-screen-corners.sh [--radius N]`): the M1 Pro's display has
rounded corners that the Linux desktop ignores. This builds Gala (pinned to the commit matching the
installed 8.6.2) with `mseries/patches/gala-screen-corners.patch`, which adds a click-through overlay that
draws black rounded masks over the four corners of the *built-in* display only (external monitors are
left square), above the top bar, dock, windows and lock screen. Default radius 10 logical px
(`GALA_SCREEN_CORNER_RADIUS` in the drop-in; 0 hides it).

Safety: the patched Gala lives in `/usr/local/lib/mseries/gala`; `/usr/bin/gala` and the login screen are
untouched. Only your user session is pointed at it (systemd drop-in under `~/.config`). The launcher falls
back to stock Gala by itself if the patched one dies within 15 s of starting, and then stays on stock until
`~/.cache/mseries-gala-failed` is deleted. It takes effect at the next login. Revert with `--disable`. If a
session ever will not start, switch to a text console (ctrl+alt+F3), log in and run
`rm ~/.config/systemd/user/io.elementary.gala@wayland.service.d/mseries-screen-corners.conf`.
Build notes: needs `libibus-1.0-dev libgnome-bg-4-dev` besides the mutter/gala/granite dev packages; Gala's
bundled `vapi/libmutter.vapi` maps `Monitor`/`LogicalMonitor` to `meta/main.h`, which does not declare them,
so the patch points them at `meta/meta-monitor.h` / `meta/meta-logical-monitor.h`.

**Colours and window radius** (`bash mseries/install-theme-tweaks.sh`): user stylesheets
(`mseries/theme/gtk-4.0.css`, `gtk-3.0.css`) override the theme's named colours `BLUEBERRY_*` and
`STRAWBERRY_*` (the accent, selection and error colours are derived from them) with softer tones, and raise the
window corner radius from 0.5rem to 0.8rem. `ghostty.config` sets a muted 16-colour palette. `--uninstall`
restores backups.

## System audit, 2026-10-12: findings and fixes

Findings from reading this boot's logs, `systemctl`, `ps`, `/proc/meminfo` and the kernel/initramfs build:

| Finding | Evidence | Fix |
| --- | --- | --- |
| Display crossbar never made it into the fairydust initramfs | `apple-dcp: Failed to get dp-xbar: -517` x70 per boot; display up ~2.6 s late; widened the greeter/display race | `install-initramfs-crossbar.sh`. Root cause: mkinitcpio ignores `/etc/mkinitcpio.conf.d/*.conf` when a config is given with `-c` or a preset's `ALL_config`; the fairydust presets set it, the stock one does not. That also means `zz_mseries_boot.conf` and Omarchy's drop-ins (incl. its HOOKS with plymouth) only ever applied to the stock kernel. |
| No swap | `free`: 0 B swap, 19 GB used, 11.6 GB shared (GPU buffers) | `install-system-tuning.sh`: zram swap (half of RAM, max 8 GiB, zstd), swappiness 100, page-cluster 0, zswap off |
| AppCenter background daemon | 682 MB resident | autostart override (`Hidden=true`); AppCenter itself still works |
| ModemManager running, duplicate snap CUPS | no modem; apt CUPS + snap CUPS both running | disabled ModemManager and snap cups |
| Wi-Fi resume recovery could never trigger or work | rejection filter used `journalctl -k` (wpa_supplicant logs are not kernel messages); `modprobe -r brcmfmac` failed with "Module brcmfmac is in use"; "connecting" counted as down so it restarted NetworkManager after every slow resume | rewritten in `mkosi.images/.../mseries-wifi-resume-fix`: acts only on recent status-16 rejections while Wi-Fi is not connected, stops NetworkManager/wpa_supplicant before reloading `brcmfmac_wcc`+`brcmfmac`, then restarts them |
| Build caches on the Arch side | 34 GB (compressed on disk: ~9 GB) | removed `usb4-pkg`, `fairydust`, `usb4`, `test`; built packages kept in `~/fairydust-usb4/pkgs/` |

Seen and left alone (noise, not defects here): Wingpanel's intermittent SEGV in `PanelWindow.on_realize`
(upstream race when the panel is respawned; Gala restarts it), repeated NM/`g_str_has_prefix` assertions from
Wingpanel indicators, the greeter's wireplumber abort, brcmfmac P2P-device `-52` errors, `systemd-growfs` failing
to resize the LUKS volume, USB `cannot reset (-71)` floods when a dock is pulled, and kernel taint `S`
(CPU out of spec) which is normal on Asahi. Revert the tuning with `install-system-tuning.sh --revert`.

The user GTK palette now uses muted slate blue (`#748fae`) and dusty rose
(`#bf9298`) for accents and error feedback. Error entry borders are softened too.
Restart apps to pick up the updated user stylesheets.

Spellcheck squiggles are drawn by each application or text engine; the GTK
palette does not override every spelling marker (including Chromium/Electron).
These colour tweaks keep spelling checks enabled.
