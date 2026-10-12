# ANE candidate preflight — 2026-10-12

Target: M1 Pro / T6000 / j314s. Source:
[joshuaswarren/omarchy-ane](https://github.com/joshuaswarren/omarchy-ane)
at `000ef5f6b0ef3652dc3ce0233c23747c12c2f875`.

The upstream driver and userspace were prepared locally. No module was
installed or loaded, no firmware was fetched, and no live device tree, m1n1
image or GRUB entry was changed. This is build/overlay compatibility evidence,
not ANE hardware qualification.

## Results

- `libane` and `ane-run`, `ane-session`, `ane-selfcheck` compile on elementary.
- `make -B -C tools check` passes on the host, including the mocked IOCTL,
  stats, pool, session-cache, probe-network, lookup-digest and LeakSanitizer
  checks. The initial sandbox run could not run LeakSanitizer under tracing;
  host execution resolved it. `-B` is needed because upstream tracks some
  x86-64 test binaries which ordinary make initially treated as current.
- `ane.ko` builds inside the existing Arch kernel build root. Its vermagic is
  `7.1.13-1-2-fairydust-usb4-ARCH SMP preempt mod_unload aarch64`, matching
  the running release. Its source version is `C33A315E498A1BC1242CD90`.
- `t6000-ane.dts` compiles and applies to a private copy of the currently
  pinned `t6000-j314s.dtb`. The new `/soc/ane@284000000` reports compatible
  `apple,t6000-ane`, status `okay`.
- Decompiled base and candidate both contain 18 `usb4` and 13 `acio` strings.
  This is a limited preservation sanity check, not a complete DT diff or dock test.

Artifacts live outside Git at `~/Documents/mseries-ane-staging/`.
Reproduce the build/staging with `bash mseries/local-ai/stage-ane.sh` after
obtaining the pinned source and retaining the matching kernel build root.
The script deliberately stops if the kernel or source revision differs.

| Artifact | SHA-256 from this session |
| --- | --- |
| ane.ko | `7bca9db7b35c214881bdad886e5f2ac42f06f33bf338ca1acc999ca3ec5f6608` |
| t6000-ane.dtbo | `63f18b9f51ab81216d6af3567cfe99b78b9eb1e064442730fcfde8760e73ba62` |
| t6000-j314s-ane.dtb | `6177dc3df0825193137e413b3dd54e7a97386fccdec4307c3cfdcf08f4016956` |

## Remaining activation work

Our Arch root explicitly pins USB4 DTBs in `/etc/default/update-m1n1`.
The upstream overlay installer may refuse a kernel-owned DTBS pin. Preserve
that arrangement; do not replace it with a stock tree or run the upstream
Arch package installer directly on elementary.

Activation requires a backed-up shared m1n1 image and pinned DTB directory,
a module installation matching this kernel, a deliberately rebuilt boot image,
and a reboot with recovery available. Then follow upstream's staged bring-up
ladder: inspect the enabled DT node, bound driver, power and device ownership
before bounded execution tests. Never use a successful host build as permission
to skip that ladder. After a hung submission, upstream requires reboot rather
than unloading/reloading the module.

Neither ANE execution nor Touch ID functionality has been established here.
