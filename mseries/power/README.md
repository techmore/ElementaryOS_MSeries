# Power, battery and related display work

Documentation map reviewed 2026-10-17 on `power-usage` at `d581ac4`.
Start here; retain dated audits as evidence rather than treating them as current instructions.

## Where each kind of information belongs

| Need | Source of truth | Scope |
| --- | --- | --- |
| Priorities, targets and experiment gates | [Power roadmap](../POWER-ROADMAP.md) | Single plan; targets are not achieved results |
| Measured macOS/Linux comparison | [Baseline workflow](macos-baseline/README.md) and [parity checklist](macos-baseline/PARITY.md) | 11 categories, 52 items; JSON is the editable source, Markdown is generated |
| Earlier Linux measurements | [October 16 opportunities](../POWER-OPPORTUNITIES-2026-10-16.md) | Dated observations and estimates, not matched baseline trials |
| Original efficiency goals | [Efficiency goals](../EFFICIENCY-GOALS.md) | Historical target rationale; use this machine's measurements for qualification |
| Dynamic refresh / ProMotion | [Dynamic refresh audit](DYNAMIC-REFRESH-AUDIT.md) | Investigation and experimental patch; hardware behavior remains unqualified |
| Charge limit and CPU policy | [Installer](../install-power.sh), [CLI](mseries-power), [policy](org.techmore.mseries.power.policy) | Implementation; see roadmap for outstanding physical checks |
| Dock HDMI | [Dock investigation pointers](#dock-hdmi-and-suspend) | Separate kernel/display workstream, with power and suspend implications |
| Project-wide status | [Handoff](../OS9-HANDOFF.md), [roadmap](../ROADMAP.md), [documentation index](../DOCS.md) | Record what changed and the next evidence needed |

## Evidence and open work

The retained [macOS run index](macos-baseline/results/README.md) describes what was actually collected.
The committed `macos-2026-10-17-1220` capture has inventory and two historical battery sleep periods,
but **no active scenarios**. The recorded median sleep loss is 0.391%/h across those two periods;
it is historical macOS evidence, not a Linux sleep result or a controlled overnight comparison.
No whole-machine active-use macOS/Linux parity is established by that capture.

Next steps, in order:

1. Collect active macOS scenarios on battery, recording brightness, refresh, attached dock and app state.
2. Collect matching Linux scenarios with the same clips and comparable settings. Brightness percentages
   differ between OSes; match measured luminance where available and document any mismatch.
3. Import summaries into `parity.py`, retain source paths and inspect generated `PARITY.md`.
   A numeric score alone does not establish comparable conditions or repeatability.
4. Run alternating A/B trials at least three times before claiming an optimization; retain medians and p10/p90.
5. Qualify unresolved Linux sleep, real battery-unplug policy, lid-close and display hotplug paths separately.

Keep raw logs local as configured by `macos-baseline/.gitignore`; review summaries before committing.
Do not add another worktree's untracked run to a report without reviewing its contents and conditions.

## Dock HDMI and suspend

The dock investigation now has a local [frontier ledger](../fairydust/usb4/STATE-OF-PLAY.md),
[goal and gates](../fairydust/usb4/PRIMARY-GOAL.md), and [code review](../fairydust/usb4/DOCK-CODE-REVIEW.md).
The following links retain the earlier `189cbda` snapshot for historical provenance:

- [Primary goal and G0–G5 evidence gates](https://github.com/techmore/ElementaryOS_MSeries/blob/189cbda/mseries/fairydust/usb4/PRIMARY-GOAL.md)
- [Cumulative state and next experiment](https://github.com/techmore/ElementaryOS_MSeries/blob/189cbda/mseries/fairydust/usb4/STATE-OF-PLAY.md)

That branch records USB4 data and tunnel allocation, but no qualified elementary desktop picture through
WD22TB4 HDMI. G3 link training is its stated blocker; G2 acceptance is unresolved for the alternate DCP route.
Its Aurora prior-art notes are research leads, not a successful boot or dock qualification on this installation.

The local [DP-IN diagnosis](DPIN-DOCK-HDMI-DIAGNOSIS.md),
[USB4 ledger](../fairydust/usb4/STATE-OF-PLAY.md) and
[older Alt Mode report](../USB-C-DOCK-DP-ALT-MODE.md) retain earlier observations.
Read the pinned branch frontier before scheduling another kernel experiment. USB/Ethernet functionality,
tunnel allocation, accepted modes and a visible picture are separate checks.
Docked lid locking is also separate from suspend: the recorded USB4 suspend veto means a dark display
can leave the machine awake. Measure docked and undocked sleep independently.

No kernel, bootloader, display settings or running audio changes are part of this documentation organization.

## Suspend energy and one-shot power report

The [Omacom port](../OMACOM-IMPROVEMENTS.md) adds `mseries-power-report --sample 10`
and a bounded sleep hook through `install-hardware-support.sh` / the diagnostics
enhancement module. It records energy deltas across real suspended-clock
intervals and notifies after a known unlock. Logs do not prove low-power
residency; transition overhead is included, charging/invalid intervals are
excluded, and the Linux hardware comparison still needs an actual run. Do not
update the parity checklist from synthetic fixture results.
