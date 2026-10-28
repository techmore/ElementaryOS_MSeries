# Log audit — 2026-10-26

Status (2026-10-28): the dock fix landed in #638. The dashboard overflow was
fixed in #598, which compacts watcher state instead of using the continuation
comments described below. This receipt keeps the audit record. The `/tmp` logs
it mentions were not retained.

Fixed the dock hover path reading Gtk.Popover.visible when a workspace/group item has no context menu. A production ContainerItem regression failed before the patch with the exact live gtk_widget_get_visible / GTK_IS_WIDGET critical; it passes afterward with fatal criticals enabled. Full pinned dock build, schema checks, policy/marker tests, light/dark pointer/menu/Escape/typing, hover/unified panel and five running-app tests pass. Patch applied through canonical preparation; upstream revision remains unchanged.

Installed dock SHA-256: bc7a7789d27beb49810f887c33bd8c3c7c5afa049e2932de543ff5618bb8d2a4. Installed for next login, NOT loaded. Existing dock PID 431232 and Wingpanel PID 430738 were not restarted. No live Work Mode switching. Private logs: /tmp/log-audit-dock-before.log, /tmp/log-audit-dock-after.log, /tmp/log-audit-dock-stage.log.

Fixed the upstream-watch workflow's confirmed dashboard size failure (run 40327523535). The issue already held 378 snapshots / 173 pending changes and 63,337 characters. Overflow now uses bounded integrity-checked immutable continuation comments on the same issue, preserving state and acknowledgments; the root body is updated only after continuations succeed. Old inline/plain formats remain readable. Failure leaves previous root/state authoritative; orphan continuations after an API failure are retained rather than deleted. Full dashboard state is now retained in the workflow artifact too. Six synthetic API tests pass (overflow/roundtrip, acknowledgement, reuse, failed writes, corruption, wrong issue/author and bounded preview cases); existing 28 assistant contracts pass. New tests wired into PR validation. No actual issue/comment was written or watcher dispatched during this audit; workflow repair is source-only pending merge/run.

Restored the failed xdg-document-portal user service: active PID 507013, Documents.GetMountPoint returns /run/user/1000/doc; user failed-unit list empty. No document database/configuration changes.

The earlier native UI AirPlay timeout did not reproduce: the current full matrix passed all 12 surface/theme/scale cases. Latest native wiring run 40331180615 is green. Deprecated GTK/GIO and virtual-X DRI3 messages are not compilation failures.

Open findings: 408 observed Smithay unknown-popup errors need a protocol lifecycle reproducer; do not suppress them. Rupert off-host backup repeatedly times out waiting for its remote service (separate repository/service, not repaired here). WirePlumber unaligned latency and tas2764 over-current kernel messages need dedicated audio/hardware diagnosis; no audio/kernel settings changed. Historical notification startup failure recovered automatically; the current notification service is active. No broad source or hardware completion claim.

Unrelated Work Mode drafts in the original checkout remain untouched. Kiosk deployment remains paused for the owner's partition reboot; see the separate elementaryos-i3-kiosk repository handoff.
