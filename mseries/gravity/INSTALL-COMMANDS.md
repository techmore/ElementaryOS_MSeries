# M4 Mac mini install: the commands, in order

Written 2026-10-28. None of this has been run on the mini yet. Background and caveats: [GRAVITY-M4-BRINGUP.md](GRAVITY-M4-BRINGUP.md).

## Before you start

- A full Time Machine backup. Stage 1 shrinks your macOS partition.
- A wired USB keyboard and mouse on direct ports (U-Boot and GRUB cannot use Bluetooth), the monitor on the **HDMI** port
  (USB-C display output on the M4 is not supported yet), power connected, Ethernet if you have it.

## 1. Read the Gravity installer first (macOS Terminal)

It runs as root.

```bash
curl -fsSL https://install.gravitylinux.org | less
```

## 2. Run it (macOS Terminal)

It asks for your password and which partition to resize. Follow its Recovery instructions.

```bash
curl -fsSL https://install.gravitylinux.org | sh
```

## 3. First boot into Gravity (Fedora): get online

```bash
sudo nmcli --ask device wifi connect "YOUR_SSID"
```

## 4. Bring-up: git, gh, key-only SSH, Claude Code, this repo

```bash
curl -fsSL https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/prep/m4-mini-aurora-installer/mseries/gravity/gravity-bringup.sh -o gravity-bringup.sh
```

```bash
bash gravity-bringup.sh --ssh-key "$(cat ~/.ssh/id_ed25519.pub)"
```

No SSH key on the mini yet? Paste your other machine's public key inside the quotes. After this, `cd ~/ElementaryOS_MSeries && claude`
continues the work on the machine.

## 5. Install elementary

`--no-encrypt` is required: the Gravity image is unencrypted. Use the branch name in `--ref` until PR 692 is merged, then drop it.

```bash
curl -fsSL https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/prep/m4-mini-aurora-installer/bin/elementary-mac-setup | sudo ELEMENTARY_ACCEPT_M4=1 bash -s -- --ref prep/m4-mini-aurora-installer --no-encrypt --enable-ssh --ssh-key "$(cat ~/.ssh/id_ed25519.pub)"
```

It asks for a username, hostname and password, builds elementary, and reboots. Choose **elementary OS (M-series)** in the boot menu if
it is not already the default. Fedora stays in the menu as the rescue system.

## If something fails

- Log: `/var/log/elementary-mac-setup.log` (and `-grow.log`). Resume with `elementary-mac-setup --resume`.
- Status: `elementary-mac-setup --status`. Undo the elementary build: `sudo ELEMENTARY_HOST=fedora bash transform/elementary-grow.sh --rollback`.
- Run `claude` in `~/ElementaryOS_MSeries` and paste the error.

## Known limits

- The Fedora-host lane and the M4 kernel (Gravity's, borrowed by elementary) are untested on hardware.
- USB-C display output and USB4/Thunderbolt on the M4 are not supported by either kernel tree: use HDMI.
- Rust Pantheon apps come from `techmore/mseries-sdk-apps` and have not been built for this host.
