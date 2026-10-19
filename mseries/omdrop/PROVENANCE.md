# Vendored: netmojo-systems/omdrop-plugin

- Upstream: https://github.com/netmojo-systems/omdrop-plugin (MIT, see LICENSE)
- Pinned revision: c6529bebaf7dff3ac2fca55d27eff8005bd94637 (2026-10-18)
- Taken unmodified: `bin/` (the `omdrop` command, receiver `airdrop-serve.py`, identity, lifecycle, contacts), `share/`, `docs/`, `tests/`, `skills/`, README, CONTRIBUTING, manifest.
- Not taken: `core/` (Rust omdrop-core, optional), the Omarchy QML panel (`Panel.qml`, `Radar.qml`, `OmdropIcon.qml`), `preview.png`.
- Our layer on top: `mseries/quick-settings/AirDropPanel.vala` (native Quick Settings section), `mseries/omdrop-stub/` (stub radio backend for tests), `mseries/install-omdrop.sh`.
- Radio backend (the Wi-Fi AWDL driver, `omdrop-awdl`) is NOT part of this repo and is NOT installed by us: it replaces the running brcmfmac kernel driver, which is the kernel owner's decision.
- AirDrop is a trademark of Apple Inc.; this project is not affiliated with Apple.
