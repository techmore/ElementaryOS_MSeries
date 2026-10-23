# Elementary M4 compatibility backports

These public-source adaptations are separate from the unchanged Gravity ARM64
packaging exports. Revision 5 remains the last built package. Revision 6 is the new source candidate; its full package build is pending:

| Patch | Purpose / upstream |
| --- | --- |
| 0001 | Initialize scheduler storage; Aurora 6c2d17f / 0d1871c |
| 0002 | Retain terminal-timeout M4 jobs; Aurora 0f89327 |
| 0003 | Separate finalization owner from job-held allocation; Aurora 7ba04b6 |
| 0004 | Pin callback modules, propagate DRM fops owner, permanently drain work; Aurora c163a8d |
| 0005 | Independent timeout state and field-only callback borrows; Aurora 0f89327 |
| 0006 | Parent-synchronized cancellation, exact accounting and paired stop removal; Aurora c9be905 / d1ebc54, current ed55042 callback |
| 0007 | M4+ register-preserving WFI and forced WFxT-off override; Aurora c407e1097ba74b464982c66483ba507a50ed927a / 3f0822d73dbe341d8073a9db05b316cb564dc92f, adapted to Gravity’s M4 Donan part names |

Actual M4 and legacy Asahi driver objects, Rust core and both C scheduler
objects compile with the combined recipe. Twelve generic ARM64 QEMU cases pass;
expected-failure controls cover initialization, allocation reference, work disable
and the old cancellation accounting. Fresh default KUnit preparation reproduces
the tested scheduler source. The full R5 kernel package now builds and passes
independent inspection; real module lifetime and native M4 firmware/hardware
qualification remain open. R6 build and package inspection are pending.

package-versions.json binds r3 (initialization), r4 (initialization/retention),
r5 (all six scheduler changes), and r6 (those changes plus the M4 WFI/WFxT backport)
to distinct immutable patch sets. The R6 target config also requires built-in
ISO9660 and SCSI CD-ROM drivers after the R5 live ISO could not mount its raw
USB medium in QEMU, and a built-in Apple watchdog driver after Aurora's latest
shared Asahi config change to take over the boot watchdog before a slow initramfs
can reset the machine. resulting-files-by-version
preserves historical source gates too. No older package is credited with newer
fixes. Historical experimental recipes start from r4; normal preparation selects
all seven R6 patches; R6 source application is checked against the pinned Gravity tree,
but native idle behavior and the hosted R6 package build remain unqualified.

A separate loadable C-backend QEMU fixture now verifies shared callback-module
retention and unload after cleanup, with a safe missing-owner negative. It does
not establish M4 Execution/Rust driver or firmware teardown; that worker boundary
is tracked separately.
