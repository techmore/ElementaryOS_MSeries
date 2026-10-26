# Fleet Shepherd direction — 2026-10-26

Owner requested remote-machine/agent management inside T3. Owner clarified that
**Machine Lab has replaced Orchard**, not the reverse. Keep that local VM/container
product separate; do not revive the Orchard product name based on older source
paths or historical handoffs.

Reviewed public [omarchy-fleet-shepherd](https://github.com/joshuaswarren/omarchy-fleet-shepherd)
HEAD `b39cf962dcbbae397c1d21f4267c24ab49e5ddbc`, MIT. Its v0.1.1 interface
observes Herdr agent state and OMP usage through local/SSH connectors. The bundled
Python helper runs fixed `herdr api snapshot` and `omp stats --json` commands,
with bounded output, deadlines and strict SSH host-key policy. The upstream UI
is Quattro/QML and is not a native GTK app. No upstream code is vendored here yet.

Native delivery belongs in T3: a Remote Machines page with explicit configured
connector identity, per-machine agent/usage state, source time and partial/offline
recovery. Reuse the helper's bounded read-only contract after inspecting its
implementation and retaining its license. Do not replace Machine Lab or install
another shell. Remote mutation is not implemented upstream; any control action
needs a separate explicit adapter and accurate per-action support state.

This is a source review and owner direction, **not an implemented Fleet port**.
Next: finish/install the unified dock menu first, then build the native remote
connector flow using fixtures before connecting real machines. No SSH, remote
configuration, Herdr/OMP installation or remote command was run in this review.
