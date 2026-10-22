Revision 6 is the default research build/package recipe; selected image Mesa
remains verified revision 4 pending fresh revision-6 package checks. Revision 5
has passed hosted build/download checks and retains its immutable snapshot.

The base is Gravity Mesa 87ac51d with the original archive and matched kernel
UAPI. Four exact phases apply public PR1, rodata error handling, scoped NIR
workgroup-ID divergence and native Apple9 external-to-2D normalization. Each
phase checks patch and before/after hashes with zero fuzz. Final source gates
also check unchanged baseline files. Explicit revision 5 applies only its first
three phases and rejects a mixed newer native compiler source.

Revision 6 adds 24 constant/dynamic compiler byte-and-binding comparisons across
direct and sampler-state paths and four malformed external controls. These run
against the freshly built integrated compiler library. Targeted candidate tests
pass, and the original-object control rejects 20 positive cases. Existing five
AGX groups, seven NIR cases, eight allocation-helper cases and isolated llvmpipe
remain required. No compiler-only test qualifies EGL image import or GPU output.

The corresponding-source bundle retains exact patches, full build/package/check
recipes, all supplemental test sources and MIT/GPL licenses. Source bundle
creation explicitly selects the version; old v5 artifacts remain verifiable.
Fresh replay and v5/v6 bundle roundtrips pass. Full revision-6 build/package and
native compositor, YUV, synchronization and GPU tests remain open.

Public PR1 ends at 208d4a484459a12c77bf073362613f842288c2e0. Intake records
all eight commits, Git blobs and URLs. Follow-ups retain Mesa MIT attribution;
Python recipes are GPL-3.0-or-later. The base archive retains source copyright
notices and licenses/MIT. Version snapshots and patch bytes must remain frozen
when later research revisions are added.
