# Unpromoted matched final cancellation candidate

After revision-4 compatibility and owner/module/disjoint-timeout layers, port
Aurora c9be905 accounting and d1ebc54 stop removal, using the parent-synchronized
field-only cancellation callback from ed55042. Removing a hardware parent
callback under its lock either prevents it or joins the running callback.
Cancellation then accounts only the unfinished job it owns; a legacy detached
parent's credits are not returned twice, and existing completion errors survive.
Finalization calls fini directly, with the prerequisite permanent work drain.
M4 still retains any hardware-owned resources independently until its worker ends.

Actual M4/legacy driver, Rust core and both C scheduler objects compile. Twelve
generic 2-vCPU ARM64 QEMU cases pass. Three new cases inspect stable counters
and fence errors for unfinished parents, legacy prior reset-stop, and completed
EIO parents held pending until fini. Each ends at zero credits/score and exactly
one job release; a late signal does not change the result.

The isolated old-cancellation/stop negative fails its score==0 assertion cleanly.
Earlier negative attempts are retained separately: helper assertions initially
bypassed KUnit rewriting, then a broad three-case replay timed out. They are not
claimed as clean results. Helpers now return observations so assertions execute
inside annotated test cases, after helper-owned resources have been dropped.

prepare-scheduler-kunit.py --experimental-teardown selects all four experimental
layers and teardown-kunit.patch from a pinned archive. Its source is byte-identical
to the twelve-case run. The optional negative patch is run only with filter
rust_drm_sched.teardown_accounts_unfinished_parent_once, in a separate QEMU run.
Normal kernel/package/image recipes remain revision 4. Actual module unload,
full combined Image/modules/DTBs/package compilation and native M4 remain open.
