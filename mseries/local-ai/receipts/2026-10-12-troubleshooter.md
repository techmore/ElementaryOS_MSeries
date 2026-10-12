# Gemma 4 troubleshooting verification — 2026-10-12

Target: MacBookPro18,3 / M1 Pro / j314s, elementary/Pantheon,
`7.1.13-1-2-fairydust-usb4-ARCH`.

- Joshua repository inventory: GitHub pagination returned 148 public names;
  exact name-set comparison with the tracked inventory showed no changes.
- Runtime: installed Linux MLX v0.7.32 integration, mlx-lm 0.31.3, private
  Honeykrisp Mesa `7faf04c065`; `mlx-omarchy-info` confirmed Apple M1 Pro GPU,
  packaged ICD and matching expected/actual driver SHA. ANE remains unavailable.
- Model: `mlx-community/gemma-4-e4b-it-4bit` revision
  `475b9088d29754a3379866cf5aeb6b41acd313c2`, Hugging Face metadata reports
  5,179,241,512 bytes across artifacts. Download completed. This is also the
  revision in Joshua's 2026-10-10 Gemma E4B receipt.
- Admission: 4096 context, estimated 5 GiB full artifact, existing chat
  reservation 4.30 GiB and desktop reserve 2 GiB: FITS with about 2.27 GiB
  headroom at initial check. These are estimates, not measured peak memory.
- Local model service started at `127.0.0.1:8767` with the private ICD.
  `/v1/models` and `/v1/chat/completions` succeeded.
- Three-line OOM fixture: output identified kernel OOM termination of
  example-editor, cited L1/L3, and suggested `free -h`. Saved report under
  the user's private state directory.
- Actual journal: successful response identified repeated USB reset failures
  and Gala/Wingpanel assertions, citing input line IDs and explicitly stating
  that causal linkage was unproven. No repair was executed from model output.
  This checks useful end-to-end inference, not diagnostic accuracy generally.
- Nine regression checks passed: loopback endpoint enforcement, secret
  redaction, bounded file input, redirect refusal, log content never executed,
  coredump owner filtering, invalid PID rejection, and private report persistence
  with exact evidence, plus an event-stream fixture proving duplicate suppression
  and a single watcher-launched analysis across concurrent crash events. Python compilation and shell syntax checks passed.
- Native Wingpanel module built and installed. After reload, the live
  Wingpanel process mapped `libmseries-troubleshooter.so`.
- GTK application and crash watcher user services were active, with no GUI
  startup errors in their unit journal. GUI rendering and physical menu clicks
  have not been visually inspected.
- Deterministic panel repair was executed: the original own-user Wingpanel
  exited, a new process appeared and remained running through the verification
  interval.
- Model was stopped after the initial verification to release memory; the
  application starts it on demand. It was active again at the final service
  check, so was left available for current use. Existing MLX Chat processes
  were preserved.

Real crash-triggered automatic diagnosis and suspend/resume remain untested;
no deliberate crash or reboot was induced. No latency or performance superiority
claim follows from these checks. Reports containing actual logs are not committed.
