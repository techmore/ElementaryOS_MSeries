# Vendored: netmojo-systems/omdrop-awdl (userspace only)

- Upstream: https://github.com/netmojo-systems/omdrop-awdl, pinned at 9e9a7acc49549cd0e118890cdae4ba8dd0680639 (2026-10-18), package version 0.10.0.
- License: GPL-2.0-only (see LICENSE; upstream states the patches are kernel-derived and the package is GPL-2.0-only). Attribution and the licence travel with the files.
- Taken unmodified: `userspace/` (awdl-up, omdrop-discoverable, brcm_iovar.py, send-to-peer, helpers, radio hooks), the three packaging files we use (`awdl0.service`, `99-awdl-unmanaged.conf`, `org.omarchy.omdrop.policy`), README, docs.
- NOT taken, on purpose: `kernel/` (vendored Asahi sources), `patches/` and `dkms.conf.in` (the kernel side is Aurora's: `aurora-silicon/linux`, `integration/aurora` already carries the AWDL vendor command and netdev code, so no kernel module is replaced), `packaging/brcmfmac-awdl.conf` (a modprobe debug mask; the data-path gate does not need it and we do not change driver options), `10-wld0.link`.
- Our layer: `mseries/install-omdrop-radio.sh` (preflight / install / uninstall), `mseries/omdrop-awdl/RADIO-VALIDATION.md` (the evidence), `mseries/omdrop-awdl/TEST-PLAN.md`.

- Local test adaptation: DKMS/Arch package tests explicitly skip when their deliberately excluded packaging is absent; userspace tests are unchanged. Our installer has separate sandboxed regression tests.
