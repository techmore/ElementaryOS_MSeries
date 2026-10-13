# Upstream pins (reproducibility record)

First M-series commit is based on:

- `elementary/os` `main` @ `5215b29a2eb2d52bb946b2e8e0b92f75c32e808a`
  ("tmpfiles.d/login.conf: Fix /var/lib/lightdm ownership (#911)"),
  merged up to `7024fd04646a6a8565bf6805989b59fd72de928c` ("Add systemd-coredump (#915)", 2026-10-12)
  https://github.com/elementary/os
- `omacom/omarchy-mac` `quattro` @ `ba546a61f881c1fe9d79d75ec050eab048b8cb63`
  ("Hand off Steam launcher ownership to FEX package (#511)", 2026-09-25)
  https://github.com/omacom/omarchy-mac

At the original scaffold snapshot, additive `mseries/` documentation and the
`mkosi.images/apple-silicon/` layer sat on top. The port also touched five
upstream paths: the arm64 dependency, liveiso `ExtraTrees`, a new sysupdate
arm64 config, the README pointer, and the daily workflow trigger. No other
upstream files were modified at that snapshot.

The current elementary upstream enhancement from
`7024fd04646a6a8565bf6805989b59fd72de928c` adds `systemd-coredump` to the base
image package list. That one-line change is now carried by this branch.

The fetched `elementary/os` `main` reference on 2026-10-13 was
`7024fd04646a6a8565bf6805989b59fd72de928c`. This is the comparison point for
the OS 9 source audit; recheck the upstream branch before the next port.

## Current Apple hardware reference (audit only)

The maintained Omarchy Mac add-on packages were checked on 2026-10-13 at
omacom/omarchy-mac-pkgs main commit
222f7a8599bbdd287ac6a95362cd51c5b024baae. This is a source reference,
not a dependency of the elementary build. Omarchy-specific packages target
Arch Linux and follow their own package and test contract; elementary ports
must be translated to Ubuntu/mkosi and Pantheon/Gala.

The historical omacom/omarchy-mac quattro pin above records the source
used for the original scaffold only. Package changes now belong in
omacom/omarchy-mac-pkgs; the old branch is transitional.
