# M4 MLX preflight investigation, 2026-10-30

The [preflight](2026-10-30-m4-mlx-preflight.md) returned zero for `1 + 1`
and the kernel reported unretired GPU work ten seconds later. Its captured
output has no dispatch trace, so it does not identify which runtime path ran
or prove why the GPU failed to retire work.

A source review of the Omarchy MLX backend found two independent completion
hazards. A started GPU event alone does not prove shader completion; candidate
commit `a94172f32385041223df71006bfe9a15b0e15f80` stops the recovery branch
from publishing a completion on that basis. Candidate commit
`6a107cfbf632c5d612cc31fb94d096a59c5129bf` stops a CPU event from advancing
the separate shared GPU completion timeline beyond unfinished work. A host
regression against the actual function fails before and passes after the latter
change. The candidate CPU-disabled MLX static library compiled and linked from
pinned MLX source `9c3d35571ac450a8ecf5c17b4d0e3fac52c08bc8`; this is not a
GPU runtime test. The ordinary upstream MLX graph appears to signal each event
from its producer stream, so it is not established that the second path ran
in the failed smoke.

Neither change establishes recovery of the observed M4 GPU timeout. Review also
identified unresolved ordering on a single timeline semaphore shared by CPU and
queued GPU signals, and a retry that can replay a command buffer without proof
its original submission retired. These need a complete synchronization and
lifetime design. No new GPU workload was run for this investigation.
