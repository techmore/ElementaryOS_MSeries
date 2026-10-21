# PolyBagger T1000 Print Manager

Native elementary OS (GTK3 + Granite) app and CLI for the label printer on the Advanced Poly T-1000
bagger line (Zebra ZTC 110Xi4-203dpi, USB). It detects the printer when it is plugged in, sends raw ZPL
and verifies the job through CUPS. Label sources live in [techmore/thril](https://github.com/techmore/thril)
(`poly-bagger/UPC Labels`, site: https://techmore.github.io/thril/).

```bash
python3 mseries/polybagger-print-manager/polybagger_print_manager.py            # GUI
python3 mseries/polybagger-print-manager/polybagger_print_manager.py --status
python3 mseries/polybagger-print-manager/polybagger_print_manager.py --send "<file>.zpl"   # PASS/FAIL, exit 0/1/2
python3 mseries/polybagger-print-manager/polybagger_print_manager.py --sync --pull         # refresh offline labels
```

## What it checks
USB (vendor 0a5f) present, CUPS queue exists and is enabled, no job stuck "waiting for printer", ZPL has
`^XA`/`^XZ`, job submitted with `lp -n 1 -o raw`, then CUPS reports it completed. After a pass the GUI asks
whether the label physically came out and logs the answer. "Completed" only means CUPS delivered the data;
the printer's own status is not read back.

## Offline label store
`~/.local/share/polybagger-print-manager/labels/` holds a copy of every label `.zpl` plus `manifest.json`
(sha256). It is refreshed from the local thril checkout on every start (no network). The refresh button or
`--sync --pull` also `git pull`s thril, and fails quietly when offline. Job results go to `log.jsonl` there.

## Rules carried over from thril's `poly-bagger/AGENTS.md`
- Always send raw (`-o raw`); a non-raw queue rasterises ZPL.
- Never put `^PON` or `^FWN` in ZPL (the app warns); power-cycle the printer after a rejected job.
- Labels are sent upside down on purpose. The preview is inverted 180° for auditing only; files are sent unchanged.
- A store file (`^DF`) prints nothing; send its recall file (`^XF`) to confirm.
- Sending the same file twice within 2 minutes asks for confirmation.

## Known gaps
- Print quantity: the cause of "second send prints without limit" is not found. Needs the printer config
  (`^HH`) and directory (`^WD`) labels read first.
- Queue setup (`--setup`) uses `pkexec lpadmin -m raw` and is untested.
- Related wiring notes: [../../docs/polybagger-t1000-printer-link-troubleshooting.md](../../docs/polybagger-t1000-printer-link-troubleshooting.md).
