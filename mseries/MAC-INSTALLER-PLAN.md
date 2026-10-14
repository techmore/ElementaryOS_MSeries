> **Status 2026-10-14: NOT PURSUED.** The owner decided against building this installer. Kept as a record of what was studied; do not start work from it. `bin/elementary-mac-setup` remains the install path.

# Plan: a native macOS installer for elementary OS (modelled on omacom/omarchy-mac-installer)

Requested 2026-10-14. Source studied read-only: [omacom/omarchy-mac-installer](https://github.com/omacom/omarchy-mac-installer)
(MIT, created 2026-09-20, active daily, 15 stars; extracted from maralcbr/omarchy-mx-mac). Nothing was cloned,
built or run. Today our installer is `bin/elementary-mac-setup`, which runs from an existing Asahi Arch Linux
install (unverified on hardware); the goal is the Omarchy experience: download a Mac app, click, and boot elementary
OS beside macOS, with no USB stick and no terminal.

## What Omarchy's installer is

| Part | What it does | Where |
| --- | --- | --- |
| macOS app | One-page UI (SwiftUI), model admission, release-channel choice, progress | `Sources/OmarchyAppleInstallerApp` |
| Privileged helper | Does the disk work as root (partition, copy, boot object) | `Sources/OmarchyAppleInstallerHelper` |
| Trust core | Verifies a signed catalog and a signed release before touching the disk | `Sources/OmarchyAppleInstaller`, `Release/` |
| Engine | Pinned Asahi installer v0.9.2 + m1n1, driven through a Python overlay | `Engine/` (`source-lock.json`) |
| Image producer | Builds the payload zip: ESP and root images, UUIDs, `installer_data.json` | `image-builder/` |
| Packaging | Signed, notarized `.pkg` (Developer ID) | `Packaging/` |
| Tests | Portable suite `bash test/all` (Linux ok), Swift debug/release tests, VM acceptance | `test/`, `Tests/` |

Its README is careful about claims: it states which images passed VM acceptance and which physical Macs were tested.
We keep the same rule (see `AGENTS.md`): a source build is not an installation result.

## How we adopt it

1. **License and provenance.** MIT: keep its `LICENSE`, copyright notice and Git history; record the exact upstream
   commit in `UPSTREAM-PINS.md`. Do not copy its signing keys, identity, catalog URLs or release infrastructure; its
   README says those target the original publisher. Check the Asahi installer pieces in `Engine/` keep their own
   licenses.
2. **Where it lives.** Recommended: a separate repository (`ElementaryOS_MSeries_Installer`) imported from upstream with
   history, so the Swift/Xcode project, signing and macOS CI stay out of this Linux image repo. This repo links to it.
3. **Retarget the payload (the real work).** Omarchy's payload is an Arch Linux ARM root plus Limine behind m1n1 and
   U-Boot. Ours must be the elementary OS (Ubuntu resolute, Pantheon) root built by our mkosi pipeline, in the same
   Asahi installer package shape: ESP image, root image, `installer_data.json`, with our kernel (fairydust-usb4 for now;
   Aurora is a candidate, see `WATCHLIST.md`) and boot chain. Write `build-mac-image` equivalents for mkosi rather
   than reusing the Arch scripts.
4. **Rebrand.** New bundle and helper identifiers, name, icon, LaunchDaemon label, catalog and release descriptor under
   our own signing key. Check use of the "elementary" name and logo with elementary's trademark policy before shipping.
5. **Safety model.** Keep what makes it safe: model admission (refuse anything not qualified), signed catalog and
   release verification, resumable/idempotent helper steps, credential-free logs, recorded disk-state fixtures from real
   Macs (it ships an M1 Pro fixture set).
6. **Qualification ladder.** Portable tests on Linux -> Swift tests -> simulation UI -> VM acceptance of the image ->
   physical install on a backed-up Mac. Each rung is recorded; only the last counts as an install.

## What blocks us (needs the owner)

- **A Mac with macOS, Xcode and Swift 6.2+** (Omarchy requires macOS 15+). This M1 Pro runs Linux with no Swift. The work
  Mac mentioned in `ROADMAP.md` would do for builds only if its policy allows.
- **Apple Developer ID and notarization** for a distributable app (paid Apple Developer Program). For personal testing an
  ad-hoc signed build can run on the owner's own Mac.
- **A qualified image.** Our factory ISO builds but has not booted on hardware; the installer cannot be qualified before that.
- **A Mac to test on.** Install work touches the partition table. Use a backed-up spare, not the daily driver.
- Hosting for the catalog and releases (GitHub Releases is enough to start).

## Phases

0. (no Mac needed) Import upstream into scratch/new repo at a pinned commit; read `docs/extraction.md` and
   `docs/validation.md`; run the portable suite on Linux; list every Omarchy- or Arch-specific assumption; write the payload spec for
   an mkosi/Ubuntu root.
1. (Mac with Xcode) Build and run in simulation; rebrand; keep tests green.
2. mkosi payload producer and VM acceptance of the image.
3. Signed catalog on our own key; unsigned/ad-hoc app for a physical test on an owner-approved, backed-up Mac.
4. Developer ID, notarized package, public release. Until then `bin/elementary-mac-setup` remains the documented path.
