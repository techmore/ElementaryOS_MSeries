# Tailscale menu

A Tailscale icon in the top panel (and in the Work Mode taskbar) so you can find
your devices and SSH to them without a terminal.

Click it to see:

- **Tailscale** switch: connected or not, and your tailnet name.
- **This device**: name and Tailscale IP, with a copy button.
- **Devices**: every machine on the tailnet, online first. Each row shows name,
  IP and OS. Click the row (or the copy button) to copy the IP; the terminal
  button copies `ssh <name>` (the MagicDNS name, e.g. `ssh sdolbec-ser8`).
  The row briefly says "Copied …".
- **Admin Console…** opens login.tailscale.com.

The icon is the Tailscale logo when connected and all-grey dots when not, the
same on/off look as Tailscale's own tray icon.

## Icon source

`mseries-tailscale-symbolic.svg` and `mseries-tailscale-offline-symbolic.svg` redraw
the Tailscale logo from the dot layout in Tailscale's own tray code,
[`client/systray/logo.go`](https://github.com/tailscale/tailscale/blob/v1.104.4/client/systray/logo.go)
(BSD-3-Clause, © Tailscale Inc & contributors): a 3×3 grid, dot radius r, centres
at (1 + 3i)·r, lit dots for "connected", all grey for "disconnected". Here r = 2 on a
16 px canvas, with grey dots at 40%. They are monochrome so the panel can recolour
them. The Tailscale name and logo are Tailscale Inc. trademarks. We use them only
to label Tailscale's own status, not to suggest Tailscale endorses this project.

## How it works

`TailscalePanel.vala` runs `tailscale status --json` (no root) when the menu
opens, every 5 s while it is open and every 60 s otherwise. The switch runs
`tailscale up` / `tailscale down`. Those need the operator setting; without it
the menu shows the one-time command with a copy button:

```sh
sudo tailscale set --operator=$USER
```

`Indicator.vala` is the Wingpanel plugin (`libmseries-tailscale.so`).
`../dock-taskbar/TaskbarTailscale.vala` puts the same panel in the taskbar
status area after AirDrop (`prepare-source.sh` wires it in).

We chose a native indicator over `tailscale systray`: the panel only partly
supports tray icons, and the native menu matches the other panel menus.

## Install

```sh
bash mseries/install-tailscale-wingpanel.sh     # top panel (sudo for the plugin; icons go in ~/.local/share)
bash mseries/install-dock-drawers.sh            # taskbar, then: systemctl --user restart pantheon-dock
```

## Check

- `meson test -C <build>` parses a fixture of `tailscale status --json`.
- `<build>/tailscale-panel-probe` opens the menu in a plain window with live data.
