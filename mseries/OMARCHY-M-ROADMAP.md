# Omarchy M integration, then Rust migration

Owner direction, 2026-10-14: follow the Omarchy M people and projects, merge their
work into ElementaryOS_MSeries, then convert the implementation to Rust and
measure performance. This sequence governs the integration roadmap.

Announcement: [Introducing Omarchy M](https://omarchy.org/news/2026/09/introducing-omarchy-m/).
Source roster: [official team](https://omarchy.org/teams/).
Machine-readable tracking baseline: [upstreams/omarchy-m.json](upstreams/omarchy-m.json).
Observed revisions are discovery/audit baselines, not new build pins or proof
that the code has been imported, compiled or qualified on our hardware.

Daily source monitoring is active in this Codex chat at 10:00 America/New_York.
It checks public changes against this roster and reports meaningful actionable
changes only. Monitoring is read-only; integration follows the review gates below.

## 1. Follow the people and source projects

| People / area | Project to follow | Elementary work |
|---|---|---|
| Naeem Malik, Scott Jones: Apple integration | [omarchy-mac-pkgs](https://github.com/omacom/omarchy-mac-pkgs) | Audit all Apple package changes and translate hardware fixes to Ubuntu/Pantheon |
| Marcelo Alcantara: native installer | [omarchy-mac-installer](https://github.com/omacom/omarchy-mac-installer) | Signed release selection, install/repair UX and recovery design |
| Eduardo Martinez: preview | [try-omarchy](https://github.com/omacom/try-omarchy) | VM preview, guest integration and packaging; track separately from native hardware support |
| Jaidip Subedi: USB-C display | [dp-altmode-t8112](https://github.com/subedijaidip/dp-altmode-t8112) | Study driver/HPD work, then assess M1 Pro equivalents before importing model-specific code |
| Joshua Warren: MLX | [omarchy-mlx](https://github.com/joshuaswarren/omarchy-mlx) | ARM64/Vulkan MLX integration and measured GPU workloads |
| Desktop/package team | [omarchy](https://github.com/omacom/omarchy) | Inventory desktop features and port behavior to Pantheon |
| Kernel contributors | [AsahiLinux/linux fairydust](https://github.com/AsahiLinux/linux/tree/fairydust) | Trace public driver patches and model coverage; retain our qualified kernel/recovery policy |

Also follow the source publications of Dj (GPU/SEP), Ryan Murray (kernel and
macOS tracing), Miguel Cruz (M5/N1/video), Liam (input/power/audio), Eryk
Wieliczko (M4), Shun Li (ARM64 packaging), Shawn Yeager and Randy (Intel/T2),
and Jon Kinney (coordination). Their social/team profiles are discovery
pointers. Record a concrete public repository, revision and license before
treating a claimed implementation as available for integration.

The former MX fork is feature-frozen according to its
[README](https://github.com/maralcbr/omarchy-mx-mac). Track maintained projects
for new work; retain MX as historical context and compare fixes as appropriate.

## 2. Merge and port the upstream work

Inventory **every** applicable hardware fix, driver, installer feature, desktop
enhancement, app and packaging change. For each item, record source revision,
license/attribution, supported models, elementary equivalent, dependency changes,
validation evidence and rollback. Use the existing [port map](PORT-MAP.md) and
[pins](UPSTREAM-PINS.md), then land reviewed batches on `main`.

Track explicit states: discovered → source obtained → reviewed → ported → built
→ hardware qualified. Missing public source stays open. Arch/pacman/Hyprland
code needs translation to our Ubuntu/Pantheon contracts; a verbatim merge does
not establish functional integration. Preserve third-party licenses and obtain
redistribution permission where required.

Priority areas are installer/recovery, input and USB networking, USB-C displays,
power/audio, Touch ID, video/GPU, MLX, desktop parity and atomic app delivery.
Complete both manual/transform and factory-image packaging, including the
existing overlay-pruning and `/usr`-only sysupdate gaps. Source import and
hardware qualification are separate gates.

Current evidence limits:

- The announcement's full M1/M2 compatibility list is a release target.
- The linked USB-C repository targets M2 Air `t8112/j413`; its predecessor
  targets base M1 `t8103/j293`. Neither DTB is an M1 Pro `t6000/j314` DTB.
- A compatible public Touch ID implementation has not been obtained/verified
  by this project. The announcement warrants continued source tracking.
- The [MLX hardware table](https://github.com/joshuaswarren/omarchy-mlx#supported-hardware)
  marks M1 Pro GPU/ANE untested. Qualification is still required.

## 3. Establish the integrated baseline

Before the broad rewrite, qualify the integrated M1/M2 behavior and preserve
reproducible builds, configurations, reference outputs and recovery procedures.
Record startup/interaction latency, CPU time, idle/busy memory, battery/power,
throughput and package/install timing where relevant. Define an agreed workload
and failure scenarios for each component. Keep unresolved hardware support
visible rather than treating a rewrite as a substitute for missing drivers.

## 4. Convert to Rust, then verify the gains

The requested direction is a full Rust migration of the implementation we
maintain. Inventory every code component and its external dependencies first,
including daemons, telemetry, app deployment, installers, helpers and desktop
components. Evaluate upstream kernel/firmware/Pantheon boundaries explicitly;
record feasibility and any required upstream coordination instead of silently
claiming those dependencies were rewritten.

Migrate one component at a time after its integration contract is established.
Candidate early components are persistent telemetry/network logging, power and
brightness helpers, app deployment and GTK controller logic. Prioritize measured
cost and maintenance risk; preserve D-Bus, service, CLI, storage and UI behavior.
Retain the prior implementation until parity, failure recovery, ARM64 packaging
and hardware checks pass. Do not begin a wholesale rewrite before the upstream
integration baseline is ready.

For each conversion, publish before/after results using the same workload and
hardware, and account for compile/deployment size and dependency costs. Rust is
the implementation direction; lower latency, memory or power consumption must
be demonstrated. Track regressions and unresolved scope until the roadmap's
full behavior and performance gates are satisfied.
