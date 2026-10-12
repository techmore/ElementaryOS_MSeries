# Ambient keyboard lighting

Install on the elementary desktop:

```sh
bash mseries/install-keyboard-backlight.sh
```

Polls the Apple AOP ambient sensor every five seconds and adjusts only the
keyboard LED through UPower. Uses the standard system D-Bus API, without root,
custom sysfs permissions, or Hyprland dependencies. Inspired by
`omacom/omarchy-mac` quattro's `omarchy-brightness-keyboard-auto` at
`ba546a61f881c1fe9d79d75ec050eab048b8cb63`; this is a Pantheon implementation.

Dark rooms (8 lux or below) select full keyboard lighting; bright rooms
(180 lux or above) select zero, with a linear transition. A four-percent
deadband avoids small brightness changes. Manual changes pause automation
until ambient light changes by at least 20 lux or 40 percent of the value
at the time of the override, whichever is greater. No display brightness changes.

Manual controls:

```sh
~/.local/libexec/mseries-keyboard-backlight --step down
~/.local/libexec/mseries-keyboard-backlight --step up
```

Logind gates automatic writes to an active, unlocked graphical session.
An exposed closed-lid ACPI state also suppresses writes. Locking does not
force the light off; it leaves the current value alone. Sensor/API failures
leave lighting untouched and are logged in `journalctl --user -u mseries-keyboard-backlight.service`.
Autostart resumes the helper at login. Disable with:

```sh
bash mseries/install-keyboard-backlight.sh --uninstall
```

Hardware verification on 2026-10-12: M1 Pro / j314s, ambient reading 141 lx,
UPower adjusted the keyboard from 0 to 59/255; the first subsequent poll remained at 59 with no logged errors.
The background helper runs as a user systemd service started by desktop autostart. Physical appearance, lock/lid
transitions and suspend/resume still need interactive qualification.

Run sensor regression checks with:

```sh
/usr/bin/python3 -m unittest discover -s mseries/keyboard-backlight -v
```
