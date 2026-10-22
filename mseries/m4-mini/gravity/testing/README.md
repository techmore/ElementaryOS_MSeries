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
Use the normal ARM64 KUnit QEMU runner with software TCG, no network/storage,
and matching compiler/rust-src. The DRM scheduler's KUnit selector is needed
because DRM_SCHED is hidden Kconfig state.

Test intent: dirty scheduler flags, repeated timeout with late completion,
and out-of-order completions/teardown. Passing these does not validate all
older wrapper ownership/aliasing/NoDevice cases or physical M4 hardware.
Compilation and actual TAP/JSON results must be recorded separately.

The older faux registration exposes Device<Normal>; tests use that actual type.
The test patch also adds the missing Debug bound to the existing KUnit-only
iosys_map assertion helper so the full Rust KUnit library can compile.
No assertion or runtime check is removed.
