# fairydust + USB4/Thunderbolt (Apple M1 Pro, j314s)

Makes USB4 docks/hubs enumerate on Apple Silicon by porting Sven Peter's
USB4/Thunderbolt host support (Asahi branch `b4/apple-soc-tbt`, posted to LKML
2026-08-30) onto the `fairydust` kernel this repo already builds.

Status on `MacBookPro18,3` / `apple,j314s` (verified 2026-10-12):

| Item | Result |
| --- | --- |
| Dell dock hub tree enumerates (USB2 side) | **works** — mouse, headset, dock hubs |
| USB3 tunnel / dock Ethernet | **blocked on m1n1** — driver needs bootloader-supplied tunables (see "m1n1 requirement") |
| Dock HDMI/DP video | **not supported** — DisplayPort tunnelling is not implemented upstream yet |
| Suspend with a USB4 link up | **unsafe** — upstream notes S2RAM SError panic; do not suspend while docked |

## Why this was needed (root cause)

A USB4-capable hub/dock negotiates **USB4** with the Apple CD321x Type-C
controller, and Linux cannot steer that choice (the controller picks the mode).
On stock fairydust the ATC PHY has no USB4 pipehandler and `CONFIG_USB4` is off,
so the PHY logs `ATCPHY_PIPEHANDLER_STATE_USB4 not implemented; falling back to
USB2` and routes **nothing** — the xHCI root ports sit in `RxDetect`, the hub
never enumerates, and downstream devices get no power (mouse LED stays off).

How it was confirmed (read-only, on the running machine):

* `/sys/class/typec/portN-partner/identity/*` returned garbage (the PD identity
  is not read for USB4 partners).
* CD321x registers over `/dev/i2c-0` (addr `0x3f` = typec port2, `0x3b`, `0x38`):
  * `0x5f` DATA_STATUS = `0x16800011` → bit23 `CD321X_DATA_STATUS_USB4_CONNECTION`.
  * `0x24` USB4_STATUS EUDO = `0x2667e000` → `EUDO_USB_MODE` (bits 30:28) = **2 = USB4**.
* `debugfs/usb/xhci/*/ports/*/portsc` = `Link=RxDetect` on both root ports.

## What the patch contains

`0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch` (53 files, against
fairydust `ce9f2eba72c061a50b2d790450e90af3439d8c24`):

