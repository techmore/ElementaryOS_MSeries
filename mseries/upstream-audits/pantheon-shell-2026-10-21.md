# Customized Pantheon shell upstream pass — 2026-10-21

Audited source baseline `origin/dev` at `3f85e233a7736cbf3b6a04a384f514ab422cd8f5`.
GitHub API comparisons against each public upstream default branch are retained
in [the machine-readable receipt](pantheon-shell-2026-10-21.json). Those comparisons
record exact heads, commits and changed paths. This is a source-maintenance pass,
not an inventory of installed/running binary revisions or factory qualification.

## Coverage and decisions

| Customized surface | Retained pin | Current upstream delta | Decision |
| --- | --- | --- | --- |
| Gala | `f0791434ac40a50f2aec64700a47b3bb04145752` | 26 commits to `79fb49f5d34d15c91259d50e0010ff35e3c7ee50`; removes X11 window-manager paths and GTK3 daemon, adjusts shell initialization, notification handling and gestures | Requires a deliberate compositor/session integration port. Preserve current screen corners, drawers, OSK and snapping patches. No wholesale rebase. |
| Wingpanel | `6b8ae0453b1fd6dc07bd246642998011f04b2125` | 3 commits to `e737de88bc02ddc82a9f4d23f574cc3c04098c03`: focus handling, Mutter46 requirement, semantic CSS | Focus changes overlap customized PanelWindow. Review independently with private focus probes; do not restart owner's panel. |
| Dock/taskbar | `8b45a68a122947ad3a6427bf6e159ec2acf04ad0` | 28 commits to `2b70be3e0cb39ff0e421f24bc1a2f733e0614eac`; ItemManager ownership, background duplicates, icon clipping, several memory leaks, workspace visibility and translations | Stage individual backport candidates against the complete taskbar source. Preserve Start, CodexBar, source hashes, existing tracking and owner-tuned markers. |
| Quick Settings | `fb721d4b5640a2a25ae011370c8fe8aaff8d93f4` | Identical to upstream default branch | No upstream bump. Remove duplicated desktop preparation steps so brightness, charging, audio/AirPlay, Bluetooth, layout and text scaling consistently use the same helper as factory/package builds. |
| Power indicator | `e05723d8cba82b596a5efc259b4e0d15ad9a2bc4` | One Swedish translation commit to `8a11cb2fe8f0848d05c60528c85273da4a014d0e` | No behavior fix to port. Preserve charge ETA, watts, toggle and history patches. |
| Network indicator | `8685ec8e55a45e48da0c12931a353cd440d11664` | Identical | Preserve throughput, VPN null guard, opt-in rates and usage views. |
| Bluetooth indicator | `f67e65d09a8ab046f54895a326273dce5c491430` | One Swedish translation commit to `6c7858a340a568f3702f96e861e0667bd32cdc48` | No behavior fix. Retain control-center integration and greeter/background behavior. |
| Keyboard indicator | `2d086e0177d7aa9a9e6aa4eb11fa7fb77c628c76` | Identical | Preserve active-popover patch. |
| Sound indicator | `8b7991c9156ac8127d27559506baea8e6fb72e5b` | One Swedish translation commit to `115d1495b754e2692c112fa5b02f9f3b5860a314` | No behavior fix. Preserve icon initialization patch. |
| Applications menu | `06d7170edab4d1f93ebd14173a0e2afea98e9339` | Identical | Preserve compact icons and grid customizations. |
| Files chooser portal | `f966e0108` (existing installer pin) | 20 commits to `8f4915ea6a3eebc5c510b8e29bbdd6f7049ee009`; sorting, breadcrumbs/sidebar leaks and portal theme-handler relocation | Upstream `d4dc2c2c1` moves Granite settings from portal startup into dialog construction, overlapping our startup-deadlock workaround. Qualify a replacement against private activation/theme probes before retiring the local fix. Do not stack overlapping fixes blindly. |

Primary sources are linked by each `compare_url` in the JSON. Specific next
candidates: [Dock Launcher binding lifecycle](https://github.com/elementary/dock/commit/1f55ec4c5),
[Wingpanel focus handling](https://github.com/elementary/wingpanel/commit/35d163ee8),
and [Files portal theme initialization](https://github.com/elementary/files/commit/d4dc2c2c1).
The branch watcher currently emphasizes hardware/local-AI upstreams; this receipt
explicitly covers shell ports rather than treating that watcher as complete
Pantheon coverage. Translation-only movement is not a reason to churn working
native builds.

## Focused patch and verification

`install-quick-settings-brightness.sh` now invokes
`quick-settings/prepare-source.sh` instead of maintaining a second core patch/copy
sequence. The desktop-only Share Eyes/AirDrop wiring remains after that helper.
No upstream pin, widget code, indicator binary, desktop setting or service changed.

Verification on two fresh checkouts of upstream Quick Settings at the retained
pin:

1. Applied the original desktop core sequence and the shared helper separately;
   recursive file comparison excluding `.git` found byte-identical source trees.
2. Built the helper-prepared core with Meson/Ninja: native `libquick-settings.so`
   linked successfully (239 build steps).
3. Applied the retained desktop-only sharing extras and rebuilt: native module
   linked successfully (37 incremental steps), including Share Eyes and AirDrop.
4. Three routing regressions pass: desktop invokes the helper once before its
   extras; package/factory consumers still invoke it; extras remain wired.
5. Existing private D-Bus/Xvfb fake-BlueZ probe passed saved-device filtering,
   connect/disconnect, error recovery and power-off/on. No real adapter was used.
6. Bash syntax, ShellCheck at warning severity and `git diff --check` pass.
   Default ShellCheck still reports the installer's existing informational
   SC1091/SC2015 entries. Generated Vala C emits existing compiler warnings; no
   native build failure occurred.

Build host dependencies: GTK4 4.22.4, Granite7 7.8.1, Wingpanel9 API package 8.0.4.
The source parity check covers the installer refactor; no altered user-visible
layout required screenshot acceptance. Real Bluetooth devices, live panel
loading, shell focus and hardware remain separate gates. No installation,
Wingpanel/dock restart or desktop mutation was performed.

Next iteration: stage the Dock binding lifecycle candidate in a fresh complete
customized source tree, retain all custom-source hashes, and exercise launcher
creation/destruction and badge behavior before proposing a deployment.
