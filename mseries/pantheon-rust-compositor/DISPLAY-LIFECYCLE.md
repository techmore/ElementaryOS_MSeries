# Native display lifecycle diagnostics

`PANTHEON_DISPLAY_TRACE=1` opts the native compositor into structured
`pantheon_display_lifecycle` records. It is off by default and reads the switch
once at startup. This candidate is built but **not installed or loaded**.
The existing activation implementation from merged PR #362 is included in the
same candidate; it is not a second activation mechanism.

## Enable for an attended login

After installing the exact candidate package, put the
following in a dedicated user-service drop-in for the **next login**:

```ini
# ~/.config/systemd/user/pantheon-rust-compositor@wayland.service.d/display-trace.conf
[Service]
Environment=PANTHEON_DISPLAY_TRACE=1
Environment=RUST_LOG=info,pantheon_display_lifecycle=info
```

Reload unit definitions with `systemctl --user daemon-reload`; this does not
restart the compositor. Sign out/in only when the owner is ready. Preserve any
existing logging preference when adding the target filter. Remove only this
specific drop-in and reload definitions to disable tracing at a later login.
Neither the build nor these instructions require restarting Wingpanel.

Read logs with:

```sh
journalctl --user -u pantheon-rust-compositor@wayland.service -b -o short-monotonic \
  --grep=pantheon_display_lifecycle
```

## Fields and coverage

- `monotonic_us`: microseconds since the first opted-in record in this process.
  Journal monotonic time provides the common clock for kernel/udev comparison;
  do not directly subtract the compositor-local field from a kernel timestamp.
- `generation`: operation sequence for initialization, connector reconciliation,
  CRTC reassignment, explicit enable/disable, mode changes and session pause/
  activate. End records report elapsed time even on an early return; they mean
  the operation exited, not that it succeeded. Consult transition/error records.
- `udev_event`: KMS device, event kind, coalesced flag, burst count and newly
  armed deadline. `scheduler_tick` reports event/follow-up/removal/safety due
  reasons, session pause state, burst count and wait since its first uevent.
  Scheduler records precede the corresponding reconciliation generation.
- `connector_transition`: connected state or mode-count changes from the reads
  already used by reconciliation. Removed resource handles are recorded.
  This is not an EDID-content-change detector.
- `kms_initialized`: newly hotplugged output's KMS initialization duration and
  mode. `space_mapped`, `disconnected`, `disabled`, `global_retired` and
  `reconcile_result` show publication, removal and actual topology changes.
- `use_mode`: target mode, commit duration and success. Existing rollback errors
  retain their normal logs. `link_status` records changes from existing property
  reads; `link_reset` includes the existing bounded attempt count, duration and
  result.
- `first_queue` and `first_pageflip`: at most one pair per output marker. Markers
  are created before output initialization, after a successful reassignment or
  mode change, and after a successful link reset. `since_output_marker_us` is
  elapsed time from that marker. Their generation remains the creating
  operation's generation even if another reconciliation runs first. A pageflip
  acknowledges scanout work; it does **not** prove the monitor shows a picture,
  identify a physical USB-C socket, or prove downstream HDMI link training.

Records are capped at 512 per fixed monotonic minute, plus one suppression
notice. Exhaustion can omit individual markers and never changes display work.
No per-frame stream, raw EDID, monitor serial, window title, activation token or
input contents are logged. Connector/property observations use existing reads;
no additional DRM polling, timers or link-reset attempts are introduced.

## Optimization boundary and follow-up

The deployed scheduler already coalesces a DRM uevent burst for 250 ms, performs
one settling recheck after 1 s, polls every 30 s when udev works (2 s fallback),
and retires disabled globals after 2 s. Link recovery remains at most three
attempts, at least 5 s apart. Those policies remain unchanged.

Owner-confirmed picture/input now work on all three physical ports. The parent
poller sampled at 0.5 s: right/rear-left partner-to-dock about 3 s,
dock-to-connector about 1 s, connector-to-compositor about 0.5 s. Front-left
partner arrival was recovered from the retained event log: about 4.511 s overall
(with a documented poll-boundary correction). These are coarse
single moves, not latency distributions or proof of a compositor bottleneck.

Use at least three matched moves per port, with the same dock/cable/display and
an owner picture confirmation after each move. Correlate journal timestamps to
separate USB4 discovery, connector readiness, event debounce, KMS initialization
and first acknowledged frame. Keep timeouts/failures and missed edges in the
results; never turn unknown times into zeros.

This candidate reuses successfully parsed EDID identity from duplicate-route
inspection within the same scan (startup or reconciliation). A newly mapped
connector avoids a second property/blob query when that first read parsed
successfully. Missing or malformed EDID is not cached: the later identity path
still retries, and every new reconciliation reads again. Stale-route detection
still receives the same raw EDID/blob candidates. `edid_read` records the existing
query duration and success without recording its bytes or identity. This removes
redundant I/O by source inspection; actual end-to-end speedup is unmeasured.

No cross-reconcile cache, unconditional unchanged-topology shortcut, debounce
reduction or driver parameter change is included. Layout/profile changes, link
resets and pending global removals continue even when names are unchanged.
