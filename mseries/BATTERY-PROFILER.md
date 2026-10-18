# Battery history, runtime profiler and app

Mac-style battery history for the M-series desktop (coconutBattery / the macOS Battery pane, but open and local).
No single popular open-source Linux tool does this, so this builds on the standard pieces instead of replacing them:
UPower stays the source for the panel indicator, `powerstat`/`powertop` stay installed for one-off measurements, and
this logger adds the long-term record they do not keep.

## What it records (every 15 s, `~/.local/share/mseries-battery/history.db`, 90 days)
Charge %, energy (µWh), charger state, battery flow, **whole-system power** (SMC "Total System Power", the same sensor
the panel watt label uses), CPU load and average clock, load average, battery temperature, screen brightness and the
top three CPU processes. Read-only: it never changes a setting.

## What it derives
- **Sessions**: each unplugged run (split by suspend gaps and the charger): length, % and Wh used, average W, and the
  full-charge runtime that draw implies.
- **Runtime by usage**: average draw and full-charge runtime per CPU band (Idle <10 %, Light, Moderate, Heavy ≥60 %).
- **Power events**: system power steps of ≥4 W, labelled with the likely cause (CPU load change, brightness change,
  charger) and the top process; plus suspend/off gaps with the charge lost (standby drain).
- **Health**: full vs design Wh, cycles, charge limit.

## Use
```
bash mseries/install-battery.sh              # installs logger service, `mseries-battery`, and the Battery app
mseries-battery status | sessions | profile | events | export [days]
```
App: "Battery" in the launcher (GTK4 + Granite 7: Overview, History chart, Sessions, Power events).
`bash mseries/install-battery.sh --uninstall` removes it and keeps the history.

## Prior art we could extend (not used yet)
UPower history (what GNOME Power Statistics graphs), TLP `tlp-stat -b`, powertop per-process estimates (Intel-centric,
weak on Apple Silicon), `upower` time-to-empty. Omarchy-mac's battery piece is only the charge-limit script, already
ported as `mseries-power` (see PORT-MAP.md); nothing else there profiles runtime.

## Status (2026-10-18)
Logger installed and running on the M1 Pro; 8 unit tests pass (`battery/test_battery_core.py`); CLI verified against live
and synthetic history; the app (sidebar layout, battery gauge, usage bars, event icons, chart with hover readout) renders all four pages under
Xvfb with the installed elementary blueberry stylesheet, light and dark (synthetic 8 h history). **Not verified:** the
look on the owner's live session (no window was opened on their screen), real discharge sessions (the machine
has been on the charger since logging began), and any claim about actual runtime. Runtime figures stay "—" until
there is a 30 min unplugged run.
