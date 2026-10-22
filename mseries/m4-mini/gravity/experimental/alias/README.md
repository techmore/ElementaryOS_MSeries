# Unpromoted disjoint timeout/submission state candidate

Current status: these changes are selected unchanged in the revision-5 research
compatibility recipe. This directory reproduces the historical r4-base stage;
the scoped results and qualification limits below describe that staged run.

Derived from Aurora 0f89327 after revision-4 compatibility, owner and module
candidates. Job stores independently owned inner and TimeoutData. Submission,
prepare and cancellation borrow only inner; timeout borrows only TimeoutData.
The C envelope is accessed through raw pointers. M4 retains its Execution Arc
for timeout independently; legacy Asahi retains device/ID plus a shared atomic
ran flag so its diagnostic remains accurate without borrowing submission state.
TimeoutData is constructed before C ownership and dropped normally on init error.

Actual M4 and legacy driver/Rust core/C scheduler objects compile. Nine generic
2-vCPU ARM64 QEMU cases pass. The new case holds run's mutable submission state
while sleeping and waits for timeout to execute before allowing run to return;
submission mutations, completion and exactly-once cleanup are checked. It
exercises actual callback overlap, but is not an exhaustive Rust memory-model
proof or a native GPU result. The fake backend does not exercise module unload.

prepare-scheduler-kunit.py --experimental-alias selects all three experimental
layers, followed by alias-kunit.patch, from the pinned archive into a new tree.
The resulting scheduler source is byte-identical to the nine-case run. Use
normal ARM64 KUnit, matching Rust 1.99 rust-src/clang21, two QEMU vCPUs and no
network/storage. The earlier initialization, lifetime and work-disable negative
controls remain separate evidence; no claim is made that older aliasing code
must fail a functional test rather than violating a reference contract.

The staged run used revision 4; current research packaging selects revision 5. Final teardown
cancellation/accounting and actual loadable-module lifetime need further review
before the combined candidate becomes a packaged full kernel build.
