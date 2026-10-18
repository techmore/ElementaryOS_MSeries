# Rust migration lane

This branch is the tracked lane for migrating M-series-owned operating-system
customizations to Rust while following elementary OS and hardware-support
upstreams on a short cadence. Every upstream project and each independently
shipped local component gets its own record and parity decision. The migration
does not replace the Linux kernel, boot chain, elementary OS, Pantheon, or other
large upstream projects wholesale.

## Goals

- Keep upstream changes visible daily and produce a reviewed candidate at least
  weekly; never turn a source update directly into a device update.
- Give each upstream source project its own pin, license/provenance, local
  patch list, update owner, and compatibility status.
- Give each local customization its own migration record and, if selected for
  Rust, its own crate/package, install boundary, and rollback path.
- Require observable behavioral parity before cutover. Record intentional
  enhancements separately so parity and new behavior are independently
  reviewable.
- Preserve elementary's Ubuntu/mkosi packaging and the existing Asahi recovery
  path. Do not import Arch-only package policy as if it were portable.

## What “Rust branch” means

Rust is the preferred implementation language for new M-series-owned services,
tools, and policy code where it improves correctness or maintainability. It is
not a mandate to fork every upstream dependency into Rust. Upstream projects
retain their own languages, repositories, licenses, release cycles, and test
contracts. This branch records and follows each project separately; it does not
vendor a monolithic copy of elementary OS or turn the Linux kernel, m1n1,
systemd, Gala, Wingpanel, GTK, or drivers into local Rust rewrites.

Where a local Rust replacement is justified, keep it in its own crate/package
behind the same CLI, D-Bus, file, or systemd contract as the current component.
This lets upstream pins move independently and lets each port be compared with
the old implementation. A shared Cargo workspace may be added later if the
chosen crates have compatible release and dependency needs; it is not a reason
to couple unrelated components.

## Project register

The register is intentionally per project. Complete it from the repository's
tracked build inputs, `mseries/UPSTREAM-PINS.md`, and the upstream-source audit
before broad conversions begin. “Initial scope” is not a claim that every file
has been inventoried.

| Project/item | Current boundary | Rust decision | Parity and update record |
|---|---|---|---|
| `elementary/os` | Image build, package set, mkosi and sysupdate | Keep upstream source; track and port local integration only | Pin and image-build contract in `UPSTREAM-PINS.md`; daily change detection, weekly candidate review |
| `AsahiLinux/linux` (Fairydust) | Experimental Apple Silicon kernel and local dock/display patches | Keep the upstream kernel language; maintain this branch, package and patch set separately | Per-patch source and hardware gates in `mseries/fairydust/` |
| `omacom/linux-aurora` | Released Apple Silicon kernel candidate and optional enhancements | Keep upstream kernel language; preserve recipe/config/source and Debian boundary | `mseries/aurora/release.json` and `mseries/aurora/enhancements/`; separate package and hardware qualification |
| `omacom/m1n1` | Aurora's matched boot-stage source | Keep upstream source and pin independently from the kernel | Source/package checks and shared `boot.bin` compatibility review; no boot claim without device evidence |
| Asahi U-Boot / firmware and device-tree inputs | Boot and board enablement inputs | Keep each upstream artifact under its own pin and license record | Preserve recovery entry and matched-input provenance; source checks do not count as boot qualification |
| `elementary/panel-network` | Patched network indicator and network-usage integration | Keep upstream panel plugin in its native language; separately evaluate M-series usage daemon | Pinned version/patch admission in `UPSTREAM-PINS.md`; consumer parity and package gate |
| `elementary/wingpanel-indicator-sound` | Factory sound-indicator plugin | Keep upstream plugin language and local patch separate | Source revision, license, patch and consumer hash in `UPSTREAM-PINS.md` |
| `elementary/panel-keyboard` | Factory keyboard-indicator plugin | Keep upstream plugin language and local patch separate | Source revision, license, patch and consumer hash in `UPSTREAM-PINS.md` |
| `elementary/gala` | Pantheon compositor and maintained upstream patches | Keep upstream compositor in its native language | Pin, clean patch application, build and compositor behavior are separate gates |
| M-series Gala drawers plugin | Local Vala plugin and settings schema | Evaluate as an independent local component; no Rust rewrite without a stable plugin API | Compare hotkeys, show/hide, placement, monitor handling and launch behavior |
| `JoseExposito/touchegg` | Optional gesture daemon source | Keep upstream implementation unless a separately scoped replacement is justified | Pinned source archive, license, packaging and gesture qualification in `UPSTREAM-PINS.md` |
| `omacom/libva-v4l2_request` | Optional VA-API bridge for Apple video decode | Keep upstream implementation and its kernel/firmware contract | Pinned source and package checks in `UPSTREAM-PINS.md`; enabled codecs are not hardware qualification |
| `omacom/omarchy-mac-pkgs` | Behavioral reference for Apple hardware support | Do not fork wholesale; translate only justified behavior for Ubuntu/Pantheon | `mseries/PORT-MAP.md`; retain source attribution and license |
| `mseries-power` | Privileged charge/power command and profile policy | Candidate for an independently packaged Rust implementation | Compare CLI, permissions, input validation and writes to existing regression cases before cutover |
| M-series Wi-Fi resume recovery | Root service and helper | Candidate for an independent Rust implementation | Compare hardware gates, retry/exit behavior, systemd ordering and existing regressions |
| Network-usage logger | User service, SQLite state and DNS/network events | Candidate for an independent Rust implementation | Compare event ingestion, persisted totals, privacy behavior and output contract |
| Brightness bridge | D-Bus integration/service | Candidate for an independent Rust implementation | Compare D-Bus names, methods, errors and display behavior before cutover |
| Keyboard-backlight service | M-series sensor and backlight policy | Candidate for an independent Rust implementation | Compare sensor bounds, manual override, lock/lid and suspend behavior before cutover |
| Image/install orchestration | `bin/`, `transform/`, mkosi hooks and installer scripts | Keep shell unless a specific component has a parity-backed replacement case | Preserve resume, status, abort, rollback and failure semantics before any cutover |
| Image/install orchestration | `bin/`, `transform/`, mkosi hooks and installer scripts | Keep shell unless a specific component has a parity-backed replacement case | Preserve resume, status, abort, rollback and failure semantics before any cutover |

