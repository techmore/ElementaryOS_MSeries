# WD22TB4 per-port pilot timings — October 21, 2026

All three ports now have an owner-confirmed dock picture. Front-left and right
also have explicit input confirmation. Rear-left's later picture supersedes its
initial blank-screen observation. No driver/service/runtime parameter change
was applied by this agent between those observations.

| Physical USB-C port | Partner to dock | Dock to monitor | Monitor to active desktop | Partner to active desktop |
| --- | --- | --- | --- | --- |
| Rear-left, nearest hinge | ~3.0 s | ~1.0 s | ~0.5 s | ~4.5 s |
| Front-left, closest to owner | ~3.0 s* | ~1.0 s | ~0.5 s | ~4.5 s* |
| Right | ~3.0 s | ~1.0 s | ~0.5 s | ~4.5 s |

One plug cycle each; requested 0.5 s polling. These are detection-to-observed-state
times, not physical cable insertion-to-visible-pixel measurements. This sample
cannot rank ports statistically. The compositor may mark a mode active before
pixels are visible; owner confirmation remains separate. All observed external
modes are 1920x1080/60.

* The front-left run's partner appeared in the sample completing the detach
window. The original tracker swallowed that boundary, so its summary started at
dock enumeration. The retained event log contains the partner edge; derived
values in [all-ports-followup.json](all-ports-followup.json) use that actual event.
The tracker has a targeted regression fix and test for future runs. Original
runner/results/events are retained, without rewriting old evidence.

The earlier run named `timing-front-left-01` was retrospectively confirmed by the
owner to be rear-left. [Label correction](port-timings/left-label-correction.json)
is retained alongside unchanged original results. The final front-left sample
was explicitly requested and owner-confirmed. Logical results: rear port1/DP-1,
front port2/DP-2, right port3/DP-3 on this boot; logical names are not permanent
physical labels across other boots.

On unplug, partner loss and desktop disappearance fell in the same sample for
right/rear, and about 0.5 s apart for front. Same-sample means below the observation
resolution, not instantaneous disable. Separate detailed kernel/compositor
lifecycle instrumentation is the next step for optimization. About 3 s precedes
dock enumeration, so compositor-only changes cannot account for that entire
interval. Do not shorten debounce/recovery timers based on this pilot; the
millisecond-resolution [DOCK-LATENCY-BREAKDOWN.md](DOCK-LATENCY-BREAKDOWN.md)
is the evidence for the 40 ms hotplug debounce.

The read-only poller is `mseries/hardware/dock-port-timing.py`; it requires an
identity-bound hardware receipt from the running boot and a fresh private output
folder. Five state-machine tests pass, including the boundary fix. It changes no
hardware settings. Repeatability, suspend, real `.20` recovery, Vulkan/long-run
GPU and controlled energy comparisons remain unqualified.
