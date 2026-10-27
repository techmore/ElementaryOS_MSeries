# FROZEN: edit in mseries-sdk-apps

The writable source of truth for this directory is
[`techmore/mseries-sdk-apps`](https://github.com/techmore/mseries-sdk-apps) at `mseries/phone-setup`.
This copy is a frozen migration snapshot kept for rollback and reference
(see [REPOSITORY-TOPOLOGY.md](/mseries/REPOSITORY-TOPOLOGY.md), staged transition step 5).

- Cutover revision: `mseries-sdk-apps@40d4445c4414e83da5893500528e088ec599af30` (origin/main, 2026-10-27)
- State at cutover: identical (SDK tree only adds a stray __pycache__)
- Make changes in `mseries-sdk-apps`, not here. A PR that edits this directory fails the
  `Frozen paths guard` check unless it carries the `allow-frozen-edit` label.
- Nothing here has been deleted or moved. Ownership table: [REPO-OWNERSHIP.md](/mseries/REPO-OWNERSHIP.md).
