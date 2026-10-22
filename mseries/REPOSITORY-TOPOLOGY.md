# Repository topology: project hub and focused source repositories

## Direction

Keep `techmore/ElementaryOS_MSeries` as the unifying project repository. It
continues to own the project overview, GitHub Pages site, roadmap, capability
ledger, integration records, release coordination, and the combined build and
qualification view.

As the codebase stabilizes, split source ownership into three focused
repositories:

| Repository | Owns |
| --- | --- |
| `ElementaryOS_MSeries-Kernel` | Downstream kernel source pins, patch series, package recipes, Apple Silicon hardware support, and kernel qualification. |
| `ElementaryOS_MSeries-OS` | The elementary OS image, installer and update composition, Pantheon shell/compositor, system integration, themes, policies, and OS services. |
| `ElementaryOS_MSeries-Apps` | The Rust Pantheon SDK, typed app-side OS API clients, first-party GTK/Granite applications, app packaging, and app-level qualification. |

The existing names are proposals; create remotes only after the boundaries,
build entry points, ownership and permission model are agreed. This document
does not create repositories or transfer source.

## Staged transition

1. Keep the current checkout complete and authoritative while the component
   boundaries and build dependencies are mapped.
2. Create each focused repository with source history and the build/package
   workflows needed to validate it independently. Leave the corresponding
   source in this hub checkout during this proving period.
3. Have the hub's integration workflow build against immutable component
   revisions and produce one combined release and qualification record.
4. Confirm Pages and cross-repository source links resolve from the hub; keep
   user-facing docs and the project capability ledger centralized here.
5. After a component's CI, package, integration and hardware gates pass, mark
   its hub copy as a frozen migration snapshot and choose a cutover revision.
   Do not delete the snapshot as part of the first cutover.
6. Retire duplicate working copies only after a later release proves that the
   focused repo is the maintained source and the hub still reproduces the
   combined project view.

At every stage there should be one clearly named writable source of truth for
each component. During the proving period, the old copy remains available for
rollback and reference; the hub manifest records which focused revision is
being validated.

## Cross-repository contracts

- App frontends depend on versioned OS service APIs and package interfaces,
  not filesystem paths into the OS repository.
- The OS repository owns the service provider and the compatibility contract;
  the Apps repository owns typed SDK clients and shared UI patterns. The two
  are released against an explicit API version range. For example, the OS
  owns update policy and privileged staging/rollback, while Software Updates
  uses the SDK's typed contract and owns the confirmation and status UI.
- Extract contracts from implementations when the repositories split. The
  current `mseries-update-core` combines the typed update contract with a root
  helper binary; keep its source intact in this hub during the transition and
  separate the OS-owned helper from the app-facing contract only at a reviewed
  cutover revision.
- The OS consumes kernel packages by immutable version and checksum; it does
  not build against a moving kernel branch.
- The Apps repo consumes the SDK as a versioned workspace crate or released
  package. Each app pins backend/API versions that the OS repo provides.
- The hub records component revisions, checksums, release status and known
  qualification limits. Integrated CI rejects a missing pin or a mutable
  branch reference.
- Public Pages are generated and published from the hub. Component READMEs
  remain useful for developers, and link back to the project's overview and
  current qualification record.
- Private components such as Torrential keep their existing visibility and
  license constraints; hub links and release manifests do not make their
  source or binaries public.

## Independent app releases

Once an app's native port passes its feature, accessibility, packaging and
platform acceptance gates, it can ship on its own version and release cadence.
The Apps repository owns each app version and artifact; the hub records the
release, source revision, checksum, SDK version, supported OS API range,
architecture and qualification receipt. The OS image consumes a pinned app
release rather than a moving branch. A native port can be released before it
is selected for the default image, and each app can keep its own release pace.
The SDK itself follows semantic versioning so app releases can state the
toolkit API range they support. Private apps such as Torrential retain their
visibility and licensing limits throughout this process.

## Current state

The code remains in the current monorepo. The Rust Pantheon SDK and apps are in
`rust/`; image, compositor, kernel integration, app source, release workflow,
and Pages content are still present alongside one another. The first SDK PR is
being developed here. No source has been moved or removed as part of the
repository-topology proposal.
