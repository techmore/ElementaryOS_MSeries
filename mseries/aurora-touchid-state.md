# Aurora SEP / Touch ID install — state (2026-10-17)

Goal: Touch ID on MacBook Pro 14" M1 Pro (j314s), elementary OS 9 on Asahi, so
fingerprint unlocks sudo/polkit/login (reduce prompts in agent sessions).

## Installed (all reversible)
- Kernel `7.1.12-2-20261015.19-sep-ARCH` (repo: omacom/linux-aurora, release
  aurora-2026.10.15.19; SHA256 verified):
  - modules: /lib/modules/7.1.12-2-20261015.19-sep-ARCH/
  - image: /boot/vmlinuz-aurora-sep-20261015.19
  - initramfs: /boot/initrd.img-7.1.12-2-20261015.19-sep-ARCH (has apple-sep.ko)
- GRUB entry id `elementary-aurora-sep` appended to /boot/grub/custom.cfg
  (default entry `elementary-mseries` unchanged; one-shot boot set via grub-reboot)
- Aurora userspace (aurora-touchid-20261003-2):
  - /usr/lib/systemd/system/apple-sep.{service,path} (path enabled)
  - /usr/lib/systemd/system/fprintd.service.d/aurora.conf (waits for /dev/sep-bio)
  - /usr/lib/systemd/system-sleep/aurora-touchid (stops fprintd before sleep)
  - /usr/bin/aurora-touchid-setup (enroll + PAM wiring; --remove to undo)
  - /usr/lib/aurora-touchid/{extract-mesa-calibration,wait-for-display}
- libfprint replaced with Aurora build 1.94.100 at
  /usr/lib/aarch64-linux-gnu/libfprint-2.so.2.0.0
  (distro original backed up in /var/backups/aurora-sep-userspace-20261017-001635/)

## Backups
- /var/backups/aurora-sep-install-20261017-001600/ (grub custom.cfg, boot listing)
- /var/backups/aurora-sep-userspace-20261017-001635/ (original libfprint)
- Downloads + scripts: /tmp/opencode/aurora/ (aurora-touchid.sh = PAM wiring)

## Next steps after reboot into the aurora kernel
1. Verify: `uname -r`, `systemctl status apple-sep.path apple-sep.service`,
   `ls -la /dev/sep-bio`, `journalctl -k | grep -i sep`
2. Start fprintd: `sudo systemctl start fprintd` then `fprintd-list $USER`
   (device should appear as the Apple SEP)
3. Enroll (needs physical finger): `sudo aurora-touchid-setup`
   -> runs fprintd-enroll + fprintd-verify + adds pam_fprintd to
      /etc/pam.d/sudo and /etc/pam.d/polkit-1 (creates polkit-1 if missing)
4. Lock screen: gala's lock PAM service TBD — test, then wire pam_fprintd into
   whichever /etc/pam.d/<service> the lock screen uses.
5. Agent-session ergonomics: sudo timestamp_timeout, polkit, gh/git credentials.

## Known caveats
- LUKS disk passphrase at boot is unchanged (SEP is asleep that early; no TPM).
- Dell dock: detach for first boot (community j314s reports had flaky boots
  with Thunderbolt displays attached).
- Rollback: pick any other GRUB entry. Nothing was deleted.

## Finding 2026-10-17 — SEP cannot attach on j314s (device tree, not config)

Booted the Aurora kernel successfully (the shipped initramfs was a hooks-less
mkinitcpio image and dropped to the initramfs shell; it has been rebuilt from the
known-good image — original kept in /var/backups/).

Software side is all correct and ready:
- `apple_sep` module loads (`drivers/soc/apple/apple-sep.ko`)
- `apple-sep.path` / `apple-sep.service` now succeed (they had been failing on
  7.1.13-3-2-ARCH with "Module apple-sep not found" and the failure cascade
  disabled the path unit)
- libfprint is the Aurora build (mentions `apple-sep`, `sep-bio`)
- fprintd starts and stays active

The blocker: **`apple_sep` binds to zero devices.** There is no SEP node in this
machine's device tree — `/proc/device-tree` has no `*sep*`, `*bio*`, `*touch*` or
`*fingerprint*` node, and the driver directory holds no device symlinks. With
nothing to bind, it logs nothing, registers no misc device, and never creates
`/dev/sep-bio`, so fprintd reports "No devices available".

Tell that this is a 16-inch port: the driver's opt-in parameters are named
`j414s_persistent_enrol` and `probe_owner_export`. This machine is **j314s** —
"Apple MacBook Pro (14-inch, M1 Pro, 2021)".

To make Touch ID work here, the missing piece is a **device-tree node for the SEP
on j314s** (register base, interrupt, RTKit endpoint) — obtainable from macOS/ADT
or by porting the j414s node. It is not reachable by starting services or setting
module parameters. Everything else is already in place, so the DT node is the
only remaining work.

## Precise blocker + next step — 2026-10-17 (from the kernel source)

Source: `omacom/linux-aurora` @ `5ec1028c` (branch `integration/aurora`; the tip
is the release merge for this exact build, so there is nothing newer to wait for).

The driver matches **`compatible = "apple,sep"`**
(`drivers/soc/apple/sep.rs`, `OF_TABLE`). It is Rust; `/dev/sep-bio` is published
by a one-shot boot-time bring-up (`bio_shim.c` `misc_register`), and Touch ID is
activated by the **first open** of that node.

SEP nodes ship for **t8103 (M1), t602x (M2), t8112, t8122, t8140** — and are
**missing for t6000/t6001/t6002** (M1 Pro/Max/Ultra). This machine is
`apple,j314s` / `apple,t6000`, hence zero devices bound.

Node to add, to `arch/arm64/boot/dts/apple/t600x-die0.dtsi` (that file already has
six `apple,t6000-asc-mailbox` instances, so only a seventh is needed), modelled on
`t602x-die0.dtsi:733`:

    sep: sep@... {
        compatible = "apple,sep";
        reg = <... 0x6C000>;
        mboxes = <&sep_mbox>;
        mbox-names = "mbox";
        iommus = <&sep_dart 0>;
        power-domains = <&ps_sep>;
        status = "disabled";
    };
    sep_mbox: mbox@... {
        compatible = "apple,t6000-asc-mailbox", "apple,asc-mailbox-v4";
        reg = <... 0x4000>;
        interrupts = <AIC_IRQ a>, <AIC_IRQ b>, <AIC_IRQ c>, <AIC_IRQ d>;
        interrupt-names = "send-empty", "send-not-empty",
            "recv-empty", "recv-not-empty";
        #mbox-cells = <0>;
    };

The probe takes no MMIO `reg` and no IRQ; what it actually needs is the mailbox
(`Mailbox::new_byname(dev, c"mbox")`) plus power domains and the IOMMU.

**Unknown, and the only thing blocking:** t6000's SEP mailbox base address and its
four interrupt numbers, plus the SEP DART. These are silicon-specific and must
come from the ADT — boot macOS (still installed: nvme0n1p1/2/3/6 are APFS) and read
`ioreg -l -p IODeviceTree`, or dump the ADT through m1n1. Do not guess from the
t8103/t602x values: wrong MMIO or IRQs can hang the boot. Keep a stock-kernel
entry available, and flip `status` to `"okay"` only once the addresses are
confirmed.
