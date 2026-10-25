#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read active Mutter/Gala modes and VRR selection without changing settings."""
import json
import math


def read_active():
    result = {
        "available": False,
        "modes_available": False,
        "layout_available": False,
        "power_save_mode_available": False,
        "monitors": [],
        "layout": [],
        "power_save_mode": None,
    }
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        dest, path, interface = "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig", "org.gnome.Mutter.DisplayConfig"
        state = bus.call_sync(dest, path, interface, "GetCurrentState", None, None, Gio.DBusCallFlags.NONE, 1500, None).unpack()
        monitors = []
        for spec, modes, properties in state[1]:
            for mode, width, height, refresh, preferred, scales, options in modes:
                if options.get("is-current"):
                    monitors.append({"connector": spec[0], "mode": mode, "width": width, "height": height,
                                     "refresh_hz": refresh, "refresh_mode": options.get("refresh-rate-mode", "fixed"),
                                     "vrr_available": any(m[-1].get("refresh-rate-mode") == "variable" for m in modes)})
        if not monitors or any(not math.isfinite(m["refresh_hz"]) or m["refresh_hz"] <= 0 for m in monitors):
            result["reason"] = "active mode/refresh unavailable"
            return result
        layouts = [{"x": x, "y": y, "scale": scale, "transform": transform, "primary": primary,
                    "connectors": [spec[0] for spec in specs]} for x, y, scale, transform, primary, specs, options in state[2]]
        result.update(modes_available=True, layout_available=bool(layouts), monitors=monitors, layout=layouts)
    except Exception as error:
        result["reason"] = type(error).__name__
        return result

    try:
        power = bus.call_sync(dest, path, "org.freedesktop.DBus.Properties", "Get",
                              GLib.Variant("(ss)", (interface, "PowerSaveMode")), None,
                              Gio.DBusCallFlags.NONE, 1500, None).unpack()[0]
        result.update(power_save_mode_available=True, power_save_mode=power)
    except Exception as error:
        result["power_save_mode_error"] = type(error).__name__

    result["available"] = all((result["modes_available"], result["layout_available"],
                               result["power_save_mode_available"]))
    if not result["available"]:
        result["reason"] = "incomplete display context"
    return result


if __name__ == "__main__":
    print(json.dumps(read_active(), indent=2))
