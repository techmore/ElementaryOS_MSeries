# Elementary M4 compatibility backports

These public-source adaptations are separate from the unchanged Gravity ARM64
packaging exports. The current research package is revision 5:

| Patch | Purpose / upstream |
| --- | --- |
| 0001 | Initialize scheduler storage; Aurora 6c2d17f / 0d1871c |
| 0002 | Retain terminal-timeout M4 jobs; Aurora 0f89327 |
| 0003 | Separate finalization owner from job-held allocation; Aurora 7ba04b6 |
| 0004 | Pin callback modules, propagate DRM fops owner, permanently drain work; Aurora c163a8d |
| 0005 | Independent timeout state and field-only callback borrows; Aurora 0f89327 |
| 0006 | Parent-synchronized cancellation, exact accounting and paired stop removal; Aurora c9be905 / d1ebc54, current ed55042 callback |

Actual M4 and legacy Asahi driver objects, Rust core and both C scheduler
objects compile with the combined recipe. Twelve generic ARM64 QEMU cases pass;
expected-failure controls cover initialization, allocation reference, work disable
and the old cancellation accounting. Fresh default KUnit preparation reproduces
the tested scheduler source. Full r5 kernel building, real module lifetime and
native M4 firmware/hardware qualification remain open.

package-versions.json binds r3 (initialization), r4 (initialization/retention) and
r5 (all six changes) to distinct immutable patch sets. resulting-files-by-version
preserves historical source gates too. No older package is credited with newer
fixes. Historical experimental recipes start from r4; normal preparation selects
all six current patches and the twelve-case test recipe.

A separate loadable C-backend QEMU fixture now verifies shared callback-module
retention and unload after cleanup, with a safe missing-owner negative. It does
not establish M4 Execution/Rust driver or firmware teardown; that worker boundary
is tracked separately.
