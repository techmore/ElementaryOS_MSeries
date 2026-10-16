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

## Finding 1 (probable root cause of the failed activation): HPD-low abort fires on the first poll

`-67` is `-ENOLINK`. `dpin_power_on()` calls `apple_dpin_set_inactive(io, 0)` (0005):

```c
value = read(INACTIVE);  write(INACTIVE, (value & ~1U) | inactive);
for (;;) {
    if ((read(INACTIVE_ACK) & 1U) == inactive) return 0;
    if (!inactive && !(read(HPD) & HPD_LEVEL))   return -ENOLINK;   // <- fires here
    if (time_us() >= deadline)                    return -ETIMEDOUT;
    ...sleep
}
```

The first loop iteration runs immediately after the write. The ACK cannot have changed
yet, so unless HPD is already high the function returns `-ENOLINK` without ever giving
the hardware time to ACK. HPD at the DP-IN block is not high at this point (the tunnel
that would carry the sink's hot-plug is not up yet), so activation is **guaranteed to
abort at once**. This matches the log: failure ~0.7 s after the dock appears, a few ms
after `poweron` started, with no timeout wait.

This is a code-reading plus one log line, not a register trace. Two competing
explanations remain: (a) the HPD abort is simply wrong for this ordering (activation must
wait for the ACK, HPD arrives afterwards); (b) Apple really aborts on HPD low and HPD
needs another trigger first (REA notes "observes HPD while ACK is pending"; what it does
on low is not recorded in `REA-DPIN-FINDINGS.md`). The ordering note
(`evidence/2026-10-16-router-vs-dcp-activation-ordering.md`, fact 4) already said HPD
cannot be the trigger because activation exists to observe it; the implementation
contradicts that.

**Proposed next iteration (reference only, the kernel lane is Codex/DeepSeek's):**
1. Instrument before changing semantics: on any failure log `INACTIVE`, `INACTIVE_ACK`,
   `HPD`, `IRQ_STATUS`, `IRQ_ENABLE` (a single `dev_info`), so the next boot answers (a) vs (b)
   with data instead of inference.
2. For `inactive == 0`, do not return on HPD low during the first poll; wait for the ACK
   up to the 1 s bound, and only then report `-ETIMEDOUT` (with the register dump) or
   `-ENOLINK` if HPD is still low. Update the offline test that currently asserts the
   immediate `-ENOLINK`.
3. Keep bypass armed; the failure happened before DPRX, so bypass was irrelevant.

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
- The next hardware step is not a rebuild of everything: it is Finding 1's instrumented,
  non-aborting activation, plus Finding 2's guard, then one more controlled boot.
- Do not diagnose this as "silent sink": DPRX was never reached.
