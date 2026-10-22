This unselected follow-up applies after Gravity Mesa PR1 at
`208d4a484459a12c77bf073362613f842288c2e0`. Its combined manifest also requires the
separate rodata-error candidate. Neither is selected by the default Mesa recipe.

The PR's blanket marker clears divergence of every helper value. The actual
layered tile-store helper reads layer ID, which normal NIR analysis classifies
as divergent with the driver's default options. The retained real-NIR diagnostic
confirms that PR1 clears this classification while claiming valid metadata.
This is an IR finding; no rendered-output failure was reproduced.

This patch replaces that bypass with an explicit compiler option permitting a
uniform workgroup-ID read in fragment tile helpers. Other fragment inputs retain
normal divergence analysis. Shared-base/workgroup-index intrinsics do not receive
that permission. The Asahi selector is limited to fragment programs containing
the known workgroup-ID read. Normal uniform-atomic/subgroup passes are restored.
Options are copied for one compiler invocation and the original pointer is
restored before returning; no stack options pointer escapes the compile.

Before applying, check all manifest before hashes. Apply this five-file patch
and the separately gated rodata patch with zero fuzz, then check all six after
hashes. Source roundtrip checks passed; full combined compilation is running.
Do not mutate a source tree while it builds or call a pending test a pass.

The actual-NIR test runner is `testing/mesa/test-helper-divergence.py` under
mseries/m4-mini. It takes `--mesa-workspace`, `--candidate-manifest` and a new
`--output`. Four planned semantic cases cover helper layer/group propagation,
ordinary fragment input and compute workgroup behavior. Three expected assertion
controls require fragment workgroup-ID to opt in and keep shared-base/index
reads rejected. It uses built NIR libraries, without creating a GPU device.
These tests and full-driver results remain pending until receipts are recorded.
Native compositor imports, GPU output and hardware qualification remain open.
