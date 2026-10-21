# xART guard and Touch ID on the J314S (M1 Pro) — 2026-10-21

**Status:** on this Mac, with the default guard, Touch ID cannot be used: an enrolment finishes in the
enclave but Linux refuses to save it, and the driver reports matching as `blocked`. **The owner has not
decided whether to lower the guard. It is unchanged (level 1) and nothing was written to xART by hand.**
The Touch ID Settings page says "Matching is blocked on this Mac" while this holds.

## What we measured on this Mac

Kernel `7.2.10-elementary-aurora72-wip2` (omacom/linux-aurora `644133b7`), driver parameters default.

- Probe: `xART guard level 1: 13 session records exist, 0 created by Linux; the other 13 are protected`.
  `/var/lib/aurora-sep-xart-owned.bin` (Linux's list) is 0 bytes. The Linux keybag and refkey
  (`aurora-sep-keybag.bin`, `aurora-sep-refkey.bin`) date from 2026-10-17, made by an older Aurora kernel
  that had no guard.
- Third enrolment attempt of the second boot (13:27:47–13:28:04): the enclave completed the enrolment
  (user catacomb state 7), then `xART guard: refused to rewrite a kind-4 record this Linux install did not
  create` and `enrol: Catacombs saved but identity-bag snapshot failed; not reporting enrollment success`.
  fprintd got status 0x6 and stores no print.
- After a reboot the first `/dev/sep-bio` open restored all three catacombs (`identity count 1`, `enrolment
  survived reboot`). The driver's `diag/matching` reads `blocked`.
- The xART `max revision` went 61942 → 61948 across the attempts, so some xART writes were allowed.
- Separately, the sensor patch was not acknowledged on some stage-2 power-ups (`sensor patch: no
  acknowledgment after 250 polls`, fprintd status 0x1). Verify and attach retry this; `run_enrolment` at
  `644133b7` calls `bring_sensor_online()` directly, without the retry. It succeeded on a later attempt in
  the same boot.

## What upstream documents

Sources: [aurora-silicon/linux#361](https://github.com/aurora-silicon/linux/pull/361) (merged 2026-10-18) and
[XART-SAFETY.md](https://github.com/omacom/linux-aurora/blob/integration/aurora/tools/aurora-sep/XART-SAFETY.md).

- The guard (`xart_guard`, default 1 on M1 to M3, 0 on the Neo) refuses to rewrite a session record that
  existed when the driver opened the gigalocker and is not on Linux's list. A refusal fails the request
  closed: no record changes, Touch ID may be unavailable.
- Cold-boot M1-family Macs (seen on T6000/J316s): creating the keybag rewrites a session record from before
  Linux, so the keybag can only be created with `xart_guard=0`. Upstream's M1 Pro test machine pins
  `xart_guard=0`.
- A Mac whose Touch ID was set up with the guard off "needs `xart_guard=0` to use Touch ID, not only to set it
  up": the guarded boot restores the fingerprints, then refuses the match's write (the log line above).
- A match on an M1 Pro rewrote two pre-existing session records and both shared roots (ledger diff,
  2026-10-17). Which records those are has not been established. Upstream says to treat macOS Touch ID as
  unverified after running with the guard off.
- Upstream had not measured enrolling a finger on a guarded Mac. Our log is that data point: the enclave
  asks for the kind-4 rewrite, the guard refuses it, and the enrolment fails closed.
- Turning the guard back on later does not list records written while it was off.

## What the maintainers already said (omacom PR #139, 2026-10-19)

The review thread of [omacom/linux-aurora#139](https://github.com/omacom/linux-aurora/pull/139), the merge our kernel is built from,
covers this. RyanTheTide's reply (item 2, "xART guard guidance") says: restore works under `xart_guard=1`; **use** works only for
records Linux created while the guard was on; **setup** on cold-boot Macs (T8103, T6000/T6001) rewrites a pre-Linux record and needs
`xart_guard=0`, **and the matches that follow need it too**. On an M1 Pro one verify rewrote two session records and both shared
roots. A later comment says the reference M1 Pro (J316s) runs this kernel as its daily with `xart_guard=0` and `matching=usable`,
while a base-M2 on guard level 1 reads `unverified`. The same thread tracks the "M1 Pro Touch ID first-attempt rate" (intermittent
sensor registration failures) as accepted for the edge branch with an instrumented soak as follow-up. So what we hit is known and
intended upstream: with the default guard, a cold-boot M1 Pro cannot use Touch ID, and the maintainers' own M1 Pro runs with it off.
What upstream has not published is the enrol-only measurement below.

## Options (owner decision)

1. **Leave the guard on.** Nothing about other OSes' records is at risk. Touch ID stays unusable here.
2. **Pin `options apple_sep xart_guard=0` in `/etc/modprobe.d/` and reboot.** This is what upstream's M1 Pro
   machine does, and the documented way to use Touch ID on a cold-boot Mac. It accepts that the enclave may
   rewrite shared, pre-Linux records, and leaves macOS Touch ID unverified. Untested here: whether the
   identity already in the enclave from the failed enrolment is reused or reported as a duplicate.
3. **Not recommended:** `install-aurora-sep.sh --reset-touchid` (new keybag). Creating a keybag on a
   cold-boot M1 needs the guard off and rewrites a pre-Linux record.

The `.20` kernel (`7.1.12-2-20261017.20`) was built the day before the guard merged. Its matching behaviour
has not been tested, and earlier Touch ID probes on `.19`/`.20` hung the machine (`AURORA-SECOND-BOOT.md`).

## A correction

Earlier notes and a draft report from 2026-10-21 suggested the refused kind-4 record was one Linux itself
created on 2026-10-17. Upstream describes the record the keybag creation and a match rewrite as a session
record that existed before Linux. Treat the refused record as a pre-Linux record that an unguarded kernel
may already have rewritten on 2026-10-17. Neither reading is verified.

## Reading the state

The driver publishes read-only attributes in `/sys/bus/platform/drivers/apple_sep/*/diag/`. Values seen on
this Mac: `touchid: ready`, `sensor: online`, `restore: restored`, `xart_guard: 1`, `xart_guard_list: loaded`,
`xart_guard_refusals: 0` (at boot), `matching: blocked`. `blocked` means writes are disabled, the guard has
refused a write, no list loaded, or a guard runs on a cold-boot Mac. The Touch ID Settings page shows these
under Details. `journalctl -k | grep -E 'apple_sep|xART'` shows the refusal lines.
