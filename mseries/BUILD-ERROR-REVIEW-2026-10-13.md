# OS 9 build-log review — 2026-10-13

Reviewed /tmp/os9-build-38396499561/build.log from the successful
experimental build at source commit 401dad7919a004b3ed0cc624cdab1d48d6cd5919.
Image assembly succeeded; the ISO has not been boot-qualified.

## Fixed in the image sources

- **Invalid ISO volume ID.** The assembler now normalizes the label to ISO
  9660-safe uppercase ASCII, digits, and underscores, capped at 32 characters.
  This logic is covered by mseries/test-iso-label.sh and the validation
  workflow. Rebuild run 38400807824 includes this fix; its build log is not
  available until the job completes.
- **Duplicate messagebus sysuser.** 00-session.conf duplicated the account
  already declared by the D-Bus package. The custom duplicate is removed, and
  the D-Bus helper permission step now uses the messagebus group name instead
  of assuming numeric GID 987. An isolated systemd-sysusers --root check
  created the account without a conflict.
- **Tmpfiles diagnostics.** Removed the duplicate /var/spool/rsyslog rule,
  which the package already supplies, and changed the speech-dispatcher runtime
  directory from legacy /var/run to /run. Its sysuser home now uses /run too.

## Non-fatal build-environment or package diagnostics

These messages did not prevent image assembly and do not establish a defect in
the M-series overlay:

- D-Bus clients and NetworkManager cannot contact a running system bus or
  daemon inside the image-build chroot.
- Cryptsetup cannot resolve /dev/root or overlayfs because the build has no
  installed target block device.
- Early package triggers see tss, swtpm, and kvm before their system
  accounts/groups are created; later systemd-sysusers processing completes.
- systemctl preset-all reports package units already masked, including
  sudo.service, cryptdisks, x11-common, saned, alsa-utils, hwclock, and
  screen-cleanup. The sudo-rs command-line provider is installed; these
  service masks are not a reason to unmask units.
- systemd-repart skips /opt for the NVIDIA, SDK, and virtualization sysexts.
  The package roots contain no /opt payload, so there is no content to omit.
- io.elementary.tasks runs guarded migration cleanup for a legacy Flatpak
  ref and autostart file. The post-install script uses || true; package setup
  continues successfully when either old item is absent.
- The shim alternatives message is followed by selection of the available
  shimaa64.nx.efi.signed.latest. The image sets SecureBoot=no; actual boot
  qualification remains outstanding.
- Ubuntu package scripts also emit a malformed spice-vdagent unit-key
  warning, a Bash man-page alternatives error because documentation is omitted
  during package installation, init-script deprecation notices, and HPLIP
  SyntaxWarnings. These originate in packaged files rather than this overlay.

## Verification and remaining work

- Passed bash -n on the ISO assembler and label helper.
- Passed bash mseries/test-iso-label.sh.
- Passed python3 mseries/test-image-wiring.py.
- Passed isolated systemd-sysusers --root check with the image's updated
  sysusers file.
- Passed git diff --check.
- Local just mkosi summary could not run: the recipe writes to
  /home/admin/.cache/mkosi-workspace, outside the writable workspace. The
  previous arm64 CI config-parse run succeeded before these source cleanups.
- Run 38400807824 was still building when this review was written. It predates
  the sysusers/tmpfiles cleanups, so a later full image build is needed to
  confirm those log messages are gone. Hardware boot and installer checks are
  still required before calling the image qualified.
