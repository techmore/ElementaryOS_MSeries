# Elementary M4 compatibility backports

These adaptations are separate from the unchanged Gravity packaging exports.
0001 ports scheduler initialization from Aurora 6c2d17f/0d1871c.
0002 ports opt-in terminal-timeout retention from Aurora 0f89327. The Rust
JobImpl contract defaults to false; only M4 SubmissionJob opts in. Its timeout
marks failure and wakes cleanup without freeing the job. C/reset and legacy
Rust backends retain their defaults. Reinsertion happens after timedout_job
returns, queues completed jobs for cleanup and leaves unfinished jobs reachable
by final cancellation without restarting the terminal watchdog.

The actual Rust core, C scheduler and M4 driver objects compile with 0002;
six generic ARM64 QEMU cases pass through the associated-constant API. Package
revision 4 selects both fixes; full Image/modules/DTBs build is still required.
Revision 3 remains separately identified in package-versions.json, so its
initialization-only receipt is never interpreted as containing retention.

Newer allocation-owner and timeout-aliasing refactors remain separate open
reviews. These changes do not establish native M4 GPU or firmware stability.
