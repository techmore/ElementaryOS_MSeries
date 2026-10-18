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

## Added in the second pass
- **Energy by app**: idle floor (10th-percentile draw) charged to the system, draw above it shared among processes by CPU
  share. An estimate that sees CPU time only (GPU/display work lands in the floor or the app driving it).
- **Charging runs** (Wh added, average W) and **sleep drain** (% per hour from suspend gaps on battery).
- **Health trend**: one capacity/cycles snapshot per day.
- **High-drain alert**: a notification when unplugged draw averages ≥15 W for 5 min, naming the busiest process and the
  runtime at that rate; 30 min cooldown. Edit `~/.config/mseries-battery/config.json` (`alerts`, `alert_watts`,
  `alert_minutes`, `alert_cooldown_minutes`) to change it.
- **Report**: `mseries-battery report [days] > battery.md`, or the save button in the app's title bar.

## Added in the third pass
- **Power profile** (power-profiles-daemon, read once a minute) is logged per sample; the Overview compares draw per
  profile at the same CPU load (idle and light bands), so Power Saver vs Balanced is a fair comparison.
- **Suggestions from your own data**: brightness (draw above 70% vs 50% or below at light load), a busy app, trying
  Power Saver, high sleep drain, capacity under 80%. Each appears only when this machine's samples back it
  (an hour or more on battery). CLI: `mseries-battery tips`; also in the report.
- **Preferences** (gear in the title bar): alert on/off, watts, minutes, cooldown. The logger re-reads the file each
  sample.

## Added in the fourth pass
- **Accessories**: mouse/keyboard batteries (`scope=Device`) logged on change (hourly otherwise), shown on an Accessories
  page and via `mseries-battery devices`. The MX Vertical here reports only a level (Normal/Low), no percentage, so it
  shows time at the current level; devices with a percentage get a days-left estimate from the last week's slope.
- **Logger cost, measured 2026-10-18 on the M1 Pro:** about 0.17 s of CPU per minute (~0.3 % of one core), 18 MB RSS,
  `Nice=15` and idle I/O class. The database grows by tens of KB per hour of use.

## Image integration
`enhance.sh` has a `battery` module (`--only battery`) that stages the logger, command, app, unit and desktop file and
enables the user unit for every account (`battery/test_battery_enhance.py` checks it against a scratch root). The panel
patches (ETA, watts, Battery summary card) ship through the `battery-panel` first-boot module
(`install-battery-eta.sh`, gated on the Power indicator being 8.0.2, built with network at first boot) and the
`battery` / `battery-eta` rows of `post-install.sh`. Verified: `enhance.sh --only payload` stages the script, all
three patches and `repair-panel.py`; `bash -n` passes. **Not verified:** a first-boot run, and the factory image
is unbooted.

## Use
```
bash mseries/install-battery.sh              # installs logger service, `mseries-battery`, and the Battery app
mseries-battery status | sessions | profile | apps | charging | tips | devices | health | events | report | export [days]
```
App: "Battery" in the launcher (GTK4 + Granite 7: Overview, History chart, Sessions, Energy by app, Health, Power events).
`bash mseries/install-battery.sh --uninstall` removes it and keeps the history.

## Prior art we could extend (not used yet)
UPower history (what GNOME Power Statistics graphs), TLP `tlp-stat -b`, powertop per-process estimates (Intel-centric,
weak on Apple Silicon), `upower` time-to-empty. Omarchy-mac's battery piece is only the charge-limit script, already
ported as `mseries-power` (see PORT-MAP.md); nothing else there profiles runtime.

## Status (2026-10-18)
Logger installed and running on the M1 Pro; 18 unit tests pass (`battery/test_battery_core.py`); CLI verified against live
and synthetic history; the app (sidebar layout, battery gauge, usage bars, event icons, chart with hover readout) renders all four pages under
Xvfb with the installed elementary blueberry stylesheet, light and dark (synthetic 8 h history). **Not verified:** the
look on the owner's live session (no window was opened on their screen), real discharge sessions (the machine
has been on the charger since logging began), and any claim about actual runtime. Runtime figures stay "—" until
there is a 30 min unplugged run.