For each additional upstream repository or local component, add a row before
changing it. Record at minimum: repository and upstream URL; license; pinned
revision and update signal; downstream files or patches; existing behavior and
public interfaces; parity evidence; enhancement proposals; supported boards;
build/package path; rollback; and current qualification state. Never merge
unreviewed source just because it is newer.

## Conversion contract

Each port follows this sequence:

1. Inventory the exact old implementation, callers, permissions, inputs,
   outputs, service ordering, error handling, and supported hardware.
2. Write behavior-level parity cases from the old implementation and known
   regressions. Capture representative fixtures before rewriting it.
3. Implement one independent Rust component with a narrow contract. Minimize
   dependencies; forbid `unsafe` unless the record explains why and bounds it.
4. Run the same cases against old and new implementations. Record build target,
   package contents, diagnostics, and results. Add security/dependency review
   for shipped crates.
5. Install side by side behind an explicit opt-in or image profile. Confirm
   rollback and run the relevant VM or hardware checks before changing the
   default.
6. Promote only after parity passes and the required hardware qualification is
   recorded. Keep the old implementation through a release/rollback window.
7. Track intentional enhancements in a separate section and separate tests;
   do not let an enhancement conceal a parity regression.

No code port should claim feature parity based only on successful compilation.
For hardware-dependent behavior, report source/unit evidence separately from
device evidence and state when the latter is still missing.

## Upstream update rhythm

- **Daily:** poll each registered upstream for new commits/releases, validate
  pin metadata and license/source availability, and open or refresh a candidate
  report. Do not automatically merge or deploy.
- **Weekly:** review one candidate batch per project; rebase the branch, apply
  local patches cleanly, build affected packages/images, run parity and VM
  admission checks, inspect the diff, and publish a reviewable result.
- **On source breakage:** hold that project's bump in its own record, capture
  the failing revision and blocker, and continue updates for unrelated projects.
- **On device promotion:** require green software checks, a preserved recovery
  route, explicit owner approval for boot/kernel/audio changes, and a recorded
  rollback. A CI build is not a successful boot or hardware result.

Use the existing `mseries/UPSTREAM-PINS.md`, upstream watch tools, CI, and
`mseries/VM-SMOKE-TEST.md`; this lane defines policy and is not itself an
upstream-update automation.

## Initial migration candidates

The previous plan identifies `mseries-power`, Wi-Fi resume recovery, the
network-usage logger, brightness bridge, and keyboard-backlight service as
possible Rust ports. They are candidates, not approved rewrites. Prioritize
after the full register is complete by privilege risk, current defect history,
interface stability, parity testability, and measured maintenance burden. Keep
the GTK launcher/troubleshooter low priority and retain shell build/image glue
unless evidence supports a discrete conversion.

## Current state

- Branch baseline: `origin/main` at `f114d865bfab7ee73610198d5f1b43d1a767581c`.
- This commit establishes scope, per-project tracking, parity gates, and the
  upstream update rhythm only.
- Full source-by-source register, first selected port, daily CI candidate lane,
  and parity evidence are outstanding.
