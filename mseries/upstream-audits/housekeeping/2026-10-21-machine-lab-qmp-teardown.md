# Machine Lab fake-QMP teardown — 2026-10-21

## Confirmed failure

The Share Eyes final validation at `ada283c3` compiled all 39 targets. Machine
logic printed all 14 TAP results, including two expected qemu-img skips on CI,
but Meson timed out after 60 seconds. The independent clipboard fake-QEMU test
passed. An earlier source run passed, consistent with a race rather than an
assertion or guest failure.

The QMP fixture started two Python peers inheriting the test's stdout/stderr,
called `GSubprocess.force_exit()` and returned without waiting. In 100 local
QMP-only runs with captured output, iteration 22 timed out with parent status 0
and both owned peers still alive (PIDs 630783 and 630785). Only those peers,
identified by the exact audit-fixture executable path, were killed. No global
process cleanup was used. Source scratch and raw receipts were retained outside
Git. This reproduces the CI distinction: test completion is not output EOF.

## Change

The fixture now uses private stdout/stderr pipes, sends termination, then calls
`communicate_utf8` to drain diagnostics and wait/reap each peer. It records any
child diagnostics and asserts signal termination was observed. No QMP runtime,
VM launcher, clipboard implementation, or application source changed.

A Python regression launches only the QMP test in an owned process group and
private temporary directory. It checks successful TAP output plus parent exit
and captured-output EOF within 10 seconds, repeated 20 times. On failure it kills
only its owned group before collecting diagnostics. The 60-second machine-logic
timeout is unchanged; the new test has its own 30-second outer bound.

## Verification

- Full Machine Lab application and test build: 39 targets completed.
- Equivalent 100-iteration captured-output run after fix: zero failures, 7.856 s.
- All five Machine Lab Meson suites pass, including the bounded 20-run EOF
  regression (1.63 s), machine logic (0.36 s), and clipboard fake peer (5.23 s).
- Python compilation and `git diff --check`: pass.

Raw local receipts in the morning task output directory:
`machine-lab-qmp-teardown-before.json`, `machine-lab-qmp-teardown-after.json`,
`machine-lab-qmp-teardown-fixed-tests.log`.

This is fixture reliability evidence; it does not qualify real guest startup,
clipboard interoperability, Apple hardware or a production deployment.
