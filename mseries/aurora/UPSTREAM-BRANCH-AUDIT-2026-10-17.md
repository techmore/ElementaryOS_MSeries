# Aurora upstream branch audit — October 17, 2026

Audited all **51 branches** in `omacom/linux-aurora` and the heads of **11 open
PRs**, including PRs from forks. Baseline: our published `.20` kernel source
`c46d7dcdb8712ea9aeb0ce47b439ffae76371e55`. The upstream default branch is
`integration/aurora` at `5d570a78a4ab29ac383ec8988be2356dfc6c8a75`.
Refs are a dated snapshot; full hashes and graph results are in
[the machine-readable receipt](branch-audits/2026-10-17.json).

## Result and recommended order

**41 branch tips are already ancestors of `.20`; two more add release tooling
only.** Of the eight divergent branches, several duplicate or broaden features
already implemented in the current kernel. None is a demonstrated new fix for
our J314S + WD22TB4 HDMI path. Keep the released `.20` baseline intact for the
first target-machine qualification.

1. **Test what `.20` already supplies on J314S:** dock display, SEP/sensor,
   PMP/power behavior and the VRR interfaces. Driver presence is not a measured
   battery improvement or evidence that the compositor enables VRR.
2. **Prepare a separate local-AI kernel candidate from the first commit of
   [PR #67](https://github.com/omacom/linux-aurora/pull/67)** if GPU-visible host
   memory is needed. Keep its eGPU commit separate. This needs a real source
   build and M1 Pro memory/correctness qualification.
3. **For broader M3 Air coverage, evaluate [#135](https://github.com/omacom/linux-aurora/pull/135)
   and [#134](https://github.com/omacom/linux-aurora/pull/134), followed by
   [#119](https://github.com/omacom/linux-aurora/pull/119)** for the relevant OS
   firmware. They pass clean application checks on `.20`; #135 also passes
   the reproduced host suite. They are not M1 Pro enhancements.
4. **Rebase M3 display work before considering it:** #122 and #127 conflict
   with `.20`. Keep Neo telemetry and generic SMC optional-property hardening
   as separate research/porting candidates.

No kernel patches, release pins, live services, boot images or boot selection
were changed by this audit. Kernel branch merges would require a new source
build; our current OS-repository adapter repackages a fixed upstream binary.

## Important source findings

### ProMotion / VRR already exists in `.20`

The `vrr` branch has a distinct commit identity, but
[PR #3](https://github.com/omacom/linux-aurora/pull/3) was merged into the old
`tb` lineage. Source inspection confirms the current `.20` implementation:

- `drivers/gpu/drm/apple/apple_drv.c`: attaches the `vrr_capable` property.
- `iomfb.c`: reports capability and populates `display_info.monitor_range`.
- `parser.c`: gives the internal 120 Hz ProMotion mode a 24 Hz minimum.
- `iomfb_template.c`: uses `crtc_state->vrr_enabled`, programs adaptive sync,
  and supplies architectural-counter timestamps rather than constant 120s.

[Current template source](https://github.com/omacom/linux-aurora/blob/c46d7dcdb8712ea9aeb0ce47b439ffae76371e55/drivers/gpu/drm/apple/iomfb_template.c#L1338).
The historical `vrr` patch conflicts and should not be reapplied. The remaining
question is Gala/Mutter's use of the interface and actual panel behavior. PR #3
itself records an internal-panel range/uAPI limitation for Mutter; no automatic
desktop fix or measured power saving follows from the kernel code alone.

The existing local `power/DYNAMIC-REFRESH-AUDIT.md` describes the older running
Fairydust driver, not this new kernel. Its `force_vrr` patch is not the right
starting point for Aurora `.20`.

### Compute preemption has a narrower current implementation

`candidate/g14x-compute-preemption` auto-enables compute preemption for every
G14X GPU. `.20` already has `compute_preempt`, preserves the debug override,
and auto-enables only the tested M2 Max chip (`0x6021`).
[Current workqueue](https://github.com/omacom/linux-aurora/blob/c46d7dcdb8712ea9aeb0ce47b439ffae76371e55/drivers/gpu/drm/asahi/workqueue.rs#L685).
The candidate's added breadth is untested M2 Pro/Ultra behavior, not a missing
M1 Pro fix. Its patch conflicts; retain the release behavior.

### Neo input is substantially superseded; SMC hardening is only partial

`.20` already parses the J700 C1FE report with a 32-byte header, 30-byte contact
records and eight-byte trailer, validates lengths, and reports positions and
presence without inventing pressure. The old J700 MTP patch conflicts with this
newer implementation.

For battery fields, `.20` checks key existence for selected optional properties
such as BITV/B0RC/B0RI/B0RV. It does **not** have the divergent battery branch's
full metadata-size/readability/complete-read admission helper. That is a real
hardening idea, primarily backed by Neo telemetry evidence, but needs a rebase
and cross-model supply-uevent/charge-limit tests. It is not a proven M1 Pro
power-saving change.

`neo/j700-smc-telemetry` is 131 commits ahead of its old common ancestor and
3,420 behind `.20`. Its own qualification document says it was not rebased
onto aurora-wip. It carries diagnostic/telemetry DT variants, bounded reads,
write restrictions and suspend-safe polling from a September J700 experiment.
[Qualification notes](https://github.com/omacom/linux-aurora/blob/e63dc3d7a9de2e2c80b70c0c39811a9b2671b4e2/tools/testing/j700-smc/README.md).
Do not merge that historical bring-up branch wholesale into the shared driver
stack. Its API file comparison reached the 300-file cap; review here was of
the head, recent relevant history and qualification notes, not every one of
its 131 unique commits.

## Additional open PR candidates

| PR | Benefit and hardware | `.20` source check | Recommendation / remaining gate |
| --- | --- | --- | --- |
| [#67](https://github.com/omacom/linux-aurora/pull/67), draft | memfd-to-dma-buf imports for local GPU compute; separately AMD/Nouveau modules | Both commits apply | Split: consider only `6984b8c…` first. The `.20` full recipe config has UDMABUF/heaps and both discrete GPU drivers off. Modify the actual build config, not just `asahi.config`; rebuild image/modules together. Contributor evidence is M2 Max on an older release, up to 512 MiB, not this PR head or M1 Pro. No measured AI speed/power win. Keep the unbuilt/unbooted eGPU commit out of the first candidate. |
| [#135](https://github.com/omacom/linux-aurora/pull/135) | Preserve M3 Air/T8122 thermal fallback at state 2 when an experimental ceiling is raised | Applies; reproduced host suite: **54 base / 58 patched**, all pass | Strong scoped hardening candidate for T8122. Contributor combined-tree build/J613 tests exist; full `.20` integration build and long-duration qualification still required. No reason to raise clocks on J314S. |
| [#134](https://github.com/omacom/linux-aurora/pull/134) | J613 camera on OS firmware 14.7: PMU base typo and temporal-filter workaround | Applies | Contributor reports full combined-tree build and 30 fps streams on one J613. No M1 Pro camera benefit claimed. |
| [#119](https://github.com/omacom/linux-aurora/pull/119) | J613 camera on OS firmware 26.6.2 | Applies, including after #134 | Requires the matching m1n1 ISP heap and local firmware/setfile provisioning. Firmware recognition is shared code; test other ISP paths before broader enablement. No camera data was collected here. |
| [#122](https://github.com/omacom/linux-aurora/pull/122), draft | T6030/M3 Pro HDMI hold lifetime, identity and relink tests | Conflicts | Rebase shared display changes and rerun KUnit/full build. Author lists one existing test failure, one skip and hardware follow-ups. This is not the M1 Pro WD22TB4 HDMI path. |
| [#127](https://github.com/omacom/linux-aurora/pull/127) | J613 lid-closed dual external displays | Conflicts | Needs the #103 m1n1 readiness marker, matched DT and rebase across shared display code. Contributor hotplug/lid/suspend evidence is J613 + Hyprland. Confirm no M1/M2 regression and qualify Gala separately. |
| [#110](https://github.com/omacom/linux-aurora/pull/110) / [#86](https://github.com/omacom/linux-aurora/pull/86) | Omarchy ARM pacman package-pin handling | Both apply; #110 supersedes #86 | Exclude from elementary: we do not use this Arch/Omarchy installer. |
| [#9](https://github.com/omacom/linux-aurora/pull/9) | Historical J316C USB4 display implementation against `tb` | Conflicts | Modern release has its own broader tunnel/display stack. Do not replace it with this old opt-in design. |
| [#8](https://github.com/omacom/linux-aurora/pull/8), draft | Experimental J456 iMac amplifier bring-up | Conflicts | No J314S relevance; protection, routing, target build and packaging gates remain. Keep out of a general speaker release. |
| [#7](https://github.com/omacom/linux-aurora/pull/7) | Historical SEP implementation against `asahi` | Conflicts | Current release already contains later SEP/sensor work. Retain its newer state/provisioning safeguards; do not revive old reset/keybag instructions. |

For #67, the udmabuf path has 16 KiB size/offset alignment and a default 64 MiB
per-buffer limit; it takes appropriately sealed memfd pages and keeps them
resident. The system dma-heap path was not exercised by the contributor. Access
policy, memory pressure and multiple live buffers need explicit tests. Adding
the AMD/Nouveau modules is a separate, currently unqualified eGPU experiment.

## Reproduced checks and limitations

- Queried the complete branch list (51 entries, below the 100-entry page limit)
  and all open PRs (11). Compared each immutable head with the pinned source.
- Downloaded 16 public patch sets and checked both normal and reverse application
  without modifying the baseline source. Six pass forward checks: #67, #86,
  #110, #119, #134 and #135. None passes the complete reverse check. This is
  why source inspection was also used for superseded features.
- Applied #134 then #119 to an isolated copy of the `.20` ISP files; the series
  coexist cleanly. This is a source application check, not a camera build/test.
- Ran upstream `tools/asahi/m3-runtime-tests.rs` on the base and a separate
  #135 copy using macOS Homebrew Rust 1.98.1, edition 2021, `-D warnings`:
  **54/54** and **58/58** pass. This is not the release's Rust 1.93.1 toolchain
  or an ARM64 Linux kernel build.
- Checked the original release recipe config: UDMABUF/heaps/AMDGPU/Nouveau
  are off; HZ remains 1000 with NO_HZ_FULL. No validated tick-rate change was
  discovered as a separate candidate in the audited branch set.
- Contributor hardware/build results above are attributed to their PRs. No
  local M1 Pro, M3 Air, Neo, camera, amplifier or dock result was produced.

The graph comparison is complete for the named branch set. Source review is
targeted enhancement discovery and applicability assessment, not an exhaustive
security audit or approval to install every patch that applies.

## Complete branch inventory

Ahead/behind are commit counts against `c46d7dcd…`, not kernel version numbers.
An ancestor tip has no new commits to import; later history may have revised
or replaced its behavior. Distinct commit identities can also carry the same
feature, as the VRR source check demonstrates.

| Branch | Immutable tip | Ahead | Behind | Disposition |
| --- | --- | ---: | ---: | --- |
| `asahi` | [`77cb8f24c2`](https://github.com/omacom/linux-aurora/commit/77cb8f24c2381a8abb7272d7bbdec548d6426a8a) | 0 | 2648 | Ancestor; no new commits |
| `aurora-wip` | [`4ec597a742`](https://github.com/omacom/linux-aurora/commit/4ec597a7427da2cf03c899406b7997c875d4a9fb) | 0 | 2242 | Ancestor; no new commits |
| `candidate/g14x-compute-preemption` | [`ab21a1ab04`](https://github.com/omacom/linux-aurora/commit/ab21a1ab046f23bf726645f23bcbca367cad489b) | 1 | 783 | Current M2 Max variant retained; do not broaden by merging |
| `candidate/installer-download-resume` | [`05b0b44fd1`](https://github.com/omacom/linux-aurora/commit/05b0b44fd19e4a07a83d200f1f0dc7341fd1a90e) | 0 | 772 | Ancestor; no new commits |
| `carry/pr80-ane-nodes` | [`b5ece52ad9`](https://github.com/omacom/linux-aurora/commit/b5ece52ad96b765370057c5f538fbe0f7f21f002) | 0 | 687 | Ancestor; no new commits |
| `carry/pr86-omarchy-arm-pins` | [`bb547a4ef6`](https://github.com/omacom/linux-aurora/commit/bb547a4ef6fc2b75bee79c254114dee98cb3d2aa) | 2 | 688 | Omarchy installer only |
| `carry/pr91-pmgr-misc` | [`604a84d068`](https://github.com/omacom/linux-aurora/commit/604a84d0681206190f8d8edc74f86391c2c933fb) | 0 | 735 | Ancestor; no new commits |
| `carry/pr92-tb-s2idle` | [`ff507243bb`](https://github.com/omacom/linux-aurora/commit/ff507243bbacb14335f695cb9ddc8f76698f9d14) | 0 | 735 | Ancestor; no new commits |
| `carry/pr95-t8122-418c` | [`0d51a40369`](https://github.com/omacom/linux-aurora/commit/0d51a403693b9526bfc4268f22898faeb38a6704) | 0 | 687 | Ancestor; no new commits |
| `docs/aurora-roadmap` | [`64df7a4a28`](https://github.com/omacom/linux-aurora/commit/64df7a4a2809b236900c79b7e5fbcf2e5f7e5d0b) | 1 | 956 | Historical roadmap; reference only |
| `docs/m3pro-performance-profile-20261012` | [`42c56239e9`](https://github.com/omacom/linux-aurora/commit/42c56239e90004507abe332e72d7b94bae9f37e6) | 0 | 739 | Ancestor; no new commits |
| `docs/omacom-roadmap-current` | [`710b882e69`](https://github.com/omacom/linux-aurora/commit/710b882e6976b9bd64ff7a0f9ab0a606ee3f4943) | 0 | 780 | Ancestor; no new commits |
| `docs/unified-launch-roadmap` | [`56029d6352`](https://github.com/omacom/linux-aurora/commit/56029d635243516e0ae98a21086a7765eacaa6d4) | 0 | 753 | Ancestor; no new commits |
| `fix/bt4378-hardware-id-20261011` | [`bd58f8e0a4`](https://github.com/omacom/linux-aurora/commit/bd58f8e0a4b8daed724d167d2b164fff71818358) | 0 | 748 | Ancestor; no new commits |
| `fix/dma-heap-allocation-result` | [`9c2cc3b3bb`](https://github.com/omacom/linux-aurora/commit/9c2cc3b3bba220236390075c81af1d1af7c9ee3d) | 0 | 756 | Ancestor; no new commits |
| `fix/esp-history-metadata` | [`519cfffb15`](https://github.com/omacom/linux-aurora/commit/519cfffb15e2b4f303e5d82895533991143de06b) | 0 | 770 | Ancestor; no new commits |
| `fix/frozen-ignorepkg-deps-20261011` | [`43ae7c9e85`](https://github.com/omacom/linux-aurora/commit/43ae7c9e85fbb3ce371b06dd516eaa3b46804110) | 0 | 742 | Ancestor; no new commits |
| `fix/hdmi-hold-review-followups` | [`11150ed2b4`](https://github.com/omacom/linux-aurora/commit/11150ed2b47ac04d8b424a25ac52bfd63fe1a04f) | 4 | 671 | M3 Pro hold fixes; rebase required |
| `fix/j493-bluetooth-resume-recovery` | [`3a8fd50539`](https://github.com/omacom/linux-aurora/commit/3a8fd50539a50c72fd5f35078af909e5f759b815) | 0 | 767 | Ancestor; no new commits |
| `fix/j516s-hdmi-hold` | [`d4a128739e`](https://github.com/omacom/linux-aurora/commit/d4a128739e3d4ad0cc940010b1621c30d1517140) | 0 | 686 | Ancestor; no new commits |
| `fix/j700-mtp-contact-position` | [`ddb87a1708`](https://github.com/omacom/linux-aurora/commit/ddb87a170804f05ee56b15f314ef15cda3b2d812) | 1 | 2242 | Current Neo input supersedes this patch |
| `fix/kernel-only-package-contract-20261011` | [`7c2b4e8050`](https://github.com/omacom/linux-aurora/commit/7c2b4e8050cbf9da0504a0072189a2242e418801) | 0 | 744 | Ancestor; no new commits |
| `fix/m2max-compute-preemption` | [`3879421069`](https://github.com/omacom/linux-aurora/commit/3879421069964c46999312c5ffd50247ac4da17d) | 0 | 765 | Ancestor; no new commits |
| `fix/m3-failed-work-owner` | [`195a2bc8a0`](https://github.com/omacom/linux-aurora/commit/195a2bc8a080aa4d18d261852d4f557bc639dcb8) | 0 | 687 | Ancestor; no new commits |
| `fix/m3pro-display-submit-admission` | [`a85f8eee2f`](https://github.com/omacom/linux-aurora/commit/a85f8eee2fd54ed9e7237f25d1f085e9d7848111) | 0 | 790 | Ancestor; no new commits |
| `fix/m3pro-hdmi-thunderbolt` | [`13d2affbc4`](https://github.com/omacom/linux-aurora/commit/13d2affbc4d176b528d0c5ef5b17d639c6daab19) | 0 | 739 | Ancestor; no new commits |
| `fix/macsmc-optional-battery-properties` | [`4676c48ecf`](https://github.com/omacom/linux-aurora/commit/4676c48ecf1b1acaba7c442d33fe9aae0f037e77) | 1 | 2242 | Optional battery-property hardening; port required |
| `fix/migration-test-fixtures` | [`833de07062`](https://github.com/omacom/linux-aurora/commit/833de07062944ae15213677cbb6d23149835a5ec) | 0 | 767 | Ancestor; no new commits |
| `fix/native-gl-glyph-package-20261012` | [`1c8bd82347`](https://github.com/omacom/linux-aurora/commit/1c8bd8234712bddde3988b391717943813cb6e2f) | 0 | 717 | Ancestor; no new commits |
| `fix/native-msaa-package-20261013` | [`9593361be5`](https://github.com/omacom/linux-aurora/commit/9593361be554b708ef26a0d110a2fb012f0fc0b9) | 0 | 714 | Ancestor; no new commits |
| `fix/typec-routes-under-off-dcp` | [`5ca53abe30`](https://github.com/omacom/linux-aurora/commit/5ca53abe30ab0e6b0a57c06e2d6c3813c40d3bcf) | 0 | 636 | Ancestor; no new commits |
| `integration/aurora` | [`5d570a78a4`](https://github.com/omacom/linux-aurora/commit/5d570a78a4ab29ac383ec8988be2356dfc6c8a75) | 2 | 0 | Release metadata/tooling only |
| `max/t6031-display-20261011` | [`9f7ff5e87f`](https://github.com/omacom/linux-aurora/commit/9f7ff5e87f954a012dda4063b6cd57c7e93c02c2) | 0 | 738 | Ancestor; no new commits |
| `max/t6031-gpu-20261011` | [`39562a87b0`](https://github.com/omacom/linux-aurora/commit/39562a87b0fe78565240dba98ee2f0b8c402a8fc) | 0 | 739 | Ancestor; no new commits |
| `max/t6031-gpu-groundwork-20261011` | [`40b438de00`](https://github.com/omacom/linux-aurora/commit/40b438de003ce00c6157d521d3249c7a20d222e1) | 0 | 740 | Ancestor; no new commits |
| `max/t6031-kit-20261011` | [`af43b84b90`](https://github.com/omacom/linux-aurora/commit/af43b84b902aab0166849adffdf19542af05f18e) | 0 | 740 | Ancestor; no new commits |
| `max/t6031-kit-integration-20261011` | [`93af871ea4`](https://github.com/omacom/linux-aurora/commit/93af871ea4150ac80b32fa1eb75cb1fecc42a425) | 0 | 726 | Ancestor; no new commits |
| `merge/aurora-wip-pr131` | [`7638540a67`](https://github.com/omacom/linux-aurora/commit/7638540a67d8a8fd1a0f228ba119e14193702f9e) | 0 | 1 | Ancestor; no new commits |
| `migrate/aurora` | [`e2f68afa23`](https://github.com/omacom/linux-aurora/commit/e2f68afa23816d1dde226c432ce1d62f6dee4da6) | 0 | 788 | Ancestor; no new commits |
| `neo/j700-smc-telemetry` | [`e63dc3d7a9`](https://github.com/omacom/linux-aurora/commit/e63dc3d7a9de2e2c80b70c0c39811a9b2671b4e2) | 131 | 3420 | Old Neo qualification tree; research only |
| `pr/m3pro-performance-kernel-20261012` | [`ac34611f8d`](https://github.com/omacom/linux-aurora/commit/ac34611f8de50386b6c08872c07f857fdbc24cf2) | 0 | 730 | Ancestor; no new commits |
| `release/aurora-20261012-16` | [`61e46776a5`](https://github.com/omacom/linux-aurora/commit/61e46776a56ef966dd35a32e6938f2ecb9f3094a) | 0 | 720 | Ancestor; no new commits |
| `release/aurora-20261015-19` | [`0a8bd8bb4d`](https://github.com/omacom/linux-aurora/commit/0a8bd8bb4d5f96bd11bdfdc858b3b25ab5c52018) | 0 | 634 | Ancestor; no new commits |
| `release/aurora-20261017-20` | [`c8aad9a06b`](https://github.com/omacom/linux-aurora/commit/c8aad9a06bb5c25f1442ee4e78ab8f9c0ec8c55f) | 1 | 0 | Release metadata/tooling only |
| `release/omacom-20261011-r14-tools` | [`feb42416b4`](https://github.com/omacom/linux-aurora/commit/feb42416b414462cb9ff1f7b28819c99b2d1743c) | 0 | 751 | Ancestor; no new commits |
| `release/omacom-20261011` | [`e70a953c9a`](https://github.com/omacom/linux-aurora/commit/e70a953c9afc4db4d13cb9ff5b9053ecfaa0e253) | 0 | 784 | Ancestor; no new commits |
| `review/j613-external-dp` | [`d5224e9f10`](https://github.com/omacom/linux-aurora/commit/d5224e9f10ba11d6b0cb99e7c9d9cea486849510) | 0 | 662 | Ancestor; no new commits |
| `tb` | [`38c14f6107`](https://github.com/omacom/linux-aurora/commit/38c14f6107dfdb3366dee3cdfc3226cf4cda9ca2) | 0 | 2158 | Ancestor; no new commits |
| `test/neo-association-event-ownership` | [`f7d9c785ae`](https://github.com/omacom/linux-aurora/commit/f7d9c785aeabd214939908d588018469975a1fa4) | 0 | 767 | Ancestor; no new commits |
| `usb4-base` | [`2daeae4fb0`](https://github.com/omacom/linux-aurora/commit/2daeae4fb0a91701c30cff53e23d42e23a9ae3ec) | 0 | 2209 | Ancestor; no new commits |
| `vrr` | [`e853c9eef4`](https://github.com/omacom/linux-aurora/commit/e853c9eef448eed71b18f27df689ee0acae6c5f0) | 1 | 2161 | VRR already implemented; do not reapply |
