# M1 Pro desktop setup

Hardware confirmed by the owner: elementary OS 9 Early Access boots to
Pantheon on a 2021 14-inch M1 Pro, kernel
`7.1.13-1-2-fairydust-usb4-ARCH`, ARM64.
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

## Tether: iPhone messages and OTP handoff

Install the optional, pinned ARM64 upstream package with
`bash mseries/install-tether.sh`. It pairs the iPhone directly to this laptop;
it does not need a relay Mac. Launch the app and approve pairing on both
devices. The package install does not enable a daemon or change Bluetooth or
firewall settings.

The current host has BlueZ 5.85; upstream Tether needs 5.86+ with the
experimental bearer API for SMS/iMessage over Bluetooth. The app can be
installed, but the message transport is not ready on this host. Do not try to
solve that by enabling experimental mode on BlueZ 5.85. Wi-Fi pairing and OTP
handoff are independent, but require TCP 5134 and mDNS UDP 5353 to reach the
laptop; configure firewall access only if you choose to use that path.

Optional Brave setup is in [`tether/README.md`](tether/README.md). It requires
loading an unpacked extension and registering its native host. The extension
requests access to all websites, so review that permission before enabling it.
No Brave extension is installed automatically. Remove the app with
`bash mseries/install-tether.sh --uninstall`; pairing state is preserved unless
you separately run `--purge-data`. That removes Tether's XDG files, not the
Bluetooth bond stored by BlueZ; forget the laptop from both devices to fully
unpair.

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
backend and reads its same-user structured snapshot every five seconds without
blocking Wingpanel. Opening the dropdown requests fresh usage when the cached
provider data is at least 30 seconds old; these requests are limited to one per
minute and skipped while a fetch is running. Manual refresh remains available.
The indicator preserves CodexBar preferences. For one-minute background usage
polling and refresh-on-open in CodexBar's own windows, configure the running app:

```sh
~/.local/bin/codexbar-linux --configure '{"refreshSeconds":60,"refreshOnOpen":true}'
```

