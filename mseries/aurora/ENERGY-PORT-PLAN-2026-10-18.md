# Aurora energy ports and frozen feature releases — 2026-10-18

Target: the owner's **J314S, T6000, 14-inch M1 Pro (2021)**, followed by other
M-series boards with separate qualification. This plan supersedes the older
"kernel is DeepSeek's; contribute data only" planning restriction for this
owner-requested source/release work. Live boot selection, display preferences,
audio policy and experimental sleep parameters were not changed.

## Fresh upstream inventory

[The receipt](branch-audits/2026-10-18-energy.json) records **52 branches and
12 open PR heads**, including fork heads. The 51 previous branch identities
are unchanged against the fixed `.20` base. Their immutable graph comparisons
remain valid; the new J700/T8140 display-DART branch was compared separately.
The integration branch remains `5d570a78…`; the published kernel stays `.20`,
source `c46d7dcd…`. No new released M1 Pro energy delta was found.

New [draft PR #139](https://github.com/omacom/linux-aurora/pull/139) combines
integration and WIP on **Asahi 7.2.10**. Pin:
`aurora-silicon/linux@582e9ef3d44c93082e8abc740ad3e0a8dde29752`.
It supersedes the stale `aurora-wip` branch as the current integration proposal;
the branch name alone would miss this work. Its author reports J316S/M1 Pro,
J413/M2 and J700/Neo results, with different configurations and boot payloads.
Those are contributor results. They do not qualify this J314S or our new config.
The PR remains draft and cannot cleanly merge into its current base.

Coverage: complete ref/PR discovery and disposition, followed by targeted energy
code inspection. GitHub capped the PR commit endpoint at 250 entries and the
compare file list at 300; neither is called a full review of the 26,581 commits
reported ahead of `.20`. Ten relevant files were read at immutable source SHAs.
PMGR, CPU idle, J314S DTS, PMP argument/correlation helpers and their host tests
are **byte-identical** between `.20` and this 7.2 snapshot. PMP Rust changes are
primarily the 7.2 platform/MMIO adaptation and SoC matching; cpufreq/NVMe also
have API, diagnostic and non-M1 thermal-policy changes. No new measured J314S
idle-watt fix was established by those differences.

## Energy and hardware disposition

| Area / source | M1 Pro applicability | Implementation / next gate |
| --- | --- | --- |
| [PMP + J314S DT + DCS-safe suspend, #91/#123](https://github.com/omacom/linux-aurora/pull/123) | Direct J314S fix | Already in `.20`, its source-built successor and the pinned 7.2 snapshot. Current hardware log confirms PMP ready, started, and owning fabric/DCS. Do not apply a duplicate patch. Suspend/resume still needs local cycles. |
| Idle fabric governor and external-CRTC holds, same series | Other M1/M2 Pro/Max without PMP; J314S falls back only without PMP | Already carried. `idle_fabric_pstate=0` retained. The governor refuses to compete with PMP. The external scanout hold prevents reducing display bandwidth. No reason to turn it on over the running PMP. |
| [Thunderbolt sleep controls + review fixes, #92/#124](https://github.com/omacom/linux-aurora/pull/124) | M1 Pro; dock topology matters | Already carried. `s2idle_teardown`, `resume_recovery`, `router_sleep` remain N. Router sleep lost links in contributor tests. Teardown drops USB/network/display tunnels and skips PCIe tunnels; qualify exact WD22TB4 topology before opt-in. |
| [ProMotion VRR, #3](https://github.com/omacom/linux-aurora/pull/3) | Internal M1 Pro display | Already in `.20`; old divergent VRR patch conflicts. Remaining work is compositor/panel acceptance. Do not change refresh rate or claim power savings from property presence. |
| CPU PD / cpuidle / cpufreq | T6000 | Existing menu governor and CPU PD accounting retained. Captured per-CPU counter deltas. No HZ=250 change or governor switch is justified by the audited evidence. T8140 fast-die limits are not a new M1 Pro optimization. |
| PMP boot-argument bounds and reply correlation | Shared firmware-control correctness | Present in both pinned trees. Executed production 9 argument-parser + 3 reply-correlation host tests on the 7.2 snapshot. Firmware-ready logs are a scoped local test, not a sleep/power result. |
| NVMe / PCIe sleep ordering | Shared resume and storage integrity | `.20` already contains the carried ownership/quiesce work. The inspected 7.2 NVMe diff is API/comment adaptation, not a proved energy gain. Storage checks and recovery boot are mandatory before stable promotion. |
| [udmabuf/system heap, #67](https://github.com/omacom/linux-aurora/pull/67) | M1 Pro GPU compute, application-dependent | Integrated existing source-build candidate. Full config enables the memory interfaces. No AI energy/speed claim. eGPU modules stay in their separate profile. |
| Optional SMC battery-property validation | Shared reporting reliability | Rebased production helper in source candidate. All-readable plus 65 per-key failure cases pass ASan/UBSan. Telemetry hardening does not reduce watts by itself. |
| [T8122 thermal fallback, #135](https://github.com/omacom/linux-aurora/pull/135) | M3 Air, no M1 Pro clock increase | Integrated original patch into the `.20` enhancement candidate; 58 production Rust tests pass. Remains board-specific. |
| [J613 camera #134/#119](https://github.com/omacom/linux-aurora/pull/134) | M3 firmware combinations | Integrated in the `.20` source candidate with firmware prerequisites documented. No M1 energy claim. |
| M3 display/clamshell #122/#127 | Other boards; shared display changes can regress M1 | Conflicting 7.1 patches remain separate. The pinned 7.2 unified lane is the integration vehicle to evaluate their dependency stack; do not independently apply historical display patches over it. |
| G14X compute preemption / ANE short polling | Mainly M2 Max / workload-specific | Preserve current qualified scope. Do not broaden to M1 or equate faster polling with lower energy. |
| Neo telemetry, new J700 DART fix, M3 GPU redesign | Other SoCs | Tracked as separate board work. Never import the old 131-commit telemetry branch wholesale or enable a compile-only M3 backend on T6000. |
| AVD hardware decode, Wi-Fi/BT recovery, display/audio | Potential workload power and wake effects | Existing driver paths retained. Paired workload measurements are required. HDMI audio remains off; no speaker-protection or live audio changes. |

Contributor energy numbers are useful hypotheses: [#91](https://github.com/omacom/linux-aurora/pull/91)
reports 4.98→3.96 W with the display off and 5.96→5.18 W at backlight zero on
one J314S with PMP. [#92](https://github.com/omacom/linux-aurora/pull/92) reports
4.03→2.71 W during s2idle with a Mac peer and teardown enabled. Their release,
power source, topology and workload differ from ours. These are **not local gains**.

## Implemented order and release gates

1. **Now: retain and freeze the observed baseline.**
   `mseries-aurora20-j314s-2026.10.18-exp1` pins kernel/source/recipe hashes,
   the actual kernel image, matched boot payload and selected installed driver/
   J314S DTB hashes. [Receipt](hardware-tests/2026-10-18-j314s-aurora20.json):
   boot observation, PMP readiness, idle accounting and selected severe-log
   screening pass. Full graphics/GPU/storage/network/input/thermal/suspend/
   recovery/energy acceptance is explicitly not run. Freeze channel is
   **experimental**, never stable.
2. **Now: integrate the previously CI-built source ports.**
   PR #79's six-patch source lane is integrated, with authors/hashes retained.
   Its unchanged source series previously built both native ARM64 profiles in
   [run 39085271170](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39085271170).
   Retested local adapters and production logic. New repository CI rebuilds
   the combined integration. No existing `.20` files/defaults are replaced.
3. **Now: pin and build WIP independently.**
   `candidate.py prepare --profile unified72` consumes a checksum-pinned PR #139
   archive, resolves the fixed `.20` config against 7.2.10 and uses separate
   identity `7.2.10-elementary-aurora72-wip1`. Source prepared and PMP tests
   passed locally. Native ARM64 Image/modules/DTB/package inspection is a CI
   gate. This lane deliberately does not claim upstream's Fedora-config tests,
   complete M3 feature parity, local boot success or a measured power win.
4. **Next hardware batch: exact boot-chain acceptance.**
   After build success, review candidate DT/m1n1/initramfs and recovery together.
   Use a separate versioned non-default entry; retain byte-exact rollback and
   root-unlock support. Run internal display + GPU readback, NVMe I/O integrity,
   Wi-Fi/BT/input, all ports/orientations, and WD22TB4 modes/replug/DPMS. Record
   boot ID and all artifact hashes for every result. Observe known SEP-probe
   failures without automatically opening the sensor.
5. **Then sleep and energy.**
   At least three successful suspend/resume cycles, with dock connected and
   disconnected, and a recovery boot. Measure steady idle, normal work and
   video with fixed brightness/refresh/topology/app mix. Alternate baseline/
   candidate AB/BA for at least three matched pairs; report median and p10/p90.
   Start with all new Thunderbolt controls off. Test each optional control as
   a distinct configuration/freeze identity after default-path acceptance.
6. **Promote a feature-frozen release only on evidence.**
   `qualification.py freeze --channel stable` refuses mixed kernel/boot/module
   identities, failed/missing required cases, fewer than three boot IDs, fewer
   than three sleep cycles, unmatched/nonalternating energy pairs or a >10%
   paired power regression. That threshold is an acceptance budget, not a
   claimed energy improvement. A frozen ID is never overwritten; new source,
   config, modules or boot payload require a new ID and new tests. Publish
   source/config/checksums beside binary payloads and use prerelease labels
   until the complete policy passes.

The current 30-second SMC window ran during active source/agent work. Its
25.16 W median (p10 22.51, p90 28.06; n=31) is an uncontrolled observation,
not an idle baseline or regression verdict. Controls were unchanged; workload
was not controlled. No battery-life improvement is claimed.
