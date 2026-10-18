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

## Factory gesture daemon

Touchegg 2.0.18 is pinned to `fc30d316e163f4504043353d6610e670ce5c6439`
(tag resolved through GitHub on 2026-10-14). Both the factory build and the
manual installer fetch this exact commit. Source: JoseExposito/touchegg.
License: GPL-3.0-or-later. The factory payload retains COPYING, COPYRIGHT,
the build recipe and a pinned source-archive URL under
`/usr/share/doc/mseries-touchegg`. Build and gesture qualification are pending.

## Factory VA-API bridge candidate

`omacom/libva-v4l2_request` revision
`c653eaa6234a02b5f31f77a8aa23f7a744650e87`, source archive SHA256
`0d8368fe7d1fea304acdc4903e2442486c880daffc37819fef687c8cecf34cf3`.
Factory and manual install use the same source. License: GPL-3.0.
The factory retains COPYING, README, support contract/matrix, source provenance
and the build recipe. Upstream reports no supported matrix rows at this pin;
M1/T8103 evidence is not M1 Pro qualification. Enabled codec compilation is
not hardware codec support. Kernel AVD, firmware and client validation are open.

## Factory sound and keyboard indicators

`panel-factory-pins.json` records package/source requirements for all four
factory panel plugins. Sound 8.0.3: `elementary/wingpanel-indicator-sound`
`8b7991c9156ac8127d27559506baea8e6fb72e5b`; keyboard 2.4.2:
`elementary/panel-keyboard` `2d086e0177d7aa9a9e6aa4eb11fa7fb77c628c76`.
Installed package copyright metadata identifies GPL-3.0-or-later; the build
requires and retains the actual upstream license, local patch and recipe.
Each built plugin records its source and SHA256. Both final consumers compare
package versions and retained binary hashes before image publication.
These checks do not establish that the plugins load or render on hardware.

## Optimization repository (2026-10-15)

`techmore/ElementaryOS_MSeries_Optimization` at `7d65b03` (powerlab sampler, tuning drop-in, docs). Not consumed by the image yet; see `OPTIMIZATION.md`.

## Aurora kernel port (2026-10-17)

`mseries/aurora/release.json` is the machine-readable pin ledger for
`omacom/linux-aurora` release `aurora-2026.10.17.20`, kernel source
`c46d7dcdb8712ea9aeb0ce47b439ffae76371e55`. It pins the unchanged public
kernel package, original recipe/config and corresponding source archive,
plus m1n1 `omacom/m1n1@d05ba17dfb771871d608225be42968bbb1e75a18` and its source.
Checksums are verified before extraction; the Debian payload retains kernel
COPYING/LICENSES and upstream recipe, and travels with corresponding source.
This opt-in port does not replace the factory kernel profile or qualify a boot.
