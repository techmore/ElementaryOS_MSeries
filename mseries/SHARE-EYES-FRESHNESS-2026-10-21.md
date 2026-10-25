# Share Eyes freshness and native upstream check — October 21, 2026

Source review began on `dev` at `8610f72b`; the patch was integrated onto
current `dev` `45632062` with all concurrent changes preserved. All edits isolated. No installed indicator,
Wingpanel, live share, Transmission daemon or session was changed.

## Confirmed Share Eyes defect and fix

`ShareState.parse` previously accepted every future heartbeat because
`now - updated <= 15` is also true for negative ages. A clock correction could
therefore leave an old launcher marked running/live until the future time passed.
The existing state contract says absent/stale launcher evidence is not live.

The parser now requires a positive timestamp no later than the current clock,
then applies the existing inclusive 15-second freshness window. Invalid evidence
uses the existing cleared-state path: live/viewer/port/credentials/URLs reset.
The next valid heartbeat recovers normally. This changes no media protocol,
permissions, network address, viewer cap or backend behavior.

- Added regression fails against the original parser at the future-timestamp
  assertion, then passes with the guard.
- Cases: future time/clock rollback; zero and absent heartbeat; count/credential
  clearing; exactly 15 seconds fresh; 16 seconds stale; next valid heartbeat.
- Meson `share-state` test passes. Native `mseries-share-eyes` and render probe
  compile with GTK 4.22.4, Granite 7.8.1, libsoup 3.6.6 and JSON-GLib 1.10.8.
- Private D-Bus/Xvfb, memory settings and synthetic future-state file: narrow
  360-pixel light/dark probe renders show sharing off and Start Screen Share.
  Existing probe snapshots have transparent backgrounds; this is state/render
  evidence, not a new contrast or assistive-technology certification.
- Live clock changes and sharing were not tested. The normal Quick Settings
  preparation embeds these source files; a standalone build does not deploy them.

## Torrential upstream

[Upstream rewrite](https://github.com/davidmhewitt/torrential) `main` remains
`3af2c2ab473d074bb95a63a3bb185d5809ee8d8a`, checked with GitHub's commit API and
`git ls-remote` on October 21. It is the same baseline used by the private native
fork. Upstream README still describes an unreleased Rust rewrite. No upstream
source delta is available to merge.

The fork's actual default branch is `mseries-native`, clean local/source revision
`6ab0de5`; its backend and UI/close fixes are preserved. Existing PR #1 proposes
`serde_with` 3.12.0 → 3.24.0, but is one commit ahead/four behind this branch and
has no checks. Its lock update is not in the native branch. Current inherited
workflows target `main`/JSON changes, so they do not establish native validation.
No dependency change or merge was performed. A separate native build/test CI
pass is the next gate before adopting that lock update.

The fork API still returns no license; the audited baseline has no license grant.
The existing private/optional packaging boundary is unchanged. No package was
built, installed or published, and no real torrent was added.

## Signal indicator

The custom `signal-wingpanel` is the project's local GTK 4 StatusNotifier host,
not a vendored Signal Desktop source fork. Its existing Meson module builds
against GTK 4.22.4, Gee 0.20.8 and the installed `wingpanel-9` pkg-config interface
(reporting 8.0.4). No compile failure requires an API replacement.

Two existing `Gdk.Texture.for_pixbuf` calls warn as deprecated since GTK 4.20;
these warnings do not show broken tray behavior. They are a scoped future
modernization opportunity with icon/pixmap fixture coverage. No Signal account,
real tray item or running panel was used for verification, and no module was
installed or reloaded.

The freedesktop StatusNotifierWatcher documentation endpoint returned HTTP 403
in this review; no new protocol compatibility claim is based on that page.

## Next acceptance

Review the focused diff and hosted checks, then stage through the established
Quick Settings preparation. The running desktop stays unchanged until a separate
approved install/load. Screen-share TURN/cap changes still require the existing
matched-pair cost baseline and remain outside this fix.
