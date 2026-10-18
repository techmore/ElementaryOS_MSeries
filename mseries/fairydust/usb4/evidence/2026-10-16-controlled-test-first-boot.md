# Controlled test, first hardware boot — what the journal shows

2026-10-16, Claude. Read-only analysis of `journalctl -b -2 -k` on the M1 Pro
(boot of 11:45:04, GRUB entry `elementary-usb4-dpin-controlled`, kernel
`7.1.13-elementary-fairydust-usb4-dptunnel`, cmdline
`thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=15000`).
The boot was started by the owner/Codex; nothing here was run by this analysis.
Raw journal is not stored in the repo; the lines quoted below are enough to reproduce
the reading. The older entry (boot at 11:48) and the stock kernel (now) are unrelated.
Companion record (outcome, saved-journal hashes and continuation):
[2026-10-16-controlled-test-first-boot-outcome.md](2026-10-16-controlled-test-first-boot-outcome.md).

## Timeline (seconds since kernel start)

| t | Event |
|---|---|
| 8.2 | `apple-dcp 28cc00000.dcp: DCP index:2 dptx target phy: 1 dptx die: 0 tunnel: 1`, crossbar `dpin0 -> dispext1,0` (the DT wiring and bridge probe worked) |
| 11.12 | `thunderbolt 0-1: Dell WD22TB4 Thunderbolt Dock` (USB4 link up) |
| 11.79 | **`phy phy-b01e50000.phy.12: phy poweron failed --> -67`** |
| 11.79 | `thunderbolt-apple-nhi: DP source preparation failed: -67` |
| 11.79 | `0:5 <-> 1:14 (DP): not active, tearing down` (right pairing; fail-fast tore it down) |
| 89.6-90.2 | burst of `Gen2/3 link error` then dock USB devices and `thunderbolt 0-1` disconnect; ACIO re-initialises at 92.8 (probably a cable event or link loss; unconfirmed) |
| 94.8 | s2idle suspend refused (`unable to suspend while a USB4/Thunderbolt connection is active`, -16): expected |
| 96.4 | **NULL pointer dereference** in kworker `apple-dp-source`: `pm_runtime_resume_and_get` <- `dpin_init+0x2c` <- `dcp_dptx_connect_source+0x268` <- `apple_dcp_dp_source_start` <- `apple_dp_source_work` |

No `DP source ready for host port 5 before DPRX` line, no DPRX attempt, no EDID. Milestone M1 is still not met.

## Finding 1: activation aborts on HPD low, and Apple's own code does the same (corrected)

`-67` is `-ENOLINK`. `dpin_power_on()` calls `apple_dpin_set_inactive(io, 0)` (0005), which
returns `-ENOLINK` when HPD (`+0x00` bit 2) is low while the ACK has not yet matched.
The first poll runs right after the write, so unless HPD is **already high** when
activation is requested, it aborts at once. That matches the log (failure about 0.7 s after
the dock appears, no timeout wait).

**Correction to my first version of this note and the PR #53 comment.** I called the
HPD-low abort a probable Linux bug. Reading Apple's own function in the owner's local REA/Kuna
output (`rea-investigation/dpin-active-block-kuna.json`, entry `0xfffffe000938c154`,
`makeDPINAdapterPortActive_block_invoke`) shows macOS does the same:

```
set DPTX_INACTIVE = !makeActive  (reg +0x0c); deadline = now + 1000 ms
if ((readReg(+0x10) & 1) != target) do {
    if (now > deadline)  -> log "timeout: no response from firmware after %ums"; return 0xe00002d6
    if (makeActive && !(readReg(+0x00) >> 2 & 1))
                         -> log "notice: hpd status: HPD_LEVEL_STATUS=0x%08x"; return 0xe00002eb
    IOSleep(1 ms for the first 5 polls, then 5 ms)
} while ((readReg(+0x10) & 1) != target)
```

So the Linux implementation faithfully copies Apple (explanation (b) in my first version),
and removing the abort would diverge from macOS. The real question is **why HPD is low at
that moment**, and the likely answer is ordering: in macOS this activation runs from the
tunnel-client state change *after* the sink's hot-plug has reached the DP-IN block, whereas
our bridge asks for activation as soon as the adapters are enabled, before HPD has
propagated through the new tunnel. Not yet proven: HPD might only rise after DP-IN is
active, which would be a chicken-and-egg that macOS breaks some other way.

**Proposed next iteration (reference only; kernel lane is Codex/DeepSeek's):**
1. Treat `-ENOLINK` from the PHY power-on as *retryable until the existing 5 s source
   deadline* in `apple_dp_source_work()` (today only `-EAGAIN/-EPROBE_DEFER/-EINPROGRESS`
   are), or better, wait for the DP-IN plug IRQ (already enabled in `dpin_init`) and then
   activate. This is a smaller change than removing the abort and keeps Apple's semantics.
2. On every failure log `INACTIVE`, `INACTIVE_ACK`, `HPD`, `IRQ_STATUS`, `IRQ_ENABLE`
   (and, on a retry, whether HPD ever went high). That single boot decides between "HPD just
   needed time" and "HPD needs the source active first".
3. Keep bypass armed. DPRX was never reached.

## Finding 2 (separate bug): stale PHY after the ACIO re-probes

At 96.4 the worker started a new source attempt after the dock/ACIO went away and came
back. `dcp->phy` (taken once with `devm_phy_get`) still points at the *old* `struct phy`;
the ACIO re-probe destroyed and recreated its child PHY devices, so `phy_get_drvdata()`
returned freed memory (`dpin->dev == NULL` -> fault at offset `0x1d0`). This is the
provider/consumer-removal case flagged in `DPIN-IMPLEMENTATION.md` ("ACIO depopulates its
children"). Candidate fixes: look the PHY up per start and `phy_put()` per stop, or
guard every start with a check that the provider is still bound (device link with
`DL_FLAG_AUTOREMOVE_CONSUMER`, or fail with `-ENODEV`). Either way a start after
provider removal must fail cleanly, never oops. B5/B8 in the gap ledger did not cover this.

## What this changes in the plan

- The bridge, DT mapping, module loading and fail-fast path **work on hardware**:
  that is real progress over "never tested".
- The next hardware step is not a rebuild of everything: it is Finding 1's retry-until-HPD (with
  register logging), plus Finding 2's guard, then one more controlled boot.
- Do not diagnose this as "silent sink": DPRX was never reached.
