# Retained baseline runs

| Run | Contents | What it establishes | Missing |
| --- | --- | --- | --- |
| [macos-2026-10-17-1220](macos-2026-10-17-1220/summary.json) | Inventory, settings, historical sleep summary; AC attached, brightness 50%, display reports 120 Hz | MacBookPro18,3 / M1 Pro inventory; two historical battery sleep periods (0.391%/h median) | All active scenarios; matched Linux run |

`scenarios` is empty in this committed run. Do not treat its inventory-only collection conditions as a
battery workload measurement. Sleep statistics refer to historical battery periods, not time spent collecting
inventory on AC. The parity checklist currently imports this run alongside older Linux observations.

Keep raw process dumps, powermetrics and logs local. Add a reviewed summary row here for each published run,
including power source, display/app conditions, completed scenarios and limitations. Preserve older runs;
do not replace their summaries with a newer capture.
