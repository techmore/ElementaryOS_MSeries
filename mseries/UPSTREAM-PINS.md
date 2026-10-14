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

## Wingpanel network speed readout

The Apple Silicon image builds `elementary/panel-network` at
`8685ec8e55a45e48da0c12931a353cd440d11664`, matching
`io.elementary.panel.network` 8.0.1.x. The local patches add the live throughput
row, guard null VPN devices, add an opt-in menu-bar rate display, collapse other
Wi-Fi networks while connected, and provide Apps/Hosts/DNS usage views. A local
user service supplies usage totals and DNS-derived hostnames. The build fails
closed if the image's network indicator package moves beyond 8.0.1.x.

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

## Experimental Asahi boot-package inputs (2026-10-13)

Ubuntu Asahi resolute Launchpad PPA (`LP-PPA-ubuntu-asahi-ubuntu-asahi`)
InRelease verified under key fingerprint
`F5BFDB467341BF02DBC113AB39CC27E17A201624`. The ARM64 Packages.gz SHA-256
was `ce75a0e9d6754659842d4d818ad057869780a9900783ab505f6e891c86ffda06` and
matched the signed Release. The experimental CI fetch script additionally
pins and checks these exact artifacts:

- m1n1 `1.5.2-2ubuntu0.1~asahi1`, SHA-256
  `6c78ead41b46b7cfca145e01743ed4874e58e8b37f0127d46d3b7c186cdb2088`.
- u-boot-asahi `2025.10-2-1`, SHA-256
  `e0cc3d96dc4d57fb491979280254bc095204588c66984bc46948b35529690b51`.

The fetched m1n1 binary contains the USB4 properties `apple,tunable-rc`,
`apple,tunable-nhi`, and `apple,thunderbolt-drom`. This confirms required
strings exist; it does not verify that the PPA m1n1+U-Boot+DTB boot chain works
on the Mac. Do not describe this package set as a hardware boot result.

## Installer reference (studied 2026-10-14, not imported)

`omacom/omarchy-mac-installer` (MIT), main at the 2026-10-14 `Publish app releases only for X.Y.Z versions` merge. Read-only study; see `MAC-INSTALLER-PLAN.md`. Record the exact commit when the first import happens.
