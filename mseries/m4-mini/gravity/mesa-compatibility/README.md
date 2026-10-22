Versioned source gates for the next M4 research Mesa package. The builder, packager and checker now use revision 5 by default, with explicit
historical revision-4 support. Image/component selection stays on verified Mesa4
until a fresh hosted Mesa5 package passes.

The base is Gravity Mesa 87ac51d, with its existing pinned archive and kernel UAPI.
Three immutable phases apply the eight public PR1 commits, the allocation/error
follow-up and the scoped helper-divergence follow-up. Each phase checks the full
before/after file hashes and patch hash, applies with zero fuzz, and finally
checks all ten changed source files. Fresh replay from the original archive
matches the independently compiled candidate (all six follow-up source hashes).

The manifest retains the historical revision-4 no-patch metadata contract.
Revision 5 requires exact patch/source/test metadata; missing or mixed claims
are rejected. Source/version gates do not authenticate a signer or qualify GPUs.
The complete public PR1 alone is not selected: its demonstrated layered-helper
metadata issue must remain corrected by the later phase.

Full combined driver build, five AGX groups, seven actual-NIR cases, eight
allocation-helper cases and isolated llvmpipe have passed in separate native
receipts. The compatibility source bundle contains exact patches, recipes, tests and
MIT/GPL licenses, ships inside the package and beside the base source archive,
and is retained through image intake. Its extracted module independently replays
all ten source hashes. A fresh hosted package and native
compositor/full tile-pipeline/GPU tests remain open. Future revisions must retain
these snapshots and patch bytes so historical artifacts remain checkable.

Public source and authorship: GravityLinux/mesa PR1 ends at
208d4a484459a12c77bf073362613f842288c2e0; source intake records all eight commit
IDs, Git blobs and URLs. The follow-ups are local MIT changes, with experimental
source/tests under gravity/mesa-candidates and testing/mesa. Original Mesa source
copyright notices and its licenses/MIT are retained in the pinned archive.
The build/validation/testing Python recipes use GPL-3.0-or-later.
