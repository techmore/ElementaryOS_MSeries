# Aurora display and USB-C upstream scan — 2026-10-26

## Scope

Read the current `omacom/linux-aurora` open pull request index and the primary diffs/status for the display, Type-C, USB4, and J314S-relevant candidates. The candidate source is the exact WIP4 source archive pinned at `bd526b3c11ccf8e91d6240261beb3219d8f17f03`, plus the local DCP timeout recovery patch `0002-drm-apple-free-dp-tunnel-route-from-silent-dcpext.patch`. This was a source review; no upstream code was imported, no build or hardware test was run, and no upstream message was sent.

## Findings

- **[#186](https://github.com/omacom/linux-aurora/pull/186), head `2a37f6f206456462970b3bbb3bf9bf8bd8944acd`, open:** reserves Type-C display pipelines until HPD and permits takeover of a pipeline held by a direct DP-Alt port without HPD. It edits `drivers/gpu/drm/apple/dcp-fabric.c`, the same routing function area changed by WIP4 patch 0002. Its purpose is plausible for port allocation, but it does not handle the observed DPTX `RemotePort` training timeout. Keep excluded until a source-level interaction review/rebase or upstream merge.
- **[#163](https://github.com/omacom/linux-aurora/pull/163), head `b8930ad8c5d319d74f9c284c764b7df29d879881`, open:** treats `-ENOSPC` as an occupied display pipeline so TIPD can preserve dock USB. This is not DPTX training recovery. Its `cd321x_display_taken()` and KUnit changes conflict semantically and textually with #186; upstream discussion says it needs a rebase with #186. Exclude from this WIP4 dock trial.
- **[#9](https://github.com/omacom/linux-aurora/pull/9), head `e707d60d5fdca4e0400a79795af5d26e1f5e2368`, open:** an older, broad USB4 DisplayPort tunneling implementation (+3225/-163 across DRM, Thunderbolt, ATC, Type-C, DTS and host fixtures). The WIP4 source already contains the tunnel/DPTX implementation and J314S route descriptions; #9 is not a small additive recovery fix. Its displayed DTS change is for J316C. Do not import it into the WIP4 pin.
- **[#154](https://github.com/omacom/linux-aurora/pull/154), head `54a14dabb01600453995e0877bb630fa622ede4c`, open:** shares an Apple host link between simultaneous DP tunnels. The current incident is one 1080p display; this does not explain its timeout.
- **[#157](https://github.com/omacom/linux-aurora/pull/157), head `9d3aeb24cb864d5f99a7172e9004884bf3c1a9a0`, open:** sRGB surface/link colorimetry, already included as WIP4 patch 0001. It changes color handling, not hotplug recovery.
- **[#170](https://github.com/omacom/linux-aurora/pull/170), head `4a220a8b8cf1ebf2a3b17da0a90908c03b38617b`, open:** gated J314S CPU context-loss diagnostic. It is unrelated to display routing and is deliberately excluded.
- **[Issue #130](https://github.com/omacom/linux-aurora/issues/130), open:** reports DCP crash/no recovery for direct DP-Alt after display power-on or s2idle on J316S. The SoC family is relevant, but the path and trigger differ from this J314S WD22TB4 USB4 tunnel incident; it reinforces that suspend/wake recovery is not qualified and provides no ready patch to cherry-pick.

The open index has newer work for M3/M6, J700, audio, and other devices, but no additional J314S tunneled-DPTX timeout fix was identified in this scoped scan. The WIP4 pin remains unchanged. Re-scan before the trial if the upstream candidate heads or integration base move.

## Decision before testing

No newly found upstream change is safe to add to this WIP4 candidate without introducing a broader or overlapping subsystem change. Keep the exact staged package and continue with the prepared attended trial only after owner approval. The kernel trial and display-profile watcher are separate: the watcher’s repaired D-Bus `ApplyMonitorsConfig` request has succeeded manually, while automatic unplug/replug/restore behavior has not yet passed a physical cycle.
