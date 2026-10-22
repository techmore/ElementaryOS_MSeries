# Signal on Pantheon: implementation boundary

Status: the current integration is an intermediate theming and desktop-integration layer, not a native GTK/Granite client. The release gate is tracked in [#227](https://github.com/techmore/ElementaryOS_MSeries/issues/227).

## Recommended implementation

Keep Signal's official Desktop client as the messaging implementation and make its Linux experience fit Pantheon through a small, reversible integration layer. Signal Desktop is an Electron/TypeScript application; its own README describes it as the desktop client for Windows, macOS and Linux. The official `libsignal` repository publishes Java, Swift and TypeScript client APIs, but explicitly says use outside Signal is unsupported and that APIs can change without notice. It is not a stable GTK messaging SDK.

This boundary preserves the upstream implementation that owns device linking, encrypted storage, message synchronization, groups, attachments, calls and protocol changes. A new GTK frontend that reads or writes Signal's private profile would create a second client against private state and is not an acceptable substitute.

| Layer | Owns | Maintenance rule |
| --- | --- | --- |
| Official Signal Desktop | Account/device link, encryption, message data, calls and sync | Install only a signature-verified upstream release; preserve its profile and rollback path. |
| Pantheon integration | Desktop identity, launch/tray behavior, notifications, system accent and screenshot transfer | Keep changes narrow, reversible and isolated from the account database. Rebase the accent map from a pristine release after each upstream update. |
| GTK/Granite native client | No current implementation | Treat as a separate port proposal requiring an upstream-supported client API and an explicit security/maintenance plan before implementation. |

## Current state and limits

`install-signal.sh` installs the signed ARM64 beta. `signal-accent.py` patches a mutable release's bundled CSS to follow the system accent; the launcher refreshes that patch at startup. `--atomic` keeps the verified release tree unchanged and therefore does not receive the accent patch. The Wingpanel indicator and desktop entry provide Pantheon launch behavior. These pieces change presentation and integration only; the message client remains upstream Signal Desktop.

Signal's own **System** appearance preference should select light or dark mode. The accent patch must not rewrite chat colors or avatars. Acceptance still needs to verify both appearances, text/control readability and intended logo surfaces on the installed release; Electron's Linux theme detection is a runtime dependency, so a source-level color map alone does not prove it follows Pantheon's preference.

The screenshot shelf retains the original regardless of drag outcome. A completed drag is not acknowledgement from Signal. Acceptance must inspect the actual compose preview and content without sending, cover multiple images and copy/paste fallback, and record the XWayland shelf → Wayland Signal case. Preserve the isolated profile and exact client/tool revisions in the receipt. See [the screenshot-shelf guide](screenshot-shelf/README.md).

## Acceptance before calling the integration complete

- Verify accent, light/dark appearance, typography, controls, contrast and logo behavior on a throwaway Signal profile after an upstream update.
- Verify the Signal tray item activates the app and unread state remains legible in Wingpanel.
- Drag a screenshot from the shelf and inspect the actual Signal attachment preview and content; repeat with multiple screenshots and the copy/paste fallback, without sending.
- Repeat the drag on each supported display/session combination. Confirm a refused or unreadable drop leaves the saved original available for retry.
- Record app version, shelf revision, display backend, observed result and any failure. Keep #227 open until this owner-session evidence exists.

## Upstream references

- [Signal Desktop](https://github.com/signalapp/Signal-Desktop)
- [libsignal: overview, API stability and supported language bindings](https://github.com/signalapp/libsignal)
