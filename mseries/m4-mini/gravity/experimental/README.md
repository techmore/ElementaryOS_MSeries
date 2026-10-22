# Unpromoted scheduler integration candidates

The retention patch adapts Aurora 0f89327 to Gravity 4fc326f after compatibility
0001. Unlike the diagnostic patch, it adds a default-false JobImpl associated
constant and opts in only the M4 SubmissionJob backend. C/reset backends and
legacy Rust jobs keep their existing defaults. M4 timed_out marks failure and
wakes the worker; it does not free the job or signal the lifetime fence there.

This directory is excluded from build-kernel.py and all package manifests.
The exact production-API candidate is compiling rust/kernel.o, asahi_m4.o and
sched_main.o against the preserved full M4 configuration in a separate local
source/output tree. That compile is pending; it is not a full kernel/package
build or native hardware test. Six fake-backend QEMU tests support the C
retention mechanism, but the backend API integration needs its own evidence.
Allocation-owner and mutable-callback aliasing reviews remain open.
