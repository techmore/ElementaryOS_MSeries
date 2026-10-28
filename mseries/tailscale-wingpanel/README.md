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

The icon is dimmed when Tailscale is off.

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
bash mseries/install-tailscale-wingpanel.sh     # top panel (asks for sudo, no restart)
bash mseries/install-dock-drawers.sh            # taskbar, then: systemctl --user restart pantheon-dock
```

## Check

- `meson test -C <build>` parses a fixture of `tailscale status --json`.
- `<build>/tailscale-panel-probe` opens the menu in a plain window with live data.
