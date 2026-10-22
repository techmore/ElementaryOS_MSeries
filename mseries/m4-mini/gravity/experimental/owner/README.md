# Unpromoted scheduler allocation-owner candidate

Current status: these changes are selected unchanged in the revision-5 research
compatibility recipe. This directory reproduces the historical r4-base stage;
the scoped results and qualification limits below describe that staged run.

Derived from Aurora 7ba04b6 after the current revision-4 compatibility recipe.
Scheduler handles and entities own finalization; each job retains only the
allocation. This prevents deferred dependency cleanup from using freed scheduler
storage without creating a cycle that prevents finalization. Stop/fini ordering
is preserved pending its separate cancellation review.

Actual M4 driver, Rust core and C scheduler object compilation succeeds. Seven
generic 2-vCPU ARM64 QEMU cases pass. The new case calls C entity_fini to model
forced killed-entity cleanup without the convenience destroy's flush wait. It
keeps a job blocked on a fence, drops entity/scheduler owners, then signals the
dependency and verifies exactly one job and allocation release. Test-only Drop
instrumentation observes allocation release without retaining the allocation.
Removing the job-held Arc fails the early-release assertion. The negative test
avoids signalling its dependency after failure to avoid a deliberate use-after-free.
This is not native M4 GPU or complete scheduler lifetime qualification.

Use prepare-scheduler-kunit.py --experimental-owner with the pinned source archive
to create a new isolated tree. That selects the owner patch and owner-kunit.patch
instead of the normal testing manifest. Run the ARM64 KUnit runner with matching
Rust 1.99 rust-src, clang 21, two QEMU vCPUs, no network/storage and rust_drm_sched
filter. The optional negative patch is applied only for the one deferred-lifetime
case in another test run. It is never selected automatically.

The directory is historical; its identical patch is now in r5 compatibility.
Mutable callback aliasing and module callback/code lifetime remain open.
