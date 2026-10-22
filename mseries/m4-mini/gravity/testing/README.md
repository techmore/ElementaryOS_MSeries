# Scheduler KUnit recipes

The current revision-5 default selects 0003-scheduler-lifetime-kunit.patch after
all six compatibility patches. Its twelve generic ARM64 QEMU cases cover dirty
storage, repeated timeout/late/out-of-order completion, NoDevice completion and
teardown, deferred allocation lifetime, permanent work disable, overlapping
submission/timeout, exact final accounting with unfinished or legacy-detached
parents, and preservation of completed EIO. Test-only initialization factoring,
Drop probes, forced entity fini and the faux backend never enter kernel packages.

prepare-scheduler-kunit.py creates a new isolated source tree. Use matching
Rust 1.99 rust-src, clang21/libclang, two QEMU vCPUs and no network/storage.
The runner offers accelerator fallbacks; record actual acceleration rather than
assuming TCG. Tests do not exercise M4 firmware, graphical sessions or actual
loadable-module refcounts/unload.

Earlier 0001/0002 test patches and optional diagnostics are historical r3/r4
materials; do not layer them on the r5 default. The --experimental-owner,
--experimental-module, --experimental-alias and --experimental-teardown options
reproduce staged 7/8/9/12-case recipes from the frozen r4 base. Those public
patches are now also selected by r5 compatibility.

Negative controls run in separate QEMU instances with their exact single-case
filters. The old broad teardown negative timed out; an earlier helper assertion
bypassed KUnit rewriting. Those attempts are not clean results. Helpers now
return observations; assertions remain in annotated test bodies.
