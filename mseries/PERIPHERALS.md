# Apple and Logitech keyboards, trackpads and mice

`mseries-peripherals` (source `mseries/hardware/peripherals.py`, installed by `install-hardware-support.sh`) shows
every Bluetooth or cabled input accessory with one battery reading and handles the plug-in moment.

```
mseries-peripherals status [--json]   link, trust, charge for every accessory
mseries-peripherals pair [ADDRESS]    pair + trust + connect (add --replace to drop a stale bond first)
mseries-peripherals watch             the user service (graphical-session.target)
```

## What it does

- **Charge you can trust.** The MX Vertical's HID++ driver reports only "Normal", which UPower shows as 55%. BlueZ has the real
  number from the mouse's GATT battery service (100%). `status` takes an exact kernel percent first, then BlueZ's, and falls
  back to a level word. Charging state comes from the kernel supply, which Apple's Magic devices fill in over the cable.
- **Plug-in.** A Magic Keyboard, Trackpad or Mouse (or a Logitech mouse/keyboard) on USB is matched to the one paired device of
  the same vendor and kind. If it is paired, the watcher trusts it, shows "plugged in" with the charge, and connects it again
  on unplug if it stayed off. If nothing is paired, the notification offers **Pair**; one click runs `pair` for that kind.
  Two paired keyboards make the cable ambiguous, so it only reports charge.
- **Low battery.** One notice at 15% on a connected or cabled device that is not charging; re-armed after charging or 30%.
- **Why pairing is a click and not automatic.** A keyboard pairs with no PIN, so trusting whatever is advertising would let
  a rogue device in range type for you. `pair` without an address also refuses to guess: it needs exactly one unpaired
  Apple/Logitech accessory of the right kind with a live signal. We have not found a way to read an Apple accessory's
  Bluetooth address over its cable, so the cable cannot name the device to pair; macOS does this with a private protocol.
- **Wake and reconnect.** Paired, trusted devices reconnect through BlueZ as before; the existing Broadcom resume recovery
  (`--enable-bluetooth`) still covers suspend.

## Kernel

All of it is already in the Aurora 7.2 kernel configuration: `BT_HIDP`, `UHID`, `HID_BATTERY_STRENGTH`, `HID_APPLE`,
`HID_MAGICMOUSE` (Magic Mouse 2, Trackpad 2 and their USB-C versions, over USB and Bluetooth), `HID_LOGITECH_HIDPP`,
`HID_LOGITECH_DJ`. `python3 mseries/check-kernel-config.py CONFIG --peripherals` fails a build that drops one.
Both preserved configs and the running 7.2.11-elementary-aurora72-wip3 pass it.

## Status

- **Verified:** on the running M1 Pro with the paired MX Vertical, `status` reads 100% where UPower says 55%; the watcher
  starts, records state and stays quiet; 25 offline tests cover battery choice, cable matching, plug/unplug plans, low-battery
  re-arming and pairing (`python3 -m unittest discover -s mseries/hardware -p 'test_*.py'`).
- **Not verified:** any Apple accessory. No Magic Keyboard, Trackpad or Mouse was available: cable charge reporting, the
  plug-in matching, the notification **Pair** action (needs a notification server that supports actions) and pairing a Magic
  device through `bluetoothctl` are tested only against fixtures. Reconnect after unplug, behaviour across suspend, and the
  MX Vertical over its USB-C cable are also unchecked.
- UPower's own 55% entry for the MX Vertical is unchanged; the power indicator may still show it.
