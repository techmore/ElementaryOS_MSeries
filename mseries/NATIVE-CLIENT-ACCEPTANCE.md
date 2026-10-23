# Signal and Messages completion gates

This ledger tracks the original native-client objective and the selected official
Signal integration path. A passing source or fixture check does not close a live
acceptance gate. It supersedes subjective percentage estimates.

| Gate | Current evidence | Remaining acceptance |
| --- | --- | --- |
| Shared Rust/GTK/Granite SDK use | Messages uses mseries-pantheon-kit; combined 30 library tests passed | SDK v1 stability audit remains issue #535 |
| Messages package | Latest ARM64 package installed user-locally; binary hash matches release and absolute launcher validates | Owner-session launch/UI acceptance |
| Messages recovery and API errors | Private GTK/D-Bus test passes unavailable service, Retry, v99 rejection and v2 recovery | Actual owner service/session |
| Messages compose/outbox | Synthetic confirmed, failed and unknown send outcomes pass through actual GTK app | Owner-approved live phone sends; no fixture result proves delivery |
| Phone isolation | A/B/A drafts, mixed-refresh rejection and delayed old-phone response tests pass | Live phone switching; backend atomic snapshot identity contract |
| Messages navigation/scaling | Actual 520/1040 resize, Back/reselect and enlarged-font transitions pass | Broader scales, long-content bounds and hardware layout |
| Messages light/dark | Explicit io.elementary.stylesheet.blueberry and :dark GTK runs pass; four captures reviewed in /tmp/messages-review-{light,dark} | Long-name/unbroken-body light/dark review passed after wrapping fix; broader error/selection states and contrast/accessibility review remain |
| Keyboard/assistive technology | GTK test backend validates eight explicit control labels and two button roles; Ctrl+F/Escape/Back and viewport interactions pass | Complete keyboard focus/order and screen-reader interaction |
| Feature parity/localization | Migration inventory in RUST-PANTHEON-CLIENTS.md | Source comparison in MESSAGES-PARITY.md identifies implemented refresh viewport parity and active-window read guard; localization and live behavior remain |
| Phone pins | Validated UUID/keyring/import source and tests | BlueFerry release with merged phone ID field, then live acceptance (latest public v0.8.1 lacks it) |
| Signal client boundary | Official signed client with Pantheon overlay/tray/launcher; PR #525 | Owner-session theme/tray/update/rollback acceptance; not a Rust Signal UI |
| Screenshot full workflow | Native release passes nested +3/+4, region/window, orientation, cancellation, saving, sound requests, shelf/expiry/retention | Privileged package installation, next login, native DRM/audio/input acceptance |
| Signal attachments | Shelf retention regression suite passes | Actual multi-image compose preview/content, Copy/Paste, Wayland/XWayland; do not send |
| Publication/CI | PR #525 open; PR #526 draft; latest Messages CI pending without an assigned job | Required head checks, release review and publication |

## Deployment boundary

The verified screenshot package is recorded in OS9-HANDOFF.md. This executor's
no-new-privileges flag prevents sudo; the owner must install it from their terminal.
Installation does not restart the compositor. Only a later login loads it.
The installed compositor remains 0.1.0+git75c2c3df at the latest read-only check.

## Next batch

Finish long-content/theme/accessibility acceptance and latest Messages packaging
while the privileged screenshot install is pending. Preserve unrelated updater
edits. Do not mark the goal complete while any required gate above remains open.
