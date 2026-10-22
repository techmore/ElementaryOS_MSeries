# Orchard for Incus (native) has moved

The native Orchard for Incus is now the **Incus** and **Podman** sections of
[Orchard](../orchard/README.md) (`mseries/orchard/`), merged on 2026-10-21 with Machine Lab into
one app: Machine Lab's sidebar, pages and style; Orchard's name, icon, clients, windows and tests.

- Sources: `mseries/orchard/src/` (`IncusClient.vala`, `Instance.vala`, `Dashboard.vala`,
  `ResourceBrowser.vala`, `CommandPalette.vala`, `LogViewer.vala`, `MountsWindow.vala`,
  `SystemWindow.vala`, `ImagePullWindow.vala`, `DeviceEditor.vala`, `ModelService.vala`,
  `ModelBridge.vala`, `SandboxesWindow.vala`, `PodmanClient.vala`, `PodmanPage.vala`,
  `PodmanDetails.vala`, `Indicator.vala`); the instance page that replaced `InstanceDetails.vala`
  and `MainWindow.vala` is `incus-page.vala`.
- Tests: `mseries/orchard/tests/` (fake Incus socket, fake podman, `meson test`).
- Background: `mseries/orchard/docs/ORCHARD-FOR-INCUS-README.md`, `docs/UPSTREAM-PARITY.md`,
  `mseries/orchard/NOTICE.md` (attribution), `mseries/orchard/audit/`.
- Install: `bash mseries/install-orchard.sh` (removes the `com.github.techmore.orchard-incus` entry).

Preferences (`~/.config/orchard-incus/preferences.ini`) and metric history
(`~/.local/state/orchard-incus/metrics`) are read by Orchard unchanged. The Python
implementation in `mseries/orchard-incus/` is separate and unaffected.
History: `git log --follow mseries/orchard/src/IncusClient.vala`.
