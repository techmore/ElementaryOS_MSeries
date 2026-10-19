# Vendored: netmojo-systems/omdrop-plugin

- Upstream: https://github.com/netmojo-systems/omdrop-plugin (MIT, see LICENSE)
- Pinned revision: c6529bebaf7dff3ac2fca55d27eff8005bd94637 (2026-10-18)
- Taken unmodified: `bin/` (the `omdrop` command, receiver `airdrop-serve.py`, identity, lifecycle, contacts), `share/`, `docs/`, `skills/`, README, CONTRIBUTING, manifest.
- Not taken: `core/` (Rust omdrop-core, optional), the Omarchy QML panel (`Panel.qml`, `Radar.qml`, `OmdropIcon.qml`), `preview.png`.
- Our layer on top: `mseries/quick-settings/AirDropPanel.vala` (native Quick Settings section), `mseries/omdrop-stub/` (stub radio backend for tests), `mseries/install-omdrop.sh`.
- The radio backend is separately vendored as userspace-only `mseries/omdrop-awdl` (GPL-2.0-only). Its explicit `install-omdrop-radio.sh install` installs helpers and policy, does not enable AWDL, and does not replace a kernel module. See that directory’s PROVENANCE.md and TEST-PLAN.md.
- AirDrop is a trademark of Apple Inc.; this project is not affiliated with Apple.

- Local test adaptations: optional-core tests explicitly skip without the deliberately omitted core tree. The receiver-limit fixture uses add_file_from_memory so libarchive-c 5.1 preserves requested archive names; receiver production code is unchanged.
