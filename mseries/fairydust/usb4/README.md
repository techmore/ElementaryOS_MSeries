# fairydust + USB4/Thunderbolt (Apple M1 Pro, j314s)

Makes USB4 docks/hubs enumerate on Apple Silicon by porting Sven Peter's
USB4/Thunderbolt host support (Asahi branch `b4/apple-soc-tbt`, posted to LKML
2026-08-30) onto the `fairydust` kernel this repo already builds.

Status on `MacBookPro18,3` / `apple,j314s` (verified 2026-10-12):

| Item | Result |
| --- | --- |
| Dell dock hub tree enumerates (USB2 side) | **works** — mouse, headset, dock hubs |
| USB3 tunnel / dock Ethernet | **works** (verified 2026-10-12) - Realtek r8152 on the 10 Gb/s USB3 bus, 1 Gb/s full duplex, DHCP, 0% loss. Needs the new m1n1 + quirk fix |
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

## USB3 tunnel: bandwidth-allocation timeout (the Ethernet blocker)

After the new m1n1 supplied the ACIO/NHI tunables, the USB4 router registered, the dock (Dell
WD22TB4, 20 Gb/s x2) was discovered and the USB2 side worked, but the USB3 tunnel failed:

    0:4 <-> 1:16 (USB3): activating
    0:4 <-> 1:16 (USB3): allocating initial bandwidth 9000/9000 Mb/s
    ...~1.4 s...
    1:16: USB3 tunnel activation failed, aborting

(visible with `echo 'module thunderbolt +p' > /sys/kernel/debug/dynamic_debug/control` and one
dock replug). The PCIe tunnel right after it logs `Writing hop`; the USB3 one never gets that far:
it dies in `tb_usb3_pre_activate()` -> `usb4_usb3_port_allocate_bandwidth()`.

Cause: `quirks.c` disables USB3 bandwidth allocation for Apple host routers with
`{ 0x05ac, 0x2000, ... }`, but the M1 Pro/Max (T6000) host router identifies as
**`05ac:2001`** (log: `USB4 Switch: 5ac:2001`; adapter reg0 `0x200105ac`). The quirk never
matched, the allocation handshake (unimplemented in Apple's router) timed out and the tunnel was
torn down. Fix: match any Apple router (`{ 0x05ac, 0x0000, ... }`). Only the host router consults
the flag, so downstream devices are unaffected. Only `thunderbolt.ko` changes; exported symbol
CRCs are identical, so `thunderbolt_apple.ko` is untouched.

Debugging aids that worked: `/sys/kernel/debug/thunderbolt/<router>/port<N>/{regs,path}`
(read-only adapter registers; type `0x200101` = USB3 down, `0x200102` = USB3 up).

Still open after this: the dock's DP tunnel (`could not allocate DP tunnel`, `DPRX read timeout`)
- DisplayPort tunnelling is not supported upstream yet, so dock video stays dead.

## Verified result (2026-10-12, MacBookPro18,3 + Dell WD22TB4)

After the quirk fix, a live module reload (no reboot) brought up the USB3 tunnel:

    0: running quirk_no_usb3_bw_alloc [thunderbolt]
    0: disabling USB3 bandwidth allocation
    0:4 <-> 1:16 (USB3): activating ... USB3 Down/Up path activation complete
    0:4 <-> 1:16 (USB3): consumed bandwidth 13500/13500 Mb/s

`lsusb -t` then shows the dock's SuperSpeed hubs on the 10000M bus and `r8152 2-1.4.4` (Realtek GbE);
interface `enx<mac>` came up with carrier, DHCP and 1 Gb/s full duplex.

Live reload used (worked cleanly, no oops; mouse/headset on the dock drop for ~15 s while the
domain is torn down, so have the trackpad ready). A reboot is the conservative alternative:

    sudo modprobe -r thunderbolt_apple      # also drops thunderbolt (dependency)
    sudo modprobe thunderbolt dyndbg=+p     # dyndbg optional
    sudo modprobe thunderbolt_apple dyndbg=+p

Notes: `rtl_nic/rtl8153b-2.fw` is missing from the root's linux-firmware (r8152 works without the
patch); `could not allocate DP tunnel` / `DPRX read timeout` repeat every ~30 s (DP tunnelling is
unsupported upstream; log noise only). Turn debug off again with
`echo 'module thunderbolt -p' | sudo tee /sys/kernel/debug/dynamic_debug/control`.

