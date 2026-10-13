# M-Series bug-fix audit

Audit date: 2026-10-13. Target: elementary OS 9 Early Access on
MacBookPro18,3 (M1 Pro). The installed desktop boots with kernel
7.1.13-1-2-fairydust-usb4-ARCH. The separate mkosi factory ISO built successfully in run 38396499561 but
has not been hardware-booted. See FIRST-ISO-BUILD.md. A working transformed installation is not evidence
that the factory image works.

## Fixed in this update

| ID | Finding | Change |
| --- | --- | --- |
| DOC-01 | The README and public status page said no M-series desktop had booted, while the M-series setup guide recorded a working M1 Pro desktop. | Clarified the distinction between the installed desktop and the unverified factory ISO. |
| CI-01 | The M-series validation workflow omitted transform scripts, the root mkosi configuration, repositories, and the arm64 package manifest from its change filters. A change in those paths could skip the workflow. | Added those paths to the pull-request trigger. |
| CI-02 | The fork scheduled a daily release workflow that required elementary's signing and R2 credentials. | Replaced it with a manual arm64 build that retains logs and experimental installer artifacts without those credentials. First arm64 image build succeeded on October 13. |
| IMG-01 | The hardware overlay prunes package payloads, but its arm64 consumers did not explicitly install all of its runtime dependencies. ExtraTrees does not resolve apt dependencies. | Added runtime packages to liveiso and sysupdate arm64 configs, with a regression test for both consumers. |
| IMG-02 | Overlay finalization deleted the brightness helper and its autostart entry before they could reach the final images. | Retained both paths and added a temporary-image regression test that runs the real cleanup script. |
| IMG-03 | ISO assembly hardcoded the APT disc metadata directory to binary-amd64 even for arm64 builds. | Select the Debian architecture from the actual target; arm64 images use binary-arm64. Pending rebuilt-image verification. |
| IMG-04 | xorriso warned that the image volume ID did not comply with ISO 9660. | Normalize the label to uppercase ASCII/digits/underscores, capped at 32 characters. Pending rebuilt-image verification. |
| UP-01 | Current elementary OS 9 upstream includes systemd-coredump, but the original M-Series base did not. | The current branch now includes the upstream merge at 7024fd04646a6a8565bf6805989b59fd72de928c. |
| SRC-01 | The port map still presented omarchy-mac/quattro as the current Apple hardware source. Package development moved to omacom/omarchy-mac-pkgs. | Recorded the current package repository and audited revision; retained the old pin as history. |
| DOC-02 | The public feature table described an untested generic kernel plan as if it were the status of the running M1 Pro, and the CodexBar description no longer matched its compact quota rows. | Rewrote the support page around observed host evidence and corrected the desktop notes. |
| DOC-03 | An older optimization audit said ambient keyboard lighting was missing, although the Pantheon helper is implemented and was measured on the M1 Pro. | Corrected the audit: ALS-to-UPower automation works at 141 lux; only interactive lock/lid and suspend qualification remains. |
| DOC-04 | The arm64 package notes said the Asahi speaker packages had no Ubuntu source, but resolute/universe provides the installed versions. | Updated the manifest and build notes; the factory image still needs to package the tested audio setup. |

These source and image changes at commit 401dad7 passed a factory-image
build; hardware qualification remains pending.

## Open fixes and verification

| Priority | Finding | Concrete next step | State |
| --- | --- | --- | --- |
| P1 | Candidate Gala failure: an IBus input-purpose change may arrive while its on-screen keyboard is disabled, when the GTK4 helper's model manager is null. | Reproduce with the OSK disabled and a focused text field. If confirmed, add a null guard through a package-safe build and verify recovery across package upgrades. | Needs reproduction |
| P1 | A Dell WD19S display connected through the Apple USB4 dock path still has no DisplayPort tunnel. The experimental kernel now brings up the hub and downstream input, but the display connector is absent. | Continue the kernel and device-tree work; verify one external display on the M1 Pro and record hot-plug/reboot behavior before claiming support. | Known kernel limitation |
| P1 | Suspending with a USB4 dock attached is blocked by the ACIO driver; the machine stays awake with its display off. | Implement and qualify the ACIO sleep/wake handshake, or provide a safe docked-lid mode that locks without suspend retries. | Reproduced; tracked in ROADMAP.md |
| P1 | Non-USB4 USB-C devices can disappear after suspend because the Apple Type-C PHY and DWC3 drivers lack system-sleep power management. | Add kernel resume handling and verify dock/adapter recovery through repeated suspend cycles. | Kernel bug |
| P2 | Wingpanel can crash in PanelWindow.on_realize and Gala respawns it. | Capture the exact upstream version and logs, then report or patch the upstream Wingpanel failure. | Known upstream issue |
| P1 | The factory arm64 ISO built successfully but has not been booted on hardware. | Independently verify the installer checksum, qualify the kernel and boot path, and complete hardware post-boot checks before a stable release. | Validation blocker |
| P2 | The installed desktop guide has not yet confirmed physical display-brightness key presses and persistence after a fresh login, although the Mutter backlight and OSD calls succeed. | Verify both keys and the selected level after logout/login; record the exact result. | Needs owner check |
| P2 | Ambient keyboard lighting has a successful sensor/API check, but lock/lid transitions and suspend/resume are not qualified. | Verify that the helper leaves the light alone while locked or closed, then resumes safely after unlock/open and suspend. | Needs interactive check |
| P2 | The transformed desktop can play through the Apple speaker safety/DSP chain using packages already available in Ubuntu resolute, but the factory image does not install them or the matching PipeWire LV2 plugin. AVD firmware and its VA-API bridge are also absent. | Package the tested audio chain into the Ubuntu image without bypassing speakersafetyd; separately identify compatible AVD kernel, firmware, userspace sources, and licensing. | Image packaging gap |
| P2 | Wi-Fi firmware provisioning and resume recovery are present in the image layer but lack a fresh end-to-end test on an M1 Pro booted from that image. | Confirm firmware source, connect, suspend/resume repeatedly, and capture service/kernel logs from the factory image. | Needs image test |

## Porting boundary

The current Apple Silicon behavior reference is
[omacom/omarchy-mac-pkgs](https://github.com/omacom/omarchy-mac-pkgs), audited
at main commit 222f7a8599bbdd287ac6a95362cd51c5b024baae. Its packages target
Arch Linux. This project should translate relevant behavior into Ubuntu,
mkosi, systemd, and Pantheon/Gala; it must not import Arch package scripts or
hooks. Apple-specific changes to those packages remain in that repository,
general Omarchy changes go upstream, and one-shot installation belongs in the
Omarchy Mac installer.

## Evidence

- [M1 Pro desktop setup](DESKTOP-SETUP.md)
- [Current Omarchy hardware audit](OMARCHY-AUDIT-2026-10.md)
- [USB-C dock and DisplayPort status](USB-C-DOCK-DP-ALT-MODE.md)
- [Factory image post-boot checklist](POST-BOOT-CHECKS.md)
- [Upstream source pins](UPSTREAM-PINS.md)
