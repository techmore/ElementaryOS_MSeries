# Unified T3 native panel — October 26

- Complete pinned dock build, production launcher keyboard/pointer/tracking,
  marker/size and hover suites pass (`test-build.sh`). Latest linked dock menu
  light/dark fixtures pass: hover/focus, pin/toggle, tabs, closed polling and
  Activity/Fleet/Open T3. The rebuilt dock is installed and running.
- New native host light/dark fixtures pass: no second popover, unopened usage,
  live/stale badge, tabs, no snapshots in the six-second closed interval and
  three desktop-action/host-close routes. Screenshots retained; inert helpers
  and private HOME/buses, no real provider request or SSH.
- `check-codexbar-port.sh` passes, including v0.78.0 pin/custom helpers, 18 native
  suites and live snapshot schema. No secret/account snapshot retained.
- Full Debian package builds with the new module, native settings and assets;
  corrected installation destination is outside Wingpanel discovery. Private
  filesystem/service cutover test preserves all three rollback modules and
  asserts the host stops before active-directory migration.
- Initial staging caused an unwanted automatic Wingpanel restart. The retained
  trace shows `.so.new` hot-loaded against the old exported constructor. The
  corrected default installer stages outside discovery and preserves the
  recovered panel PID. Explicit activation is separate. Runtime map receipt
  shows only the unified module, no legacy module. This proves loaded code,
  not physical menu/focus/account acceptance. No further reload was requested.
- T3 server/front-end remain running; remote hosts left unconfigured per owner.
  Whole-chat checks remain deferred. No factory boot or Machine Lab changes.