## Dock video (HDMI/DP out of the dock): why it does not work, and where it stops

Status: **not supported** on this kernel, with a USB4 dock on a fixed (captive) cable. Everything
else on the dock works (USB2/USB3 hubs, headset, mouse, 1 Gb/s Ethernet).

What the kernel shows (Dell WD22TB4, monitor on the dock's DP out via a DP-to-HDMI cable):

    1:14: DP adapter HPD set, queuing hotplug          <- the dock sees the monitor: cable/monitor OK
    0:5 <-> 1:14 (DP): DPRX read timeout               <- ~316x per attempt, retried every ~30 s
    0:5: DP IN resource unavailable: DPRX negotiation failed
    1:14: could not allocate DP tunnel

Root cause: the host DP IN adapter (0:5) is never driven by a DisplayPort source. The Linux
thunderbolt core waits for the adapter's DPRX capabilities, which only appear once the display
controller (DCP) acts as DP source on the tunnel. In this device tree the DCP external pipes are wired
only to the ATC PHYs (`dcpext1`: `apple,dptx-phy = <1>`, `mux-controls = <&atcphy1_xbar>`,
connector `displayport = <&dcpext1>`); there is no route from the DCP to the ACIO DP IN adapters, and
`apple-dcp` has no tunnelled-DP mode. Upstream says the same: DP/PCIe tunnelling "need further
reverse engineering" (Sven Peter's USB4 series, Aug 2026). No Asahi branch has it (checked
`sven/tbt-wip`, `tbt-reset-wip`, `b4/apple-soc-tbt`, `dcp/dptx-fixes`, `dp-altmode-WIP`).

What would be required: DCP firmware protocol for a tunnelled DPTX endpoint, AUX-over-tunnel via the
DP IN adapter, crossbar/DPXBAR routing to ACIO instead of an ATC PHY, plus link training - new driver
work against undocumented firmware.

Workarounds that do not need that code (not verified here): a non-Thunderbolt/USB4 USB-C cable so the
dock falls back to plain DP Alt Mode on the fairydust DP port (front-left, atcphy1); or a USB-C to
DP/HDMI adapter on that port. Neither applies when the dock cable is captive.

Retry noise: fixed by `QUIRK_NO_DP_TUNNEL` (set for Apple host routers in `quirks.c`, checked at the
top of `tb_tunnel_dp()` in `tb.c`). With it the host no longer allocates a DP IN resource, burns ~300
`DPRX read timeout` polls and tears the attempt down every ~30 s; it logs one debug line instead
("host does not support DP tunneling, not creating tunnel"). Remove the table entry once DisplayPort
tunnelling is implemented. Installed module checked by string/exports/section comparison; not yet
observed live against the dock (it was unplugged when the module was reloaded) - re-check with
`journalctl -k | grep -c "DPRX read timeout"` after the next dock connection (expect 0).

## Boot menu

`install-stage2.sh` adds the "elementary OS (M-series, fairydust + USB4)" entry and makes it the default
(`set default=elementary-usb4-test` in `/boot/grub/custom.cfg`; the id keeps the old name). The earlier
fairydust and stock entries stay in the menu as fallbacks. Revert the default by setting
`elementary-fairydust` (or restore `custom.cfg.bak-before-usb4-default`).

## Suspend with a dock attached (found 2026-10-13)

`thunderbolt-apple-acio` vetoes system suspend while a USB4/Thunderbolt connection is active
(`apple_cio_prepare` returns -EBUSY, kernel log: "unable to suspend while a USB4/Thunderbolt connection is active").
Closing the lid with the dock plugged in therefore turns the display off but the Mac keeps running, and logind retries
every 30 s. Real USB4 suspend/resume needs the ACIO firmware sleep/wake handshake and is unimplemented upstream.
USB-C devices that are not USB4 (plain hubs, Ethernet) do suspend but are lost on resume (xHCI "Save/Restore Error").

