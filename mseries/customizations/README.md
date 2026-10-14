# Customization snapshot (2026-10-14)

Local deltas that previously existed only in working trees under `~/Documents` and
`~/fairydust-usb4`, saved before the partition rebuild. Apply each against the SHA noted.

| File | Upstream / base | What it is |
| --- | --- | --- |
| `gala-working-tree-vs-f079143.diff` | elementary/gala `f0791434` (`gala.PINNED_SHA`) | Screen corners + LayoutManager change + `libmutter.vapi`/`meson.build` tweaks. Superset of `../patches/gala-screen-corners.patch` |
| `gala-{Layout,Window}Manager.vala.installed` | same | The full files as built and installed |
| `wingpanel-PanelWindow.vala.installed` | elementary/wingpanel | Patched `PanelWindow.vala` as installed (see `../upstream/wingpanel-on-realize-crash.md`) |
| `panel-power-battery-eta.diff` | elementary/panel-power `panel-power.PINNED_SHA`, branch `mseries-battery-eta` | Battery ETA in the power indicator (Indicator.vala, DisplayWidget.vala) |
| `coreglass-local-ssh.diff` | joshuaswarren/coreglass `main` | `remote.ssh()` runs commands via `bash -c` when host is `local` |

Network indicator (throughput graph, usage tabs incl. DNS, quiet Wi-Fi list) is already saved as
`../netspeed/panel-network.patch` (pinned in `../netspeed/PINNED_SHA`) and verified identical to the
working tree; `netusage` source is in `../netspeed/netusage/`.
Docked-lid, power policy, brightness, clockright, local-ai (troubleshooter, crash-watch, agent)
live in their own directories under `mseries/`.
