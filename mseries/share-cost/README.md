# Screen-share cost baseline

Measures what a live screen share costs **this desktop**: the owner's browser
(which encodes one WebRTC stream per viewer), the share server, the panel and
compositor, the PipeWire capture path, and whole-system power when the SMC
sensor exists.

Why this exists: the share stack is Rust on the server side
(`rupert-share/core`, `src/share.rs`) and the desktop integration is verified
(eyes indicator, dock app, links over LAN / tailnet / the public proxy), but the
resource cost was never measured — `rupert-share`'s own test record lists "CPU of
the sharing Brave while sharing" as an open row. Any proposal to change the
media path (a Rust capture/SFU service, a TURN relay, more viewers) needs that
baseline first, because on this stack each additional viewer costs the owner's
browser another WebRTC encode chain, and the M1 Pro has no hardware video
encoder available from Linux.

## Run it

Start a share the usual way (`mseries-share-start`, or
`~/Projects/rupert-share/core/scripts/share-demo.sh --lan|--tailnet|--public …`),
connect your viewers, then capture a matched pair:

```bash
# same machine, display, content and interval; only the viewer count changes
bash mseries/share-cost/collect-share-cost.sh 60 fullscreen-video 1 5 > viewers-1.csv
bash mseries/share-cost/collect-share-cost.sh 60 fullscreen-video 3 5 > viewers-3.csv

python3 mseries/share-cost/summarize-share-cost.py viewers-*.csv
python3 mseries/share-cost/summarize-share-cost.py --process viewers-3.csv   # per-process detail
```

Arguments: `<duration-seconds> <workload-label> <viewers> [interval-seconds]`,
plus `--browser NAME` (default `brave`) and `--require-live` (fail unless the
launcher reports a live share). The collector is read-only: it reads `/proc`,
hwmon and the launcher's `state.json`, and never starts, stops or touches a
share, the portal or PipeWire. It records viewer counts as the launcher reports
them, so a run that expected 3 viewers but had 2 says so.

To verify the collector itself against a real share server without touching the
live desktop, `probe-live-share.sh /path/to/rupert-share/core` starts a
throwaway loopback-only share in a private `HOME` and `XDG_RUNTIME_DIR`, joins
one viewer through the API, and reduces a 15-second capture. It proves the
plumbing (live state, viewer count, server role) — it does not measure sharing
cost, because no browser capture runs in it.

## The protocol (what makes a number mean something)

1. **Matched pairs, not single runs.** Same display mode and scale, same
   on-screen content (a fixed fullscreen clip is best), same interval, same
   session age. Change one thing: the viewer count.
2. **Arms of at least 60 seconds**, alternating 1 → 3 → 1 → 3 viewers, medians
   reported per arm. Run-to-run variation on this machine is large; one capture
   proves nothing.
3. **Record the conditions with the numbers**: AC or battery (the machine caps
   CPU frequency on battery through `mseries-power`, which skews CPU
   comparisons — use AC for CPU work, battery for power work), brightness,
   refresh/VRR, what else is running. Close what you can; write down what you
   cannot.
4. **Read CPU and power together.** The SMC `power1_input` rail (node
   `macsmc_hwmon`) is whole-system watts on AC; battery flow is only meaningful
   while discharging. Neither isolates the share — they bound what the share
   can possibly cost.
5. **The viewer side is out of scope here.** These captures describe the
   sharer's machine only. Viewer-side decode cost, latency and quality need
   their own measurement on the viewer's device.

## What counts as a result

- A difference in owner-side CPU or whole-system watts that exceeds the spread
  between repeated arms of the same condition, with the conditions above
  recorded. Until then the honest statement is "no measured difference".
- For any proposed change (Rust capture/SFU, TURN, more viewers): before/after
  captures under the same protocol. Language choice is not a result.

## Relationship to the other collectors

Same CSV shape as `pantheon-rust-compositor/collect-session-metrics.sh` plus
`role`, power and share-state columns, and the reducer reads both (captures
without a `role` column fall back to per-process grouping). Results can feed
the Optimization repository's `powerlab` workflow the same way other
measurements do.

## What the baseline feeds

[`MEDIA-PATH-OPTIONS.md`](MEDIA-PATH-OPTIONS.md) records the owner decision
(2026-10-19): screen-share media stays **peer-to-peer**, the work stays in this
repository, and the Rust-SFU/server-capture/stock-SFU options are rejected for
this MVP. Option A (TURN deployment plus the tailnet link label) is the only
candidate, and the matched-pair baseline decides only whether the viewer cap
can be raised. That document is the go/no-go frame; this directory is the
evidence.