## Dock video investigation (2026-10-13)

- The dock is on port 2 = `atcphy1` (b03000000); `dcpext1` has `apple,dptx-phy = <1>`, so this port IS wired for
  display output (DCP -> dp-xbar -> ATC PHY). fairydust's plain DP Alt Mode path exists (typec_displayport,
  display crossbar), but the Asahi Feb 2026 report says it is "kind of" done and "blesses" one port at a time.
- With the dock attached the CD321x negotiates USB4 on its own. Registers read (read-only, i2c-0 addr 0x3f):
  DATA_STATUS = 0x0016800013 -> data connection, USB2, **USB4_CONNECTION (bit 23)**, no DP_CONNECTION (bit 8),
  no TBT_CONNECTION (bit 16). `usb_mode` in sysfs is read-only. The driver's only commands are SSPS, DBfg, PTC*,
  GAID, SWUF/SWDF, SWSk/SWSr; none restricts USB4. No documented CD321x command to forbid USB4 was found, and
  blind commands to a live PD controller were judged not worth the risk.
- Open routes: (1) find the CD321x vendor command that disables USB4/TBT (needs tracing macOS's driver with the m1n1
  hypervisor from a second computer) so the dock falls back to DP Alt Mode; (2) implement DP tunnelling (DCP ->
  ACIO DP-IN adapter), unimplemented upstream.

### Upstream status, researched 2026-10-13

- Sven Peter's USB4 series (v2, 22 patches, 2026-09-06) says: "Right now only XDomain connections and USB3-via-USB4
  tunnels are supported. Both PCIe and DisplayPort tunnels will come later since those require additional work and
  reverse engineering that is not done yet." His DP-tunnel *fixes* series exists only because DPRX reads time out.
- An Asahi tipd patch ("Disable mode control") records that the CD321x firmware picks the mode and Linux cannot
  influence it, so "make the dock fall back to DP Alt Mode" is not available from software.
- Another developer (ice3186/linux PR #1, J414c, Aug 2026) is prototyping DP source hooks and says the blocker is
  the unknown T602x/T600x DPIN0/DPIN1 crossbar programming, which needs an m1n1-hypervisor MMIO trace of macOS
  running a dock (second computer required). No video yet.
- `mseries-verify` check `upstream-dp-watch` polls AsahiLinux/linux `fairydust` every 6 h for new DP/USB4 commits
  (baseline ce9f2eba72, 0 ahead on 2026-10-13) and notifies when something lands.

## Build configuration preserved during storage cleanup (2026-10-13)

`config` is the build input preserved from the working kit; it was missing
from this directory even though PKGBUILD lists it as a source. Its SHA-256 is
`0d3540afc18751b236d816312b7a0d7311d2860476b1fce6668f6565ea04c3fd`.
`running-config` is a decompressed snapshot of `/proc/config.gz` for the
running `7.1.13-1-2-fairydust-usb4-ARCH` kernel; it records the final config,
not a substitute for the build input. Its SHA-256 is
`cc29f7340f5eac328e3553536879f0c3fd8937ee3a4c415a6d506c71008cc40a`.
The two configurations differ; PKGBUILD adjusts feature flags during build.

The extracted source directories were archived and integrity-checked before
cleanup. See `mseries/STORAGE-PLAN.md`. Installed kernel/modules, boot images,
known-good m1n1 recovery copies, and binary package backups were retained.

### Legacy Arch rebuild environment retired on the owner's host

The compiled Fairydust kernel is installed and running independently of the
old Omarchy root. That old root/home and its snapshots were explicitly
retired during storage cleanup; see mseries/STORAGE-PLAN.md. Historical
build-pkg.sh/build-m1n1.sh/install-stage1.sh mount @ and @home and therefore
require a replacement Arch chroot/container before reuse on this host.
Do not run them assuming that the removed subvolumes still exist. This
retirement does not remove the installed kernel/modules or recovery images.
