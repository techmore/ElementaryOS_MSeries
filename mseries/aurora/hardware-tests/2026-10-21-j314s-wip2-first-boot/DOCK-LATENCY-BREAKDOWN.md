# WD22TB4 plug-to-picture latency breakdown — October 21, 2026

Millisecond-resolution decomposition from the kernel/compositor journal of one
boot (Aurora 7.2 wip2 kernel, J314S, WD22TB4, 1080p60 monitor). Eight plug
cycles across all three ports; every cycle lands within ±0.03 s of the table, so
the delay is deterministic, not intermittent. Complements the 0.5 s polling
pilot in [PORT-TIMINGS.md](PORT-TIMINGS.md); it does not replace owner
confirmation of visible pixels.

| Stage | Time | Owner | Evidence in the journal |
| --- | --- | --- | --- |
| ACIO firmware boots, first lane-init attempt | 2.36 s | Apple ACIO firmware | `lane_init.c:936: Timeout reading AT register` ×21 at 100 ms, then `lane_init.c:954: SBX disconnected!` |
| Lane-init retry reaches Connected | 0.10 s | Apple ACIO firmware | `lane_init.c:1024: Entering Connected` |
| Connected to Thunderbolt device found | 0.53 s | firmware + `thunderbolt` | `lane=0/1 entered CL0!`, then `thunderbolt 0-1: new device found` |
| Device found to DCP `connected:1` | 1.00 s | kernel / boltd | retimer +0.24 s, boltd authorize done +0.66 s, DP tunnel (`allocated Type-C DPTX PHY`) +0.68 s, HPD +0.92 s, `dcp_hotplug() connected:1` +1.00 s |
| DCP `connected:1` to output mapped | 0.50 s | **compositor** | 250 ms `EVENT_DEBOUNCE` + ~245 ms synchronous DCP modeset in `initialize_output` |
| Total, firmware start to mapped | 4.50 s | | |

Findings:

* About 89 % of the time is below the compositor. The single largest item is
  the ACIO firmware waiting 2.1 s for a sideband (AT) register read that the dock
  does not answer on the first attempt; the retry succeeds 100 ms later. This is
  the `lane_init.c:936` lead recorded on 2026-10-16 in
  `mseries/fairydust/usb4/evidence/2026-10-16-hpd-fix-tested-module-only-rebuild.md`,
  now attributed to a fixed per-plug cost. It is inside closed firmware; the
  open question is whether the dock is simply not ready until ~2.3 s after
  partner attach or whether the host could retry sooner.
* DP tunnel setup starts 20 ms after boltd finishes authorizing the dock (and
  the PCIe-C cold init that follows), every cycle. USB is not gated by it (the dock hub
  enumerates at +0.56 s, before authorization ends). Correlation only: test by
  checking whether the DP tunnel can be established before PCIe-C init
  (shared tunnel clocks, patch 0005) before changing boltd policy.
* Compositor share: the debounce was pure latency. The DCP uevent pair arrives
  ~9 ms apart with all 26 modes already populated, so the debounce is now 40 ms
  (about 210 ms saved per connect and per disconnect). The +1 s follow-up
  reconcile is unchanged.
* The DCP modeset (~245 ms) blocks the compositor thread, so the internal panel
  also stalls during it. Moving it off-thread is the next compositor-side item.
* The `link-status was Bad; reset to Good` write 32 ms after mapping is cheap
  (DCP logs `Already set to timingID` and finishes in ~5 ms).
