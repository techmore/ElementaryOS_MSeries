# Windows Work Mode

Windows Work Mode is an elementary OS System Settings panel for a Windows-inspired
work setup. Open **System Settings → Personal → Windows Work Mode** to turn it on,
choose one of five supplied wallpapers or another image, enable a weekday schedule
with local start and end times, or limit it to work networks identified by public IP. While active, it also shows the existing elementary
bottom dock without auto-hide. The patched dock uses a full-width taskbar with Start,
Search, weather and status controls; stock dock builds retain their floating layout.
Icon sizes follow the adopted size system's `work-taskbar` or `work` token, with
48/40-pixel defaults when it is unavailable. Pinned apps and native running-window
behavior stay in the dock. See the taskbar section below for its controls.
The usual wallpaper and dock preferences are snapshotted and restored when Windows
Work Mode turns off or the work window ends.

The included choices are Azure Bloom (the default), Blue Flow, Blue Ribbons, Violet Arc,
and Forest Flow. Azure Bloom is rendered from `work-mode-azure-bloom.svg` in this
directory (`rsvg-convert -w 3840 -h 2160`), original CC0 artwork for this project. The
other newer choices are original artwork generated for this project; none of
the bundled files are copied from Windows Spotlight or Microsoft themes. A custom
image can be selected through the file chooser.

## Rules

Windows Work Mode applies only while **every** rule you turned on is satisfied:
the main switch, the schedule (if on), and the work-network rule (if on). With
both schedule and network on, it means "during work hours, at work".

**Work network.** Turn on *Only on work networks* and list your workplace's
public addresses, comma-separated: single IPv4/IPv6 addresses or CIDR ranges
such as `203.0.113.0/28`. *Check* shows this computer's current public address and
*Add* lists it. The address comes from `https://api.ipify.org` (the
`public-ip-service` key), which is contacted only while this rule is on and the
other rules already pass. The answer is cached in
`~/.local/state/mseries/work-mode-public-ip.json` for 15 minutes per uplink; a
change of default route (Wi-Fi, Ethernet, dock, VPN) triggers a fresh check. If
a check fails, the last answer for the same uplink is reused for up to 30
minutes; otherwise the normal desktop stays.

```sh
~/.local/bin/mseries-work-mode --status      # current state, never contacts the service
~/.local/bin/mseries-work-mode --public-ip   # fresh lookup
```

The user systemd timer checks once per minute. It stores the current wallpaper
and dock preferences before the mode first applies them. If the elementary dock
was not already running, a dedicated user service starts it and stops it again
when the mode ends. GSettings stores the controls; original desktop state is
stored under `~/.local/state/mseries/`.

Install from this checkout with:

```sh
bash mseries/install-work-mode.sh
```

Remove the panel and timer with:

```sh
bash mseries/install-work-mode.sh --uninstall
```

The GSettings values and original state snapshot are retained on uninstall. The
bottom dock uses elementary's existing dock package and pinned launchers.

## Taskbar

With the M-Series dock build (`mseries/patches/dock-taskbar.patch`), Windows Work Mode turns the dock
into a full-width taskbar: weather at the left, a Start button and Search box beside the centred apps,
and status icons plus the clock at the right. Start opens a Windows 11-style Start menu. Right-click
Start for Lock, Log Out, Restart, Shut Down and System Settings. The top bar is hidden while the mode
is active, and windows cannot be placed behind the taskbar.

`icons/windows-work-mode-folder.svg` is an original Windows 11-style folder icon (CC0).

## Windows 11-style app icons

While active, Windows Work Mode can also switch the icon theme. Microsoft's own app icons are not
bundled. Instead, `mseries/install-work-mode-icons.sh` fetches the community
[Win11 icon theme](https://github.com/yeyushengfan258/Win11-icon-theme) by yeyushengfan258 (GPL-3.0,
credits Ubuntu's Yaru) at pinned commit `a5b460a407da143b32f19a503d7fcebb3edf2371`. Its app icons
imitate Microsoft's Windows 11 designs; this repository redistributes none of them. The script copies
only the icon folders (it never runs upstream's scripts) into `~/.local/share/icons/Win11` and
`Win11-dark`, which inherit `elementary` and then `hicolor`, so apps the theme does not draw keep
their usual icons. Each theme keeps upstream's `COPYING` and `AUTHORS`, plus `MSERIES-SOURCE` with the
source URL, commit and license. It also links `io.elementary.settings` and `io.elementary.photos` to the
theme's Settings and Photos icons.

```sh
bash mseries/install-work-mode-icons.sh                                # per user, no sudo
gsettings set io.elementary.mseries.work-mode icon-theme Win11-dark    # or Win11; '' = unchanged
bash mseries/install-work-mode-icons.sh --uninstall
```

The current `org.gnome.desktop.interface icon-theme` is snapshotted when the mode applies the theme
and restored when the mode ends or on `--restore`. If the named theme is not installed, the icon theme
is left alone.
