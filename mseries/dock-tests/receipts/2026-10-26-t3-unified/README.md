# Unified T3 taskbar delivery — 2026-10-26

One `TaskbarT3` instance replaces the two separate taskbar status anchors.
Usage embeds our maintained CodexBar account/quota/session/spend view; GitHub
embeds RepoBar's repository view. They are lazy and use on-demand monitoring.
The first longer close regression found the automatic refresh watch still
polling after dismissal; the final fix stops that watch and prevents late
callbacks starting another read while an embedded view is closed. Reopening
refreshes normally. Existing standalone indicator defaults are preserved.

The T3-server view keeps account quota and provider-wide tokens distinct and
marks old/missing timestamps non-live. Activity and Open T3 launch the installed
desktop actions. Activity is the existing native Shiplog-inspired page, not an
upstream QML shell. Tstack is a native request-preparation picker with nine
pinned upstream skills installed for local Claude Code and Codex. It never
sends automatically. Full chat, remote skill discovery and cross-provider
review execution remain unqualified/deferred in this dock-first delivery.

## Verification

- Pinned dock source `8b45a68a122947ad3a6427bf6e159ec2acf04ad0`, complete patch
  preparation and native build. Full clean launcher/marker/size/hover/tracking
  suite passes; final incremental build includes the refresh-watch repair and
  explicit launcher-popover disposal.
- `test-unified.sh PREPARED_SOURCE BUILD OUT`: linked production widgets with
  fake collectors, desktop launch actions, private non-activating buses and HOME.
  Final light/dark logs retained here. Checks hover focus, click pin/toggle,
  delayed close, lazy GitHub helper, tab switching, no closed usage snapshot
  polls across a full subsequent 5-second interval, and Activity/Open T3 routing.
- Actual dock on nested Pantheon Wayland: four layout transitions, open fixture
  remains tracked, removal on close. Final source passes. No live mode switching.
- Native T3: 78 library tests, strict debug clippy, release build in 35.90 s;
  isolated light/dark Activity, local quota and Tstack GTK probes. Screenshots
  here are synthetic/private-display evidence; no live desktop screenshot or
  owner acceptance is inferred. The native render sandbox now disables D-Bus
  service activation after the earlier default bus activated a portal during
  cleanup; the clean reruns succeed without that activation.
- App-only Debian package builds and contains the installer, all nine skill
  directories and MIT notice. Skills install/readback, executable helper mode and
  differing-user-file preservation checked in an isolated home; installed
  `mseries-install-tstack-skills --check` passes on the owner account.
- `bash mseries/check-codexbar-port.sh` passes; upstream pin remains v0.78.0.

## Installed and loaded

Used `rust/claude-pantheon-rs/install.sh --no-build` and the retained native
Meson build with prefix `~/.local/lib/mseries/dock`. Reloaded only the dock and
T3 front end (the latter through its existing `win.quit` action, then D-Bus
activation). No model turn was sent. The app action list now includes `tstack`.

Loaded T3 SHA-256:
`4a1c06cf493b00e262b923eba8f791d45698243936e10299fd3db7843ffa15fa`.
Installed/loaded dock SHA-256:
`2f5bc643ea4c1970293f6cff3d4fa4ae1bbd7cb267d11f3787cd7fd90aa9e8c7`.
At readback T3 PID 339319, dock child 339340; Wingpanel PID 197327 and T3 server
PID 1581 unchanged. Seven running app identities before/after, eleven unique
saved launchers, taskbar mode true, no stock fallback marker. Legacy Orchard
launcher IDs remain compatibility identities; owner product naming is Machine
Lab replacing Orchard. No local-machine app replacement is part of Fleet.

Startup still reports the previously documented `g_list_store_remove` and
`g_object_ref` criticals. This batch does not claim to repair them. Desktop
visual acceptance, live account actions, both-layout acceptance and #593 remain
open. Separate Wingpanel module deployments are staged without panel restart;
the currently loaded panel modules remain the prior build until next login.

Next: finish live menu review and dev integration, then implement the requested
native Remote Machines flow from the source-pinned Fleet Shepherd audit.