* `drivers/thunderbolt/*`, `include/linux/thunderbolt.h`, `drivers/net/thunderbolt/*`:
  imported wholesale from the series base (Linux 7.3-rc1 Thunderbolt core + the
  Apple driver `apple.c`). fairydust is 7.1-based and lacks the 7.2/7.3 NHI
  refactor (`tb_nhi_ops`, platform NHI) that `apple.c` needs; cherry-picking
  dozens of commits was avoided. `thunderbolt.h` keeps `<linux/mod_devicetable.h>`
  (7.1 layout; 7.3's `device-id/tb.h` does not exist here).
* `drivers/reset/reset-apple-cio.c` (+Kconfig/Makefile): CIO reset controller.
* `drivers/phy/apple/atc.c`: real USB4 pipehandler (`atcphy_configure_pipehandler_usb4`,
  `atcphy_pipehandler_set_mux`); fairydust's per-SoC BIST (t8103/t8122) is kept.
* `drivers/usb/typec/*`, `tipd/*`: USB4 mode + altmode publishing for CD321x
  (struct fields added to fairydust's `tps6598x.h`; fairydust keeps `connector_fwnode`
  DRM hotplug).
* Device trees: `t600x-dieX.dtsi`, `t602x-dieX.dtsi`, `t600x-j314-j316.dtsi`
  (ACIO/NHI/mailbox/DART nodes, `typec*`↔`usb4_*_acio` graph endpoints, dwc3
  `endpoint@1` to the USB4 tunnel, `usb4-N-acio/nhi` aliases). Other SoC/board
  files (M1/M2, Studio/Ultra) are intentionally untouched.

> **Gotcha that cost a boot:** `t600x-j314-j316.dtsi` is shared with the M2 Pro/Max
> j414/j416 boards, so `t602x-dieX.dtsi` must define the same `usb4_N_*` labels.
> Without the j314-j316 graph endpoints the driver logs
> `thunderbolt-apple-acio …: error -ENODEV: unable to find Type-C graph endpoint`
> and the USB4 host router never registers (USB3 tunnel/Ethernet absent).

## Build and install

Same host-side chroot flow as the base kit (see `../README.md`).

```bash
sudo ./build-pkg.sh          # builds only; ~1-2 h on M1 Pro; progress: ./progress.sh
sudo ./install-stage1.sh     # install pkg beside existing kernels + initramfs (no /boot image change)
sudo ./install-stage2.sh     # update m1n1 boot.bin with the new DTBs + add a *TEST* GRUB entry
```

After a rebuild that only changes device trees, use `sudo ./deploy-dtbs.sh`
(copies DTBs and re-runs `update-m1n1`; backs up `/boot/m1n1` first).

Set `USB4_WORKDIR` to change where backups/logs go (default `~/fairydust-usb4`).

Checks after booting the TEST entry:

```bash
uname -r                                  # ...fairydust-usb4-ARCH
lsmod | grep thunderbolt                  # thunderbolt, thunderbolt_apple
journalctl -b -k | grep -i "graph endpoint"   # must be EMPTY
ls /sys/bus/thunderbolt/devices           # domain0 and the dock's router
lsusb -t                                  # SuperSpeed (10000M) bus should now populate
```

## Rollback

* Pick any older entry in GRUB (the TEST entry is not the default).
* `boot.bin` is shared by **all** kernels (m1n1 stage 2). Restore the saved copy:
  `sudo cp <backup>/m1n1/boot.bin /boot/m1n1/boot.bin`.
  `update-m1n1` only keeps one `.old`, so the scripts take their own backups.

## Do not

* Unbind/rebind `phy-apple-atc`, `dwc3-apple`, or `modprobe -r typec_thunderbolt` on a
  running system: unbinding `dwc3-apple` oopses (`mutex_lock` NULL in `dwc3_apple_remove`)
  and takes the display subsystem with it.
* Hot-plug a USB4 dock during boot or suspend with it attached.

## m1n1 requirement (why Ethernet still needs the bootloader)

With the DT graph endpoints in place the ACIO driver gets further but fails:

    thunderbolt-apple-acio 701ac0000.cio: error -ENOENT: unable to load rc tunable

`drivers/thunderbolt/apple.c` requires `apple,tunable-rc` (ACIO) and `apple,tunable-nhi`
(NHI) plus `apple,thunderbolt-drom` in the device tree. These are *generated by m1n1* from
Apple's ADT (`usb4_rc_tunables`, `usb4_nhi_tunables`, `dt_copy_usb4_drom` in m1n1
`src/kboot.c`). The distro m1n1 here is **v1.6.1**, which predates that code, so the
properties never appear and no USB4 router registers; only the USB2 side works.

`build-m1n1.sh` builds current `AsahiLinux/m1n1` (needs the `aarch64-unknown-none-softfloat`
rust target; the chroot needs working DNS, see `../README.md`). Use it via
`/etc/default/update-m1n1` in the Arch root (`M1N1=/path/to/m1n1.bin`). **This replaces the
bootloader stage that runs before GRUB** - a bad m1n1 cannot be recovered from GRUB; keep a
`boot.bin` backup and a way to mount the ESP from another OS.

## pacman hook trap (cost us a regression)

`95-m1n1-install.hook` runs `update-m1n1` on any kernel package install, and the default
`DTBS` is the newest `/lib/modules/*-ARCH` by version sort, i.e. the **stock** kernel's DTBs.
Re-running `install-stage1.sh` (`pacman -U`) therefore silently replaced `boot.bin` with one
that has no USB4 nodes. Pin it in the Arch root's `/etc/default/update-m1n1`:

    DTBS=/usr/lib/modules/7.1.13-1-2-fairydust-usb4-ARCH/dtbs/*.dtb

and run `deploy-dtbs.sh` after any package operation. Check with
`grep -ac usb4-0-acio /boot/m1n1/boot.bin` (must be > 0).

## Login screen stalls ~2 min (gala race) - `lightdm-wait-for-drm.conf`

The greeter's `gala` can start before the Apple DRM device exists (appledrm initialises ~9.8 s
into boot, lightdm starts ~8.7 s) and aborts (SIGABRT). The `lightdm` user's systemd instance
survives with `xdg-desktop-portal-gtk` in a failed state, so the replacement greeter waits out
D-Bus' 120 s activation timeout (LightDM log: `Greeter connected` at +119.7 s instead of ~+1 s).
The drop-in makes `lightdm.service` wait (max 30 s) for `/sys/class/drm/card*-eDP-*`:

    sudo install -D -m0644 lightdm-wait-for-drm.conf /etc/systemd/system/lightdm.service.d/wait-for-drm.conf
    sudo systemctl daemon-reload
