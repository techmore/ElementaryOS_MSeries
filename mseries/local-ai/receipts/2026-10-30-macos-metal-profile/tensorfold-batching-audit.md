# TensorFold Vulkan batching source check — 2026-10-30

## Discovery

[TensorFold PR #1561](https://github.com/ashhart/TensorFold/pull/1561) exposes the previously described batching work in a public fork. As checked on October 30, the PR is **closed, unmerged and draft**; its author says it was opened early and the batching work is intended to follow the stacked engine PRs. It is not a merged release or a tested downstream update. The older references describing it as unpublished reflect the prior observation, not its current visibility.

The public PR head was `a86eff2561ce1970d4edfdf67ff970e2785dcb88`; its immediate parent was `3992d9a` (a probe timer), whose parent was engine head `f280f25`. The batching commit changes five source files: engine/backend, command handling, dispatch and greedy. Upstream describes replacing approximately 496 submissions and fence waits per decode token with one command buffer and one fence wait, retaining per-dispatch descriptor sets and distinct staging slices. Treat the PR's performance and byte-identity claims as upstream-reported on its tested M1, M1 Max and M2 Max, not an M1 Pro result. Its reported full host matrix included 37 failures in an existing host snapshot test group, also reproduced on its own base; three Vulkan host groups passed. The server was not tested over that change.

## Compatibility with the installed downstream pin

The installed opt-in package is built from `b3ab9ba217a80c63fcc48f7643ddfe339a8f4bdc`. GitHub's compare of that revision and the public batching head reports divergent history (35 ahead, 165 behind, merge base `dd0a9cc5`); ahead/behind are graph counts, not patch equivalence. A direct tree comparison includes many non-batching differences, so switching to the old head would replace more than a batching change.

A local **read-only** applicability check exported the exact one-commit batching diff `3992d9a..a86eff2` and ran `git apply --check` against a clean archive of installed source `b3ab9ba`. The patch did not apply cleanly: `engine.zig` and `greedy.zig` failed to match; individual checks for `backend.zig`, `commands.zig` and `dispatch.zig` applied. The unbatched source shows substantial documentation/comment reflow between these histories; textual rejection alone does not prove a semantic conflict. No patch was applied, compiled, installed or run, and no Git branch, GPU, kernel, service or default was changed.

## Next qualification gate

Review the exact upstream batching commit against `b3ab9ba`, including comment/context drift and any functional differences, then prepare an isolated candidate while retaining the pinned installed build. Validate descriptor lifetimes, staging slices, barriers, reset/poison and failure handling with host tests and the project's GPU stage/contract gates. Run matched Qwen3.5 2B old/new tests with the same prompt and measurement boundary, alternating at least three pairs, and retain token IDs, teacher-forced logits, submission counts, timing, memory/thermal observations and desktop responsiveness. Compare with the existing exact-ID failures and near-tie findings; do not substitute upstream M1/M1 Max numbers for M1 Pro results. No promotion before those gates pass.
