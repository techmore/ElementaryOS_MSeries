# Kernel source evaluation — Ubuntu Asahi PPA (PROPOSED, not yet wired)

Evaluated 2026-10-12 from Launchpad + the UbuntuAsahi kernel-packaging
wiki. Nothing below is installed or enabled in the build yet; the recipe at
the end is gated on the verification steps.

## What exists

- PPA: `ppa:ubuntu-asahi/ubuntu-asahi`
  (`https://ppa.launchpadcontent.net/ubuntu-asahi/ubuntu-asahi/ubuntu`),
  the community port of Asahi Linux to Ubuntu (https://ubuntuasahi.org/).
- Kernel packages follow Ubuntu's kernel-team layout, rebased per release
  onto the matching Ubuntu base with the Asahi tree on top (process
  documented at
  https://github.com/UbuntuAsahi/ubuntu-asahi/wiki/Kernel-packaging):
  - `linux-asahi-arm` — meta package (like `linux-generic`), arm64-only.
    Latest observed: `7.0.0.1002.2` (2026-06-29), i.e. tracking the same
    7.0 base as resolute's generic kernel.
  - `linux-image-<ver>-asahi-arm`, `linux-modules-…`, `linux-headers-…`,
    `linux-main-signed-asahi-arm` — the signed image stack.
- History shows steady tracking (6.13 → 6.16 → 6.17 → 7.0 across 2025–2026),
  so this is a maintained source, not a one-off build.

## Why it fits

- Same packaging conventions as Ubuntu kernels → installs, `/boot` layout,
  and initramfs handling behave like the generic kernel mkosi already
  supports. No custom install hooks expected.
- Version `7.0.0-1002…` compares HIGHER than generic `7.0.0-38…`, so with
  both installed, kernel-selection logic (newest wins) should pick Asahi
  without removal surgery — to be confirmed at first build.
- Narrow scope: only the kernel changes; userspace (Pantheon, PipeWire,
  NetworkManager) stays stock Ubuntu + our `apple-silicon` overlay.

## Risks / open questions

1. **Series coverage**: PPA must publish a `resolute` suite. The pool
   shows 7.0 builds but suite membership needs `apt update` on an arm64
   builder to confirm (verification step 1).
2. **Signing/Secure Boot**: elementary sets `SecureBoot=no`; Asahi kernels
   are Launchpad-signed (`linux-main-signed-asahi-arm`), not Canonical-
   signed. Fine for Apple hardware (no SB enforcement via m1n1/u-boot),
   but record the assumption.
3. **UKI + sysext flow**: sysupdate builds a UKI from the installed
   kernel; confirm mkosi picks the asahi kernel (check `ls
   usr/lib/modules` in the sysupdate tree at first build).
4. **Trust**: a community PPA becomes a privileged dependency. Mitigate
   with apt pinning scoped to kernel packages only (recipe below), so a
   compromised/stale PPA cannot replace userspace.

## Wiring recipe (do NOT apply before verification)

1. Vendor the keyring: fetch the PPA signing key, verify its fingerprint
   against the Launchpad-published key, `gpg --dearmor` to
   `repos/common-files/etc/apt/keyrings/ubuntu-asahi.gpg`.
2. New `repos/common-files/etc/apt/sources.list.d/ubuntu-asahi.sources`:
   ```ini
   Types: deb
   URIs: https://ppa.launchpadcontent.net/ubuntu-asahi/ubuntu-asahi/ubuntu
   Suites: resolute
   Components: main
   Architectures: arm64
   Signed-By: /etc/apt/keyrings/ubuntu-asahi.gpg
   ```
   (`Architectures: arm64` keeps x86-64 builds untouched.)
3. New `repos/common-files/etc/apt/preferences.d/pin-asahi-kernel`
   allowing only the kernel stack from that origin (origin string to
   confirm with `apt-cache policy`, expected `o=LP-PPA-ubuntu-asahi-ubuntu-asahi`):
   ```ini
   Explanation: M-series: take only the Asahi kernel from the Ubuntu Asahi PPA.
   Package: linux-*asahi* linux-*asahi-arm*
   Pin: release o=LP-PPA-ubuntu-asahi-ubuntu-asahi
   Pin-Priority: 990
   ```
4. Add `linux-asahi-arm` to the `apple-silicon` image `Packages=` (arm64-
   gated by the image's `[Match]`, so no other image changes).
5. Rebuild arm64, then verify: `usr/lib/modules` contains the asahi
   kernel, UKI/initrd built from it, generic kernel either absent or
   superseded.

## Verification steps (in order)

1. On an arm64 Ubuntu container: add the `.sources` entry, `apt update`,
   confirm no errors and `apt-cache policy linux-asahi-arm` shows the PPA.
2. `apt-cache policy` to copy the exact origin string into the pin file.
3. Install `linux-asahi-arm` in a throwaway container, confirm
   `dpkg -l 'linux-image*'` shows asahi superseding generic.
4. Only then apply the recipe and run the arm64 image build.
