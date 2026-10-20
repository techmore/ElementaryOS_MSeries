# Gesture deployment — 2026-10-20

Installed package: `0.1.0+git432fe4b+gestures.20261020`. It is **not loaded**: the active
compositor still uses its previous executable and requires a normal new login.
No compositor or Wingpanel restart was requested.

## Source separation

- PR #326 feature source: `806cde7` (includes latest dev cursor at `6073858`).
- Independently installed source discovered during packaging: `432fe4b`.
- Combined deployment source: `314652f` on `codex/gesture-deployment`, which
  preserves the installed Windows Work Mode top-panel interface and taskbar
  clearance code. Do not merge this integration branch as a substitute for
  separately reviewing PR #326 and the Work Mode PR #329.
- The PR-only package was not installed, to avoid dropping those modifications.

## Verification

The combined source passes all 38 all-feature tests and Clippy with warnings
denied. Release packaging succeeds using the shared Cargo target directory.
The nested Xvfb/D-Bus/GTK Cairo gesture smoke passes actual pixel displacement,
cancellation/restore, edge resistance, overview scaling/commit, interrupted
springs and reduced-motion release. Production binary strings confirm no
private gesture-probe socket, and the Work Mode panel interface is retained.
The installer `--verify`, schema compilation and linked libraries pass.

Package SHA-256: `d80de0b83637592c5e649c406ed7b056897aea76ac8816e8497049056f8545ba`

Installed binary SHA-256: `fab2b8c02308cd51c9286949340a6875f4ba0666de9ca0045dc1f9b72f733aed`

The installed payload hash matches the package. Compositor PID 1944 and
Wingpanel PID 2135/start times are unchanged. The running compositor SHA-256
remains `1b75b24d8fc74d45e7dbebdcb28fdca57ab5b9b1f03eb8a29b91068b9803ba88`.
The dock restarted from PID 153271 to 160644 at 10:38:17 during concurrent work;
this task issued no restart and its systemd unit was identical before/after.
The service is active. Restart attribution is unverified; no claim is made
that every process stayed unchanged.

## Local receipts and rollback

Directory: `/home/sdolbec/Documents/Codex/gesture-animation-package-20261020/`

- `combined/pantheon-rust-compositor_0.1.0+git432fe4b+gestures.20261020_arm64.deb`
- `deployment.json` (package and process hashes, installed/loaded state)
- `combined/smoke/measurements.json`, screenshots and logs
- `verify.log`
- `pantheon-rust-compositor_0.1.0+git432fe4b_arm64.rollback.deb`
  rebuilt from the installed files before replacement; its compositor payload
  hash was verified against the previous installed binary.

Rollback stages the previous binary for a later login; it does not restart
this desktop:

```sh
sudo dpkg -i /home/sdolbec/Documents/Codex/gesture-animation-package-20261020/pantheon-rust-compositor_0.1.0+git432fe4b_arm64.rollback.deb
systemctl --user daemon-reload
```

## Next login qualification

No physical trackpad pass is claimed yet. At a normal logout/login, check that
workspace and overview swipes track fingers, short/cancelled gestures return,
workspace edges resist, tap-to-click/natural scroll match Switchboard settings,
and client two-finger pinch zoom still works. Native frame pacing, multi-output
and mixed Wayland/XWayland previews remain open. Keep the currently installed
Work Mode/taskbar behavior in the comparison. The settled overview still
configures clients once; minimum sizes may affect its endpoint.
