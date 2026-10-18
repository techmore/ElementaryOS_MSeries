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

## Precise blocker, and the fix — 2026-10-17 (corrected)

> **Correction:** an earlier version of this section claimed the aurora kernel
> ships no SEP node for t6000 and that the ADT had to be dumped from macOS. That
> was wrong — a `head -5` truncated the grep and hid `t600x-die0.dtsi`. The node
> exists, is complete, and the fix needed no macOS at all.

Source: `omacom/linux-aurora` @ `5ec1028c` (branch `integration/aurora`; the tip is
the release merge for this exact build, so there is nothing newer to wait for).

The driver matches **`compatible = "apple,sep"`** (`drivers/soc/apple/sep.rs`,
`OF_TABLE`); it is Rust. `/dev/sep-bio` is published by a one-shot boot-time
bring-up (`bio_shim.c` `misc_register`), and Touch ID is activated by the **first
open** of that node.

**The real cause:** the SEP node exists and is complete for t6000 —
`t600x-die0.dtsi` defines `sep@396400000`, `sep_mbox@396408000` (four IRQs),
`sep_dart@3952c0000`, and `t600x-pmgr.dtsi` defines `ps_sep`. The aurora package
even ships `dtbs/t6000-j314s.dtb` with `status = "okay"`.

But the boot chain does not use that file. The DTBs are **embedded in
`/boot/m1n1/boot.bin`** (m1n1 | run of 110 concatenated DTBs | gzip U-Boot), and
the j314s copy in there had `status = "disabled"` — so the driver had nothing
enabled to bind to. That is the whole bug.

**Fix applied 2026-10-17:**

```bash
# extract the booting j314s DTB out of boot.bin, flip only the sep status,
# recompile, and swap it back in place
python3 mseries/fairydust/usb4/swap-dtb.py \
    --in /boot/m1n1/boot.bin \
    --dtb patched-j314s.dtb --match apple,j314s --out boot.bin.new
sudo install -m755 boot.bin.new /boot/m1n1/boot.bin
```

Verified: the decompiled before/after differs by exactly one line
(`status = "disabled"` -> `"okay"`); the other 25 disabled nodes are untouched;
`swap-dtb.py` re-parses the output and confirms the m1n1 binary, the other 109
DTBs and the gzip U-Boot tail are byte-identical.

Backup: `/boot/m1n1/boot.bin.pre-sep-20261017-100328` (alongside the existing
`boot.bin.KNOWN-GOOD-*` copies).

**This affects every boot entry**, because m1n1 is below the kernel — which is
why the patch was kept to the single `sep` node rather than swapping in the
aurora DTB wholesale (the two differ by ~1580 lines).

**Untested:** whether the SEP actually brings up once enabled. The probe takes no
MMIO `reg` and no IRQ; it needs the mailbox, the power domain and the IOMMU, all
of which are present. Reboot into Aurora and check `/dev/sep-bio`.

**Rollback:** `sudo install -m755 /boot/m1n1/boot.bin.pre-sep-20261017-100328
/boot/m1n1/boot.bin`.

## Touch ID: the SEP is LIVE on j314s — 2026-10-17 (major)

Two m1n1 device-tree patches took it from "driver binds to nothing" to a working
SEP. Both are in `/boot/m1n1/boot.bin`, applied with `fairydust/usb4/swap-dtb.py`
(one property / one alias changed, everything else byte-identical):

1. `status = "disabled"` -> `"okay"` on `/soc/sep@396400000`
2. added the alias `sep = "/soc/sep@396400000"`

The alias was the real unlock. m1n1's `dt_set_sep()` (`src/kboot.c`) reads the
SEP's firmware blobs from the ADT and injects them — but it looks the node up
**by alias** and silently returns when there is none. With the alias present,
m1n1 injects `local-policy-manifest` (2902 B) and `iboot-manifest` (5443 B).

Result, verified:

```
/dev/sep-bio                      exists (char 10:261)
apple_sep 396400000.sep:          bound
apple_sep: sks: identity keybag provisioned
apple_sep: hwrng: registered after ready-phase survey
```

### The calibration firmware — extracted locally, no macOS needed

`/usr/lib/aurora-touchid/extract-mesa-calibration` carves the per-device Mesa
calibration out of the **iBoot System Container** (`nvme0n1p1`), which is why
`apple-sep.path` watches for it. Run:

```bash
sudo python3 /usr/lib/aurora-touchid/extract-mesa-calibration \
    -o /lib/firmware/apple/mesacal-j314s.bin
```

Produced 65046 bytes — exactly the path the device tree asks for
(`firmware-name = "apple/mesacal-j314s.bin"`).

### What is left: one device-tree node

