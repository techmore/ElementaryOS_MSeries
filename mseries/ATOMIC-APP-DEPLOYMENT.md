# Feature request: atomic app deployment and faster package delivery

Requested by the owner on 2026-10-14. Status: proposed; backend selection and
implementation remain open. This also informs the requested elementary/Nix spin
evaluation.

Tracking: [GitHub issue #50](https://github.com/techmore/ElementaryOS_MSeries/issues/50).

## Problem

App installs and updates should be quick, recoverable and consistent after an
interrupted download or installation. Current installers mix apt transactions,
Flatpak installs and direct extraction into active app directories. For example,
CodexBar and Signal overwrite files in their current installation directories.
An interrupted update can therefore leave a partial app installation.

The owner reports that the package manager is very slow and wants alternatives
considered. The current elementary OS 9 environment has `/usr/bin/apt`; `apk`
was not found. Track the slowdown against apt unless the owner identifies a
separate Alpine/apk environment. The existing installer batch also repeats
`apt-get update` in individual installers, which is an overhead candidate,
not yet a measured explanation for the reported delay.

## Required behavior

- Stage and verify an entire app release before making it active. Verification
  covers architecture, version and publisher signature or pinned digest, with
  provenance recorded alongside the release.
- Activate each app in one atomic operation on the same filesystem. Desktop
  launchers, icons and service entry points resolve through that app's selected
  release so users cannot launch a mixture of old and new files.
- Keep the previous working release and offer an explicit rollback command or
  UI action. Failed activation/health checks restore the previous selection.
- Preserve the working release after interrupted downloads, extraction failure,
  disk exhaustion or process termination. Resume/retry must be safe.
- Serialize concurrent updates to the same app and provide inspectable status,
  version history and failure logs. Cancellation must leave a usable app.
- Keep user documents, credentials and mutable app data outside release trees.
  Binary rollback does not undo data migrations: apps need compatible data or a
  deliberate backup/restore plan before promising rollback across a migration.
- Support aarch64, Pantheon launchers, portals and per-user services. Routine
  user app updates should run without administrator authentication.
- Retain rollback targets during cleanup. Never prune a running or selected
  release. Expose storage use and a controlled way to remove older releases.

Per-app atomic activation is the initial requirement. A coordinated update of
multiple apps requires one profile-generation switch; sequential independent
app updates must not be described as an atomic batch.

## Backends to evaluate

| Option | Fit | Evidence still required |
|---|---|---|
| Flatpak/OSTree | Desktop apps, existing runtimes, content-addressed releases and sandbox/portal integration | ARM64 availability and publisher status for the actual apps; rollback availability from configured remotes; runtime download size and desktop integration |
| Nix profiles | Versioned generations and rollback for CLI tools and potentially desktop apps; candidate for the elementary/Nix direction | ARM64 binary-cache coverage, cold install/build time, storage use, Pantheon/graphics integration and credential/service handling |
| Versioned upstream release bundles | Apps such as the existing signed Signal ARM64 AppImage and CodexBar binaries when no suitable packaged backend exists | An immutable release directory, atomic selector, locking, health check, rollback and integration lifecycle; prefer existing tooling where it fits |

Evaluate app delivery separately from replacing the Ubuntu base package manager.
APT/dpkg currently owns Pantheon and native OS dependencies. Moving those to a
different distribution/package format requires a separate system architecture
decision; installing apk does not migrate the existing Debian package database.
Base-system atomic updates remain a separate requirement from atomic app updates.

## Implementation milestones

1. Inventory current apps and how each is installed. Record license,
   publisher/source, architecture, runtime dependencies and migration needs.
2. Measure the current workflow: repository refresh, resolution, download,
   unpack/configure/triggers and total elapsed time. Record cold/warm caches,
   network conditions, bytes transferred and disk usage on the M1 Pro.
3. Compare the eligible Flatpak and Nix paths using the same app/workload. Avoid
   repeated metadata refresh in one installer batch; measure that change too.
   Do not claim a backend is faster before comparing actual results.
4. Select and document the backend per app. Prototype install, update and
   rollback on one existing app before migrating the rest.
5. Qualify failed downloads, failed verification, interrupted extraction,
   failed launch, concurrent updates, rollback and data-migration behavior.
6. Wire the selected approach into manual post-install and firstboot/user setup,
   then confirm that a fresh install and an upgraded install converge on the
   same declared app set. Retain recovery for the prior installation method.

## Acceptance evidence

- Fault injection before and during activation leaves either the complete old
  release or the complete new release selected, never a partial installation.
- A real ARM64 desktop app launches after install/update and after rollback;
  its launcher, icons and user service refer to the selected version.
- Two concurrent updates cannot corrupt release selection or app state.
- Cleanup preserves current/previous releases and user data.
- Published timing and storage results compare the baseline with the chosen
  backend. Faster delivery and atomicity are evaluated independently.

## Primary references

- [Flatpak architecture and OSTree](https://docs.flatpak.org/en/latest/under-the-hood.html)
- [Flatpak command reference](https://docs.flatpak.org/en/latest/flatpak-command-reference.html)
- [Nix profile generations](https://nix.dev/manual/nix/2.18/command-ref/new-cli/nix3-profile)
- [Nix profile rollback](https://nix.dev/manual/nix/2.30/command-ref/new-cli/nix3-profile-rollback.html)