The panel shows each provider's session quota remaining and the earliest
available quota ETA, labeled with its limiting window (for example,
`CX 87% · 7D ~1d7h`). An exhausted limit shows its reset countdown instead.
The dropdown keeps both session and weekly percentages, reset times, and a
visible forecast below each limit. Hover the bar for the limiting quota's detail.
Forecasts reuse CodexBar's reported usage pace and describe quota availability,
not an exact remaining token balance. Missing/unrecognized pace data, provider
errors, usage older than three minutes, and expired reset boundaries suppress
the forecast. A safe window does not imply another unmeasured limit is safe. Provider credentials remain managed by
CodexBar. The
monochrome mark comes from the [OpenAI 2025 symbol](https://commons.wikimedia.org/wiki/File:OpenAI_logo_2025_(symbol).svg)
and follows OpenAI's branding guidelines.
Remove it with `bash mseries/install-codexbar-wingpanel.sh --uninstall`.
Source: https://github.com/steipete/CodexBar/tree/main/Integrations/Linux

The CodexBar installer enables OpenAI Codex and OpenCode Go together on a
fresh install. If the existing provider is Codex, Codex+Claude, or a custom
list, it adds OpenCode Go while preserving the other CodexBar preferences.
Other explicit single-provider selections are left alone; switch to **custom** and add
`opencodego` in Settings → Providers to include it.

OpenCode Go is separate from the base OpenCode web-dashboard provider. To
connect it, open CodexBar → Settings → Providers, select OpenCode Go, and enter
your OpenCode Go API key in its **API key** field. The Wingpanel entry
then shows its reported quota. A device with only local OpenCode Go history can
show estimated local usage; that estimate is not account quota. Credentials are
stored by CodexBar per user and are not placed in the OS image or installer.

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

Historical log observations (not a declaration that every warning is harmless):
- The login screen's `gala` and `wireplumber` (user 108) abort during teardown while the
  session is handed over. They do not affect the desktop session.
- `systemd-growfs: crypt_resize() of /dev/nvme0n1p5 failed: Operation not permitted` for
  `/` and `/home`; boot continues.
- `apple-dcp: Failed to get dp-xbar`, and Thunderbolt "USB3 tunnel creation failed" / "DP
  not active" (display and USB4 bring-up). Missing `rtl_nic/rtl8156b-2.fw` for a USB
  adapter. The missing `org.gnome.Shell.Brightness` provider is addressed by the
  2026-10-12 compatibility bridge described below.
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
| Wi-Fi resume recovery could not unload the driver | `modprobe -r brcmfmac` failed with "Module brcmfmac is in use": brcmfmac is held by its vendor module (`brcmfmac_wcc`, refcount 1), not by NetworkManager. The rejection counter also read `journalctl -k`, which never contains wpa_supplicant lines | `mseries-wifi-resume-fix` now uses `modprobe -r --remove-holders` and loads the holders back, and reads rejections from the wpa_supplicant/NetworkManager units. The policy (airplane mode respected, Ethernet does not hide a down Wi-Fi, abort on failed unload) is unchanged and covered by `mseries/test-wifi-resume.py`. |
| Build caches on the Arch side | 34 GB (compressed on disk: ~9 GB) | removed `usb4-pkg`, `fairydust`, `usb4`, `test`; built packages kept in `~/fairydust-usb4/pkgs/` |

Historical issues left outside the system-tuning change: Wingpanel's intermittent SEGV in `PanelWindow.on_realize`
(upstream race when the panel is respawned; Gala restarts it), Wingpanel indicator assertions (see the subsequent log audit below), the greeter's wireplumber abort, brcmfmac P2P-device `-52` errors, `systemd-growfs` failing
to resize the LUKS volume, USB `cannot reset (-71)` floods when a dock is pulled, and kernel taint `S`
(CPU out of spec) which is normal on Asahi. Revert the tuning with `install-system-tuning.sh --revert`.

The user GTK palette now uses muted slate blue (`#748fae`) and dusty rose
(`#bf9298`) for accents and error feedback. Error entry borders are softened too.
Restart apps to pick up the updated user stylesheets.

Spellcheck squiggles are drawn by each application or text engine; the GTK
palette does not override every spelling marker (including Chromium/Electron).
These colour tweaks keep spelling checks enabled.


### Desktop log repair — 2026-10-12

Installed and verified on the M1 Pro session:

- Added a Pantheon provider for GNOME 50's `org.gnome.Shell.Brightness` API,
  backed by Mutter's real backlight API. This resolves repeated power daemon
  dimming failures. Manual changes during dimming are preserved. First install
  saves the ambient-brightness preference and disables automatic brightness;
  subsequent installs preserve the current choice. Uninstall restores the saved
  preference. Existing brightness keys remain in use.
- Fixed the keyboard indicator's binding to a removed `active` property on
  `Wingpanel.PopoverMenuItem`. Selection now uses GTK's checked state.
- Fixed the network indicator passing its device-less VPN row into libnm's
  device-name disambiguation. Existing throughput enhancements remain included.
- Repaired Signal Beta's lowercase Electron desktop identity and installed its
  own bundled icon. Hidden aliases let the dock resolve the app without adding
  duplicate visible launchers. The running Signal session was preserved.
- Corrected the misplaced `StandardError` directive in the installed SPICE user
  unit through a user override. Regenerate this override after vendor updates.
- Cleared the stale failure of the already-disabled duplicate snap CUPS browser
  only when its recorded exit status was 143 from intentional termination.
  Native CUPS remains active.

Reproduce the session integration with `bash mseries/install-log-fixes.sh`.
Build the keyboard patch with `bash mseries/install-keyboard-indicator-fix.sh`
and the network patch with `bash mseries/install-network-throughput.sh`.
These indicator builds require the development packages used by the existing
Wingpanel builds and network access to their pinned upstream sources. Reload
Wingpanel after replacing plugins. The keyboard installer accepts `--uninstall`
to restore its original library; the brightness installer also accepts
`--uninstall`. Signal's original launcher is backed up under
`~/.local/state/mseries-signal/desktop-before-integration`.

Validation: five brightness behavior tests passed; shell syntax and diff checks
passed; both native indicator libraries compiled and loaded. After a fresh panel
reload, the removed-property warning and nine libnm device assertions were gone,
and the panel remained running. Both system and user failed-unit lists were
empty. The latest five-minute warning check was empty before the panel reload.

At the end of the initial audit (subsequently fixed below): a fresh panel still reports six
`g_str_has_prefix` null-string assertions and one `Granite.Symbol` undefined-state
warning. An isolated notifications-plugin probe reproduced null-string warnings,
but their precise origin has not been established. An isolated Bluetooth probe
also crashed outside the desktop host; that diagnostic crash does not establish
that the live Bluetooth indicator crashes. No logging was suppressed. Historical
dock/kernel and greeter teardown messages remain outside these verified fixes;
no kernel upgrade or unsafe speaker changes were made.

### Gear-menu screen brightness

`bash mseries/install-quick-settings-brightness.sh` builds elementary Quick
Settings 1.4.0 at pinned revision `fb721d4b5640a2a25ae011370c8fe8aaff8d93f4`
with a native GTK brightness slider immediately beneath the toggle grid containing
Onscreen Keyboard, above text scaling. It shows the current percentage and uses
Mutter's internal-display backlight range, including its hardware minimum.
Updates are asynchronous and coalesced while dragging; external brightness-key
changes refresh the slider. No slider is shown when no active internal backlight
exists, or in the greeter.

Build dependencies include `libaccountsservice-dev`, `libpackagekit-glib2-dev`,
`libportal-dev`, `libadwaita-1-dev`, `libwayland-dev`, and the existing GTK,
Granite, Wingpanel, Meson and Vala development tools. The installer replaces only
`libquick-settings.so`, saves the stock plugin under `/usr/local/lib/mseries/`,
and accepts `--uninstall` to restore it. Reload Wingpanel after installation or
restoration. Distribution package updates may require reinstalling the patch.

Validation: native plugin compiled; widget initialized from the live display at
62.6%; moving it one percentage point changed the real backlight from 315 to
320, and a finally block restored 315. The panel reloaded and remained running.
Visual appearance has not been checked through a screenshot.


### Sound indicator startup warning follow-up

The remaining seven panel startup warnings were isolated to the sound indicator,
not the notifications plugin. A Wayland plugin probe and GLib log-handler stack
trace identified two causes: `DisplayWidget.volume_state` was initially null when
its binding synchronized, and GTK 4.22.4's `shape_apply_state()` called
`g_str_has_prefix()` on unnamed SVG animation IDs during initial state changes.

`bash mseries/install-sound-indicator-fix.sh` builds official sound indicator
8.0.3 at `8b7991c9156ac8127d27559506baea8e6fb72e5b`. The patch gives the volume
state a valid initial value and assigns unique IDs to the existing animations.
It preserves the artwork, state changes, animations and all audio routing;
no speaker output or volume settings are enabled. Build dependencies additionally
include `libpulse-dev`, `libnotify-dev` and `libcanberra-dev`. The stock library
is backed up under `/usr/local/lib/mseries/`; `--uninstall` restores it, followed
by a panel reload. GTK source reference:
https://github.com/GNOME/gtk/blob/4.22.4/gtk/gtksvg.c (shape_apply_state).

Validation of the follow-up: the patched sound indicator's isolated Wayland
startup produced no warnings. After installation, a normal Gala-respawned panel
(PID 162249 in this session) had no warning-level journal entries. The earlier
seven warnings belonged to the old process, not the fresh panel. No diagnostic
preload library or log handler is installed persistently. One temporary panel
probe initially selected X11 and crashed because Wingpanel requires Wayland;
the normal panel recovered, and subsequent probes explicitly used Wayland.
The gear menu was opened through its native toggle action after activation.

### Keyboard brightness in the gear menu

The Quick Settings patch also adds a separately labeled **Keyboard Brightness**
slider immediately above screen brightness, below the toggle grid. It uses
UPower's `org.freedesktop.UPower.KbdBacklight` system-bus API, reads the actual
hardware maximum, supports fully off, and follows `BrightnessChanged` signals.
It does not write screen brightness. Writes are asynchronous and coalesced while
dragging. The existing ambient keyboard-light helper remains enabled; its
manual-change detection pauses automatic adjustments until ambient light changes
substantially.

Reinstall with `bash mseries/install-quick-settings-brightness.sh` and reload
Wingpanel. Validation on the M1 Pro: the widget initialized at 98% (250/255),
a one-percent slider decrease changed the keyboard backlight to 247, and the
test restored the original value of 250. The native plugin rebuilt successfully.

## Pending-checks list (mseries-verify)

Fixes that can only be verified later (after a reboot or login, or when the dock is plugged in) are tracked by
`mseries-verify`, which lives next to the troubleshooting robot and keeps its history in SQLite
(`~/.local/state/mseries-troubleshooter/verify.db`, plus `verify-status.json` for panels/UIs). Install with
`bash mseries/local-ai/install-verify.sh`; a user timer runs it 90 s after login and every 10 minutes.

* Each check has a **precondition** (e.g. "booted after the initramfs was rebuilt", "dock present for 2 min") and
  a read-only **command** (exit 0 = pass). Until the precondition holds the check is `waiting`.
* Visual items are `manual`: it notifies once and asks; answer with the **Looks good / Problem** buttons in the
  Local Troubleshooter window ("Checks still open") or `mseries-verify confirm ID yes|no [note]`.
* A desktop notification is sent only when a check changes state (passed / failed / needs you).
* `mseries-verify status`, `history [ID]`, `run --notify`, `recheck ID`, `reload` (re-reads
  `mseries/local-ai/verify-checks.json`; recorded results are kept). Add new "check this later" items there.
* Commands come only from that seed file, never from a model. Tests: `python3 -I mseries/local-ai/test_verify.py`.

### Second sweep (same day): kernel/journal and the repo itself

* **Speaker amplifier faults, speakersafetyd missing.** `tas2764 1-0039: fault: over current` three times (~30-60 min
  apart, constant context bytes `02,19,00,00,00`) plus bursts of `bad TDM clock`. The kernel's "Speaker Volume Unlock"
  was locked and the sink volume 0, so nothing unsafe was being driven, but the elementary root had none of the Apple
  audio stack the Arch root runs. **Result:** `speakersafetyd` 1.1.2 installed and running (its `j314.conf` is
  byte-identical to Arch's 2.0.1; per-woofer limits loaded). The DSP chain (`asahi-audio` + `alsa-ucm-conf-asahi`) was
  tried and **reverted**: it needs PipeWire's LV2 filter plugin, which Ubuntu's PipeWire 1.6.2 lacks (Arch's 1.6.9 has
  `libspa-filter-graph-plugin-lv2.so`), so `spa.filter-graph: can't load plugin type 'lv2'` and the speaker sink
  vanished, leaving only a headphone sink at 100%. Audio was restored (Built-in Audio Stereo, muted) and
  `install-audio-stack.sh --with-dsp` now refuses until that plugin exists. Retry when Ubuntu's PipeWire ships it
  (or consider building the plugin from the matching PipeWire source). Tracked by the `amp-overcurrent` check.
* **Wingpanel SEGV (3 today).** Identical stack each time: `PanelWindow.on_realize` -> `wl_proxy_get_version`, a
  Wayland proxy invalid during a panel (re)spawn. Gala respawns the panel, which is the recovery; a null check would
  leave an unanchored panel running, so it is deliberately left alone. Report upstream.
* **Orca started and died at 18:12.** Shortcut `<Alt><Super>s`; with Command/Control swapped it is physical
  Control+Option+S. Orca then fails with an XKB `BadValue` under Xwayland. Shortcut removed
  (`gsettings set org.gnome.settings-daemon.plugins.media-keys screenreader "[]"`; `gsettings reset` restores it).
* **Repo lint:** `shellcheck` over 58 scripts: 0 errors; 13 warnings (mostly `ls | grep` style; `SC2114` is upstream
  elementary's intentional `/usr/local` replacement in the image). Fixed: `build-m1n1.sh` ignored its pinned SHA.
* **CI gap:** only the wifi test ran. CI now runs every Python test file. `test_bridge.py` had no runner.
* **A mistake worth recording:** the first Wi-Fi rewrite overwrote newer tested logic and broke two CI tests;
  restored in `2bcd925`. Re-read a file immediately before replacing part of it, and run the repo's tests before pushing.

### Third finding (same day): USB-C devices are lost across suspend

Evidence (`journalctl -k`): suspend entry `17:34:06 (s2idle)`, exit `18:00:30`, then
`xhci-hcd.3.auto: xHC error in resume, USBSTS 0x401, Reinit` / `root hub lost power or was reset` /
`usb 2-1: USB disconnect` (the ASIX Ethernet adapter). Nothing re-enumerated it until the controller was re-probed
16 minutes later. USBSTS 0x401 = halted + Save/Restore Error: the controller state was lost with its power domain.

Cause (source): `drivers/phy/apple/atc.c` and `drivers/usb/dwc3/dwc3-apple.c` define no `dev_pm_ops`; `tipd_resume()`
only re-enables the IRQ / reset line. The Type-C controller sees no event for an unchanged partner, so the PHY lane
mode, pipehandler and dwc3 wrapper setup are never re-applied after the power domain comes back.

Do not work around it from userspace by unbinding drivers: unbinding `dwc3-apple` (or its device-link supplier
`tps6598x`) oopses in `dwc3_apple_remove`. A real fix means: PHY suspend/resume that re-runs
`atcphy_configure()` for the saved mode, a dwc3-apple resume that redoes its wrapper init, and a `tipd_resume` that
re-asserts the current mux state; tested with real suspend/resume cycles (needs someone at the keyboard to wake it).
Tracked by `usb-c-survives-suspend` in mseries-verify. Workaround: replug after resume, or avoid suspend while docked.

### Reboot went to macOS: the default startup volume

Which system boots is chosen by the Mac's firmware (NVRAM `boot-volume`), not by GRUB. On 2026-10-12 it pointed at
**Macintosh HD**, so every restart or power-on booted macOS unless Linux was picked by hand in the boot picker
(hold the power button). Fixed with the official tools (`apt install asahi-bless asahi-nvram`):

    sudo asahi-bless --list-volumes                                   # *1) Macintosh HD   2) Asahi Alarm Minimal (BTRFS)
    sudo asahi-bless --set-boot "Asahi Alarm Minimal (BTRFS)" -y      # make Linux the default
    sudo asahi-bless --get-boot                                       # verify (and --get-boot --next for a one-time override)
    sudo asahi-bless --set-boot-macos -y                              # undo: macOS as default again

Things that put it back to macOS: a macOS update, choosing a startup disk inside macOS (System Settings > Startup
Disk), or `--set-boot` with the macOS name. If a reboot lands in macOS again, re-run the `--set-boot` line above.
`asahi-bless` needs root to read NVRAM, so the checklist robot (a user service) cannot verify this on its own.

## Network speed in the menu bar (2026-10-12)

The network dropdown has a **Show speed in menu bar** switch under the speed graph. When on, `↓ rate ↑ rate`
appears beside the network icon, averaged over 10 s (the timer stops when the switch is off). The choice is
stored in `~/.config/mseries/network-speed.ini`. Built by `install-network-throughput.sh` from
`patches/network-panel-speed.patch`.

Colours: libadwaita apps ignore elementary's `@BLUEBERRY_*` names and read `accent_bg_color` and friends, which
`theme/gtk-4.0.css` now sets too. Screen-corner radius raised from 10 to 14 (log out/in to apply; change
`GALA_SCREEN_CORNER_RADIUS` in the Gala drop-in).

## Power and browser (2026-10-12)

- `install-power.sh` installs `mseries-power`: battery charge limit 80% (resume at 75%; battery health was 91% at
  89 cycles), and on battery the power-saver profile plus a performance-core ceiling (3036 MHz → 2208 MHz). A udev
  rule on the charger re-applies it. `sudo mseries-power limit 100` lifts the cap; `mseries-power status` shows state.
  Note power-profiles-daemon here only has a *placeholder* driver, so the profile name itself changes nothing; the
  CPU ceiling is what saves power.
- `install-native-firefox.sh` replaces Ubuntu's snap shim with Mozilla's arm64 apt package (key fingerprint checked,
  repository pinned). Headless start 0.56 s warm, about the same as the snap Chromium (0.53 s warm); an earlier "2.6 s" snap figure was a first-run penalty, so the benefit is "no snap", not speed.
- Not possible: running macOS 27 in a VM here, see the answer in chat / `mseries/MACOS-VM.md`.

## Speaker tuning (2026-10-13)

`install-pipewire-lv2.sh` builds PipeWire's LV2 filter plugin (Ubuntu omits it), then
`install-audio-stack.sh --with-dsp` installs asahi-audio 3.4 and its LV2 plugins. The speaker sink becomes
"MacBook Pro J314 Speakers" (listed under Filters in `wpctl status`). Lesson: the first attempt left that sink at
70% because the restore code only looked at the Sinks list; it is fixed, and all sinks were muted at 0 within a
minute. Raise the volume slowly. Revert: `bash mseries/install-audio-stack.sh --revert`.
