# M4 Mac mini (J773g / T8132) install: experimental

Status 2026-10-28. Nothing here has been run on an M4 by this project.

## What upstream says

- Aurora's support data lists the M4 Mac mini (`j773g`) and M4 Pro (`j773s`) as booting, with all CPU
  cores, GPU/Vulkan, Wi-Fi, Bluetooth, HDMI, storage and fan control confirmed on 2026-10-21. USB-C/Thunderbolt,
  audio, suspend and camera are not recorded.
- Kernel work: `aurora-silicon/linux` branches `m4/pr1-basic-bringup`, `m4/pr2-gpu-dcp`,
  `m4/j713-t8132-integ-20261023`, `aurora-wip`. `omacom/linux-aurora` has no M4 branches.
- Stock Asahi Alarm does not boot M4. The Aurora native installer's signed catalog
  (`aurora-silicon/aurora-distributions`) does not yet list `j773*`, so it cannot install onto this Mac.

- Mainline: Phoronix (2026-10-02) reports pull requests for Linux 7.4 adding initial M4 device trees, including
  the Mac mini (M4, 2024), covering only CPU cores, interrupts, power states, watchdog, serial, pin control, I2C
  and the framebuffer. No GPU. The article does not confirm the pull was merged, and it does not name J773.
  A mainline or Asahi kernel is therefore not a substitute for the Aurora kernel here.

## Consequence

The README's step 1 (Asahi Alarm bootstrap) cannot work on an M4 mini. Until Aurora's catalog lists J773,
the only route is to get Aurora ALARM (`aurora-silicon/alarm-aurora`, kernel package `linux-aurora`) onto the
Mac by hand using Aurora's m1n1/U-Boot/Aura boot chain, then run `elementary-mac-setup` from that Linux.

## Using the installer on an M4

```bash
ELEMENTARY_ACCEPT_M4=1 bash elementary-mac-setup --enable-ssh --ssh-key ~/.ssh/id_ed25519.pub
```

- Without `ELEMENTARY_ACCEPT_M4=1` the script refuses on M4-family machines.
- The pacman hook now also watches `linux-aurora*`.
- `--enable-ssh` is off by default. It writes key-only sshd config, stages your public key, and a first-boot
  unit installs `openssh-server` (needs network) and the key. Password and root login stay disabled.
- Remote desktop is not wired: Pantheon/Gala has no verified RDP or VNC server yet.

## Before relying on it

1. Read `mseries/KERNEL-FLOW.md`: elementary borrows the Arch-side kernel, so the Aurora kernel must boot first.
2. Back up macOS. Keep the Aurora/Arch root as the rescue system.
3. Report results upstream in aurora-silicon/linux discussion 130.
