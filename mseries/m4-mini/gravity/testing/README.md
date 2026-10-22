# Separate scheduler KUnit candidate

The optional patch adapts Aurora 0d1871c's three poisoned-storage/delayed-fence
cases to Gravity's older JobImpl interface. Copyright/license follows the
upstream GPL-2.0 OR MIT file; the patch header retains the immutable origin.
It factors initialization to inject dirty allocation and exposes the existing
C NO_HANG status only for KUnit's fake backend. Real M4 timeout behavior is
not changed by this test patch.

This directory is not applied by build-kernel.py or included as an active
production compatibility patch. prepare-scheduler-kunit.py creates a distinct
source tree with the reviewed production patches followed by this test patch.
Use the normal ARM64 KUnit QEMU runner with no network/storage,
and matching compiler/rust-src. Record actual acceleration separately; KUnit
provides a default backend fallback list. The DRM scheduler's KUnit selector is needed
because DRM_SCHED is hidden Kconfig state.

Test intent: dirty scheduler flags, repeated timeout with late completion,
and out-of-order completions/teardown. Passing these does not validate all
older wrapper ownership/aliasing/NoDevice cases or physical M4 hardware.
Compilation and actual TAP/JSON results must be recorded separately.

The older faux registration exposes Device<Normal>; tests use that actual type.
The test patch also adds the missing Debug bound to the existing KUnit-only
iosys_map assertion helper so the full Rust KUnit library can compile.
No assertion or runtime check is removed.

`nodevice-diagnostic.patch` is an additional opt-in diagnostic after the normal
test patch. It is not selected by the testing manifest or production builder.
It reproduces the missing NoDevice cleanup with the initialization fix present.

`nodevice-retention-diagnostic.patch` is an alternative combined diagnostic
after the normal test patch (do not also apply nodevice-diagnostic.patch).
It adapts Aurora 0f89327 C retention and opts the test Rust backend in. Four
QEMU cases pass; production ownership/aliasing review and full GPU build remain
open. Neither diagnostic is selected by a build manifest.

`nodevice-retention-boundaries.patch` supersedes the four-case diagnostic as an
optional combined experiment after the normal test patch. It adds completion
inside the timeout callback and unfinished-job teardown followed by a late
parent signal. All six cases pass on 2-vCPU generic ARM64 QEMU. The test source
was restored. This does not prove mutable callback aliasing or allocation lifetime.

The optional NoDevice diagnostic patches above describe the historical r3
source lane and must not be layered on the current r4 recipe, which already
contains retention. The normal three-case testing manifest still applies after
r4. Six-case associated-constant API evidence is retained in the API receipt;
a current-recipe six-case test patch is a follow-up.
