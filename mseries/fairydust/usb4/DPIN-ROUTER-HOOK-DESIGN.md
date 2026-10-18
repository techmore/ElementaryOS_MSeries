# Router-side DP-IN hook: design sketch (answers ledger G1/G2)

2026-10-16, Claude. **Design only; nothing built, booted or applied.** Kernel
feature work is DeepSeek's; this is input for them. Builds on
[the ordering note](evidence/2026-10-16-router-vs-dcp-activation-ordering.md)
(hook belongs in `tb_dp_activate()`, not on DCP ACTIVATE) and
[DPIN-IMPLEMENTATION](DPIN-IMPLEMENTATION.md). Source facts are from the pinned
tree (`ce9f2eba` + `0002`), function names only.

## Constraints read from the source

1. `tb_dp_activate(true)` runs under `tb->lock` (CM path). DP-IN activation polls an
   ACK for up to 1 s, so it **must not run inline** in the hook.
2. The DPRX wait is asynchronous: `tb_dp_dprx_start()` queues `tb_dp_dprx_work`
   (callback tunnels) with a ~12 s deadline. So the hook does not need to *finish*
   DP-IN activation before DPRX starts; it needs to *start it at the same point*,
   and 1 s of ACK latency fits well inside the 12 s window.
3. **Not every DP tunnel passes through `tb_dp_activate()`.** Tunnels found at
   boot by `tb_tunnel_discover_dp()` (`tb.c:389`) are already active; and the
   resume path re-runs `tb_tunnel_deactivate()`/`tb_tunnel_activate()`
   (`tb.c:3232/3244`). A hook only in `tb_dp_activate()` misses discovery.
4. `tb_port` has no firmware node. The ACIO (`apple.c`) already walks fwnode graph
   endpoints for its connector, so provider lookup should hang off the host
   router's ACIO, not off a port number.

## Proposed shape

- A small ops struct registered by the DP-IN provider on the ACIO, e.g.
  `{ tunnel_start(src_port), tunnel_stop(src_port) }`, looked up from
  `tunnel->src_port->sw` -> parent ACIO device. Option (a) in the ordering note.
- `tb_dp_activate(true)`: after `tb_dp_port_enable(src, true)`, before
  `tb_dp_dprx_start()`, call `tunnel_start()` **which only queues work** and returns.
  The work item does: activate DP-IN (`+0x0c` clear, ACK `+0x10`), then notify DCP
  to connect (the missing "start bridge"), outside `tb->lock`.
- `tb_dp_activate(false)`: next to `tb_dp_dprx_stop()`, call `tunnel_stop()`; it
  cancels pending start work first, then requests inactive and waits for ACK.
- Discovery and resume: call the same start/stop from the discover and
  re-activate paths so provider state follows the tunnel, not the call site.
- Gate on `tb_port_is_dpin(src_port)` and a host router that has a registered
  provider; every other platform sees a NULL ops pointer and no behaviour change.

## Refcount (G2)

Apple pairs `incrementTunnelUse`/`decrementTunnelUse`. Suggested minimum:
a per-adapter `count` in the provider, protected by its own mutex (not `tb->lock`);
activate hardware on 0->1, deactivate on 1->0. A host DP-IN adapter carries one
tunnel at a time, so the count is normally 0 or 1, but it can briefly be 2 when the
CM creates the replacement tunnel before the old one finishes tearing down. The
count turns that overlap into a no-op instead of a double activate or an early
deactivate.

Executable model of these semantics (overlap, cancel-before-run, stop without
start, failed ACK, discovery): [`test-dpin-refcount-model.py`](test-dpin-refcount-model.py),
6 tests pass. It checks the *design* is self-consistent; it is not kernel code and
proves nothing about hardware.

## Open questions this design does not close

- DP-IN index vs router adapter number: `0:5`->dpin0 and `0:6`->dpin1 comes from
  the debugfs map, not from a stable rule. Resolve by DT/adapter ordering before
  trusting it on other models (`j316`/`j314c`).
- Whether enabling DP-IN is enough, or the ACIO `startUsingTunnel()` step is also
  required (not proven; ordering note, "What this does NOT claim").
- Lock ordering: the work item takes the provider mutex and later DCP locks; confirm
  nothing there is held when `tb->lock` is taken.
- The Sven Peter teardown series rewrites `tb_dp_wait_dprx`/`tb_dp_dprx_work`/`tb_stop`
  (ledger G3); land the hook on top of it, not beside it.

## Test ladder (all gated by the owner's no-reboot/no-unplug constraint)

Module-only unit test of the refcount with a fake provider (no hardware) ->
build against the pinned tree -> one bounded hardware run with bypass ON first,
then bypass OFF only after the teardown hazard (`DP-TUNNEL-RE.md` §9) is covered.
