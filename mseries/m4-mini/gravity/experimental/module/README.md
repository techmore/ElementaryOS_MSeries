# Unpromoted callback module and work lifetime candidate

Current status: these changes are selected unchanged in the revision-5 research
compatibility recipe. This directory reproduces the historical r4-base stage;
the scoped results and qualification limits below describe that staged run.

Apply after revision-4 compatibility and the experimental owner split. This
ports the shared parts of Aurora c163a8d: scheduler ops identify their callback
module, entity-kill work pins it before leaving entity ownership and releases
it only after free_job returns, and finalization disables/drains both scheduler
work items permanently. Disable/drain prevents a completion from requeueing work
after cancellation. It does not itself establish firmware quiescence.

The older Rust DRM wrapper also had a NULL fops.owner. The candidate adds a
Driver::MODULE default, feeds it through GEM_FOPS and sets it for the M4 and
legacy Asahi drivers. Gravity drm_prime.c:922 copies this fops owner into the
DMA-buf export owner, so open DRM files and exported buffers retain backend code.
Both job backends also declare their callback module. The G17 cleanup queue
and unrelated changes from the large upstream commit are not imported.

Actual M4/legacy Asahi driver, Rust core, sched_main and sched_entity objects
compile. Eight generic 2-vCPU ARM64 QEMU cases pass. The new empty-scheduler
case reads stable off-queue disable depths after finalization while retaining
only the allocation; both depths are one. Removing the two disables fails
that assertion. This observes permanent-disable state, not every concurrent
completion interleaving. The fake backend has MODULE=None: actual loadable
module refcounts/unload and native M4 GPU runtime are NOT tested.

prepare-scheduler-kunit.py --experimental-module creates a fresh isolated tree,
selecting the owner and module candidates followed by module-kunit.patch.
The fresh source exactly matches the eight-case run. Use normal ARM64 KUnit,
matching Rust 1.99 rust-src/clang21, two QEMU vCPUs and no network/storage.
The optional negative patch is selected manually for only the finalization
state case; it never enters normal manifests.

The staged run used revision 4; current research packaging selects revision 5. Mutable callback
aliasing, actual module unload and firmware/native teardown remain open.