`fprintd` starts and finds the SEP, then says *"the secure enclave reports no
fingerprint sensor attached"*. The sensor is an SPI device and our boot DTB has
**no `spi@39b108000` controller at all** — the aurora package's
`dtbs/t6000-j314s.dtb` has it, with a `fingerprint@0` child that is already
j314s-specific:

    spi@39b108000 {
        compatible = "apple,t6000-spi", "apple,spi";
        reg = <0x03 0x9b108000 0x00 0x4000>;
        interrupt-parent = <0x13>;                 /* AIC - same phandle in both */
        interrupts = <0x00 0x00 0x454 0x04>;       /* fits between our 453 and 455 */
        clocks = <0x34>;  pinctrl-0 = <0x6b>;
        power-domains = <0x6c>;  status = "okay";
        fingerprint@0 {
            compatible = "apple,mesa-fingerprint";
            reg = <0x00>;  spi-max-frequency = <0x7a1200>;  spi-cpol;
            status = "okay";
            enable-gpios = <0x4d 0xc4 0x00>;       /* pinctrl -> OUR 0x44 */
            interrupt-parent = <0x4d>;             /* -> OUR 0x44 */
            interrupts = <0xc3 0x01>;
            firmware-name = "apple/mesacal-j314s.bin";
        };
    };

Phandle map (aurora -> ours), resolved by matching node identity:

| aurora | node | ours |
|---|---|---|
| `0x13` | `interrupt-controller@28e100000` (AIC) | `0x13` (same) |
| `0x34` | fixed-clock | `0x14` *— but our `spi@39b10c000` uses `0x2c` for the same role; unresolved* |
| `0x6b` | pinctrl state under `pinctrl@39b028000` | **unresolved** |
| `0x6c` | `power-controller@200` (pmgr-pwrstate) | `0xa3` |
| `0x4d` | `pinctrl@39b028000` (gpio) | `0x44` |

**Stopped deliberately.** The clock and pinmux references do not line up cleanly
between the two device-tree revisions (ours is an older Asahi t6000 revision), and
a wrong reference there would misconfigure a live hardware block rather than fail
safely. Resolve those two, port the node, `swap-dtb.py` it in, and reboot — the
firmware and the SEP are already in place, so that node is the last step.

Backups: `/boot/m1n1/boot.bin.pre-sep-20261017-100328` (status only) and
`boot.bin.pre-sep-alias-20261017-102233` (both patches).

## Fingerprint sensor node ported — 2026-10-17 (completed)

The `spi@39b108000` controller and its `fingerprint@0` child are now in the boot
DTB. Our boot device tree (an older Asahi t6000 revision) had `spi1-pins` and
`spi3-pins` but no `spi2-pins` and no controller for that bus at all, so the
sensor had nowhere to attach. Added both; 33 lines, nothing removed.

Phandle map, resolved by matching node identity across the two revisions — not
guessed:

| aurora | node | ours |
|---|---|---|
| `0x13` | `interrupt-controller@28e100000` (AIC) | `0x13` (same) |
| `0x34` | `clock-ref`, fixed-clock 24 MHz "clkref" | `0x2c` (identical node) |
| `0x6b` | `spi2-pins`, `pinmux = <0x10030 0x10031 0x10032>` | **added** as `0x114` |
| `0x6c` | `power-controller@200`, `apple,t6000-pmgr-pwrstate` | `0xa3` (same reg) |
| `0x4d` | `pinctrl@39b028000` (gpio) | `0x44` |

Cross-checks that made this safe: the shared `spi1-pins`/`spi3-pins` pinmux values
are **byte-identical** between the two trees, so the pin numbering matches; the new
controller's IRQ `0x454` sits exactly between our existing `0x453` and `0x455`; and
`dtc` caught a phandle collision on the first attempt (the max is `0x113`, and a
lexical sort had wrongly said `0xff`), which is what a wrong reference would have
looked like.

Backup: `/boot/m1n1/boot.bin.pre-fingerprint-20261017-103254`.

After rebooting into Aurora, the whole chain should be live:

```bash
ls -l /dev/sep-bio /dev/spi*                 # SEP + the new SPI bus
sudo systemctl start fprintd && fprintd-list "$USER"
sudo aurora-touchid-setup                    # enrol, then wire PAM
```

If `fprintd-list` still says no devices, `dmesg | grep -iE "mesa|fingerprint|spi"`
will say whether the controller probed and whether the sensor answered.

## First Aurora boot with the patched DTB froze — 2026-10-17 21:56

Booted `7.1.12-2-20261015.19-sep-ARCH`. `apple_sep` bound and the SEP came up
(T6000/J316s profile, firmware accepted, 12 endpoints, hwrng registered,
`apple-sep.service` finished). The journal stops at 21:56:47, about 34 s in: no
panic/oops/shutdown, next boot (stock `7.1.13-3-2-ARCH`) reported "uncleanly shut
down", `/sys/fs/pstore` empty. No fprintd/fingerprint-sensor lines and no
`/dev/sep-bio` in that boot's log before the stop. Also logged:
`xART: /chosen/apfs-preboot-uuid is unavailable`. Cause unknown (SEP, the new
SPI sensor node, DCP, or unrelated). Next: read-only correlation of the freeze
with first `/dev/sep-bio` access before any second boot.
