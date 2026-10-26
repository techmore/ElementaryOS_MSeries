# Aurora20 → wip4 port audit for the owner’s machine — 2026-10-22

## Owner target and result

This audit is relative to the owner’s 14-inch M1 Pro MacBook (`J314S`) running elementary OS on Asahi, with a Dell WD22TB4 and HDMI display. The current trial is wip3; Aurora `.20` remains the persistent default. This change prepares a separate wip4 series and does not install, stage, arm or boot it.

The owner-facing kernel work is the 7.2.11 DCP/display series: upstream #157 adds external-display sRGB handling, and the local wip4 patch addresses the observed `dcpext1` DPTX timeout and pinned tunnel route. The six Aurora20 ports are included because the owner requested them, but most target other hardware or optional setups. They do not make the J314S camera, M3 thermal behavior or eGPU support qualified.

## Six requested ports

All six patches were applied in manifest order to a clean extraction of the exact wip4 source commit (`bd526b3c11ccf8e91d6240261beb3219d8f17f03`, tree `a305f231d9137847c7f0ececca98e214cc30e792`). Every `git apply --check` passed, including the eGPU patch after the udmabuf config patch.

| wip4 patch | Upstream source and status checked 2026-10-22 | Port and owner relevance |
|---|---|---|
| `0003-udmabuf.patch` | [#67 first commit](https://github.com/omacom/linux-aurora/commit/6984b8c07e84b0cf528243db1838dade971ff513); #67 remains an open draft PR | Config fragment plus checked full build config. Generic facility; usefulness depends on applications and suitable permissions/alignment. No local-AI performance claim. |
| `0004-m3-thermal-fallback.patch` | [#135](https://github.com/omacom/linux-aurora/pull/135), open | Adapted into the 7.2.11 `m3_thermal_policy.rs` helper and its host controls. **Dormant:** #158 has a compile-only M3 backend that refuses runtime startup, so no thermal control is activated. M3/T8122-only and not relevant to J314S. |
| `0005-j613-camera-147.patch` | [#134](https://github.com/omacom/linux-aurora/pull/134), open | Unmodified patch; scoped to J613/T8122 camera firmware compatibility. It does not target J314S. |
| `0006-t8122-camera-2662.patch` | [#119](https://github.com/omacom/linux-aurora/pull/119), open | Unmodified patch; requires the matching m1n1 ISP-heap support and device firmware. Not qualified on J314S. |
| `0007-macsmc-optional-properties.patch` | [upstream commit](https://github.com/omacom/linux-aurora/commit/4676c48ecf1b1acaba7c442d33fe9aae0f037e77) | Optional SMC gauge discovery. It should only change reporting when a property is missing or unreadable; prior hardware evidence is J700, and J314S telemetry remains unqualified. |
| `0008-egpu-config.patch` | [#67 second commit](https://github.com/omacom/linux-aurora/commit/d10d360a96f406f3b953eceb6e44e7be3f4c7c24); #67 remains an open draft PR | Only `--profile unified72-egpu` enables AMDGPU/Nouveau modules. The normal wip4 build keeps both off. No card, display output, BAR or compute qualification. |

GitHub state was read directly on 2026-10-22: #158 is still open at the pinned source head, #157 is still open at `9d3aeb24cb864d5f99a7172e9004884bf3c1a9a0`, and #135, #134, #119 and draft #67 are still open. The local pins are deliberate snapshots; a later upstream merge or head change does not update wip4 automatically.

## Local hardware fit and gates

- **Directly relevant:** wip4’s DCP routing patch targets the reported WD22TB4 HDMI failure. It avoids a silent DCP for 300 seconds after timeout and treats timed-out release as complete. That latter assumption is the main code risk; the observed device timed out repeatedly, but a slow response is not ruled out. A tunnel already assigned during the first plug is not moved by this patch in that same plug.
- **Potentially generic:** udmabuf/system heap support and optional SMC gauge discovery. These add no claimed performance or battery-life improvement.
- **Other hardware:** M3 Air thermal and J613/T8122 camera support are not J314S features. The thermal policy is present but inactive while M3 startup is refused; the camera patches remain firmware-scoped and require their stated companion support.
- **Optional experiment:** eGPU modules are isolated to a separately named profile/package. It is not enabled in the owner’s normal wip4 profile.
- **Passed in CI:** ARM64 candidate, normal wip4 and opt-in eGPU Image/modules/DTB builds and package inspection ([run 39854228647](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39854228647)). **Still open:** DCP KUnit, an attended wip4 boot, WD22TB4 HDMI retry/recovery, camera/SMC hardware checks on matching devices, eGPU hardware checks, suspend/recovery and 64-fix semantic parity.

The matching DT/m1n1, initramfs, boot entry and rollback have not been reviewed or staged for this revision. The existing wip3 trial and `.20` default are untouched.

## Upstream display/Type-C scan before J314S testing — 2026-10-26

The upstream `integration/aurora` head is 163 commits ahead of pinned #158, so wip4 stays on its immutable
7.2.11 base rather than moving wholesale to a changing branch. #158 has since merged at the same pinned commit;
#157 (the external-display color patch already carried as `0001`) remains open.

Reviewed [#186](https://github.com/omacom/linux-aurora/pull/186) and [#163](https://github.com/omacom/linux-aurora/pull/163).
Both remain open and `BLOCKED` as of this scan. #186 is a three-file DCP-fabric/TIPD change for direct DP-alt ports
that reserve display pipelines without HPD, including takeover when another direct port asserts HPD. Its author reports
a 7.2.10 J314S multi-display setup, and reports that a handover can leave DPTX timing out until reboot. #163 adjusts
TIPD's `-ENOSPC` handling so docks keep their USB path when a display pipeline is occupied; its hardware result is on
an M2 Air/T8112. Neither change directly addresses this J314S WD22TB4 tunneled-display timeout. #186's DCP changes
and wip4's local timeout/route-release patch touch the same subsystem, so combining them before a focused rebase and
interaction review would be unsafe. #163 is coupled to #186's standardized `-ENOSPC` semantics and lacks matching
J314S coverage. **Decision: do not add either open PR to this deploy candidate yet.** Revisit if they merge, if the
WD22TB4 failure evidence shows idle direct-port pipeline reservation is causal, or if an isolated source/KUnit review
shows a minimal safe subset. The local wip4 DCP patch remains required for the observed `-ETIMEDOUT` route wedge.

Other scanned display work: [#154](https://github.com/omacom/linux-aurora/pull/154) targets simultaneous DP tunnels
for a tiled 5K Studio Display and is outside this single 1080p HDMI target. No additional merged Aurora release
supersedes the pinned 7.2.11 base as of this scan.

## Deployment readiness

Wip4's CI package is now downloaded and audited from run 39944207967: GitHub's artifact digest and all four
`SHA256SUMS` entries match; 17 provenance-recorded modified source files match; package identity is
`linux-image-elementary-aurora72-wip4_7.2.11+elementary.aurora72.wip4-1_arm64.deb`, with 1,876 modules, 115 Apple DTBs
and the J314S DTB present. The package has no boot hooks. An offline J314S trial bundle is staged privately at
`/home/sdolbec/aurora-wip4-trial-20261026-v2/`: candidate vmlinuz/initrd, proposed GRUB config, byte-exact
`boot.bin.rollback`, package, matching source archive and provenance. Candidate initrd SHA-256 is
`07daaa0ef934b4a9e7a905e9d7d6f9bffe2a23ea59316a6f7d22602defe6349a`; rollback SHA-256 matches current shared
`boot.bin` (`9c9c2d01c3bdb2784daf99cecd6f0e2327eb8f148ea43c8e522e5bae09a14d5f`). GRUB syntax and the original-unlock/
module-package audit passed; the proposal retains `.20` as persistent default. Nothing was installed, copied into `/boot`,
added to the live GRUB config, armed or booted. This keeps the existing shared DTB/m1n1 payload, which is already the
current chain, rather than swapping it for a new payload.

Deployment is **staged but not yet approved/qualified**: review the private bundle and rollback accessibility, then
perform an attended owner-approved trial. The source archive's base tree was not independently reconstructed from the
pinned codeload archive, and fallback boot after a wip4 trial is unqualified. After boot, qualify one-shot dock recovery
and repeated plug/unplug using the monitor-restore watcher fix; do not infer permanent recovery from the current
front-left picture.
